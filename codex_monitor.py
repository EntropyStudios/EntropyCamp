"""Fast local Codex thread monitoring for reminder cards.

The Codex state database tells us which rollout file belongs to a thread. Rollout
files are append-only JSONL, so watching just the new bytes avoids repeatedly
loading every turn through app-server.
"""

from __future__ import annotations

import json
import re
import sqlite3
import threading
import time
import urllib.parse
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable


TASK_EVENT_TYPES = {"task_started", "task_complete", "turn_aborted"}
PHASE_LABELS = {
    "idle": "保持关注",
    "reasoning": "推理中",
    "outputting": "AI 输出",
    "executing": "执行工具",
    "changingFiles": "修改文件",
    "usingTool": "调用工具",
    "searching": "搜索资料",
    "waiting": "等待确认",
    "unavailable": "连接断开",
}


class CodexStateUnavailable(RuntimeError):
    """Raised when the local Codex state database cannot be read."""


@dataclass
class _ThreadState:
    id: str
    name: str
    preview: str
    updated_at: int | float | None
    rollout_path: Path | None
    exists: bool = True
    status: str = "unknown"
    latest_completed_turn_id: str | None = None
    latest_completed_at: int | float | None = None
    model: str = ""
    reasoning_effort: str = ""
    cwd: str = ""
    phase: str = "idle"
    phase_label: str = PHASE_LABELS["idle"]
    activity_started_at: int | float | None = None
    tool_kind: str = ""
    offset: int = 0

    def public(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "preview": self.preview,
            "updatedAt": self.updated_at,
            "status": self.status,
            "exists": self.exists,
            "latestCompletedTurnId": self.latest_completed_turn_id,
            "latestCompletedAt": self.latest_completed_at,
            "model": self.model,
            "reasoningEffort": self.reasoning_effort,
            "cwd": self.cwd,
            "phase": self.phase,
            "phaseLabel": self.phase_label,
            "activityStartedAt": self.activity_started_at,
            "toolKind": self.tool_kind,
        }


class CodexRolloutMonitor:
    """Watch linked Codex threads by tailing their append-only rollout files."""

    def __init__(self, codex_home: Path, poll_interval: float = 0.35) -> None:
        self.codex_home = Path(codex_home).expanduser()
        self.poll_interval = max(0.02, float(poll_interval))
        self._states: dict[str, _ThreadState] = {}
        self._condition = threading.Condition(threading.RLock())
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._revision = 0

    @property
    def revision(self) -> int:
        with self._condition:
            return self._revision

    @property
    def stopped(self) -> bool:
        return self._stop_event.is_set()

    def start(self) -> None:
        with self._condition:
            if self._thread and self._thread.is_alive():
                return
            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._watch_loop,
                name="codex-rollout-monitor",
                daemon=True,
            )
            self._thread.start()

    def close(self) -> None:
        self._stop_event.set()
        with self._condition:
            self._condition.notify_all()
            thread = self._thread
        if thread and thread.is_alive():
            thread.join(timeout=max(1.0, self.poll_interval * 3))

    def list_threads(self, limit: int = 100) -> list[dict[str, Any]]:
        records = self._read_thread_records()
        records.sort(key=lambda record: record["sortKey"], reverse=True)
        return [
            {
                "id": record["id"],
                "name": record["name"],
                "preview": record["preview"],
                "updatedAt": record["updatedAt"],
                "model": record["model"],
                "reasoningEffort": record["reasoningEffort"],
                "cwd": record["cwd"],
            }
            for record in records[: max(1, limit)]
        ]

    def rollout_sources(self, thread_ids: list[str]) -> list[dict[str, Any]]:
        """Resolve thread metadata and append-only rollout paths in request order."""
        ordered_ids = list(dict.fromkeys(thread_ids[:50]))
        records = {
            record["id"]: record
            for record in self._read_thread_records(
                ordered_ids, include_archived=True
            )
        }
        return [
            {
                "id": thread_id,
                "name": (records.get(thread_id) or {}).get("name") or "Codex 对话",
                "preview": (records.get(thread_id) or {}).get("preview") or "",
                "rolloutPath": (records.get(thread_id) or {}).get("rolloutPath"),
            }
            for thread_id in ordered_ids
        ]

    def thread_statuses(self, thread_ids: list[str]) -> list[dict[str, Any]]:
        ordered_ids = list(dict.fromkeys(thread_ids[:50]))
        self.start()
        self._ensure_threads(ordered_ids)
        with self._condition:
            return [self._states[thread_id].public() for thread_id in ordered_ids]

    def wait_for_change(
        self,
        thread_ids: list[str],
        after_revision: int,
        timeout: float = 15.0,
    ) -> tuple[int, list[dict[str, Any]]]:
        ordered_ids = list(dict.fromkeys(thread_ids[:50]))
        self.start()
        self._ensure_threads(ordered_ids)
        with self._condition:
            self._condition.wait_for(
                lambda: self._revision > after_revision or self._stop_event.is_set(),
                timeout=max(0.0, timeout),
            )
            return self._revision, [self._states[thread_id].public() for thread_id in ordered_ids]

    def _state_database(self) -> Path:
        candidates = list(self.codex_home.glob("state_*.sqlite"))
        if not candidates:
            raise CodexStateUnavailable("没有找到 Codex 状态数据库")

        def version_key(path: Path) -> tuple[int, float]:
            match = re.fullmatch(r"state_(\d+)\.sqlite", path.name)
            version = int(match.group(1)) if match else -1
            try:
                modified = path.stat().st_mtime
            except OSError:
                modified = 0
            return version, modified

        return max(candidates, key=version_key)

    def _connect(self) -> sqlite3.Connection:
        database = self._state_database()
        encoded = urllib.parse.quote(str(database), safe="/")
        connection = sqlite3.connect(
            f"file:{encoded}?mode=ro",
            uri=True,
            timeout=1.0,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only = ON")
        return connection

    def _read_thread_records(
        self,
        thread_ids: Iterable[str] | None = None,
        *,
        include_archived: bool = False,
    ) -> list[dict[str, Any]]:
        try:
            with self._connect() as connection:
                columns = {
                    row["name"] for row in connection.execute("PRAGMA table_info(threads)")
                }
                required = {"id", "rollout_path"}
                if not required.issubset(columns):
                    raise CodexStateUnavailable("Codex 状态数据库缺少线程信息")
                selected = [
                    column
                    for column in (
                        "id",
                        "rollout_path",
                        "name",
                        "title",
                        "preview",
                        "updated_at_ms",
                        "updated_at",
                        "recency_at_ms",
                        "recency_at",
                        "archived",
                        "model",
                        "reasoning_effort",
                        "cwd",
                    )
                    if column in columns
                ]
                clauses: list[str] = []
                parameters: list[Any] = []
                ids = list(dict.fromkeys(thread_ids or []))
                if ids:
                    clauses.append(f"id IN ({','.join('?' for _ in ids)})")
                    parameters.extend(ids)
                if "archived" in columns and not include_archived:
                    clauses.append("archived = 0")
                where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
                rows = connection.execute(
                    f"SELECT {', '.join(selected)} FROM threads{where}", parameters
                ).fetchall()
        except (OSError, sqlite3.Error) as error:
            raise CodexStateUnavailable(str(error)) from error

        records: list[dict[str, Any]] = []
        for row in rows:
            values = dict(row)
            name = values.get("name") or values.get("title") or values.get("preview") or "未命名对话"
            updated_at = values.get("updated_at_ms") or values.get("updated_at")
            sort_key = (
                values.get("recency_at_ms")
                or values.get("updated_at_ms")
                or (values.get("recency_at") or 0) * 1000
                or (values.get("updated_at") or 0) * 1000
            )
            rollout_value = values.get("rollout_path")
            records.append(
                {
                    "id": values["id"],
                    "name": name,
                    "preview": values.get("preview") or "",
                    "updatedAt": updated_at,
                    "sortKey": sort_key or 0,
                    "rolloutPath": Path(rollout_value) if rollout_value else None,
                    "model": values.get("model") or "",
                    "reasoningEffort": values.get("reasoning_effort") or "",
                    "cwd": values.get("cwd") or "",
                }
            )
        return records

    def _ensure_threads(self, thread_ids: list[str]) -> None:
        if not thread_ids:
            return
        records = {record["id"]: record for record in self._read_thread_records(thread_ids)}
        initialized: dict[str, _ThreadState] = {}
        with self._condition:
            missing_or_changed = [
                thread_id
                for thread_id in thread_ids
                if thread_id not in self._states
                or self._states[thread_id].rollout_path
                != (records.get(thread_id) or {}).get("rolloutPath")
            ]

        for thread_id in missing_or_changed:
            record = records.get(thread_id)
            if not record:
                initialized[thread_id] = _ThreadState(
                    id=thread_id,
                    name="Codex 对话",
                    preview="",
                    updated_at=None,
                    rollout_path=None,
                    exists=False,
                    status="unavailable",
                )
            else:
                initialized[thread_id] = self._initialize_state(record)

        changed = False
        with self._condition:
            for thread_id in thread_ids:
                if thread_id in initialized:
                    self._states[thread_id] = initialized[thread_id]
                    changed = True
                    continue
                record = records.get(thread_id)
                state = self._states[thread_id]
                if not record:
                    if state.exists or state.status != "unavailable":
                        state.exists = False
                        state.status = "unavailable"
                        changed = True
                    continue
                for attribute, value in (
                    ("name", record["name"]),
                    ("preview", record["preview"]),
                    ("updated_at", record["updatedAt"]),
                    ("model", record["model"]),
                    ("reasoning_effort", record["reasoningEffort"]),
                    ("cwd", record["cwd"]),
                ):
                    if getattr(state, attribute) != value:
                        setattr(state, attribute, value)
                        changed = True
            if changed:
                self._revision += 1
                self._condition.notify_all()

    def _initialize_state(self, record: dict[str, Any]) -> _ThreadState:
        path = record["rolloutPath"]
        state = _ThreadState(
            id=record["id"],
            name=record["name"],
            preview=record["preview"],
            updated_at=record["updatedAt"],
            rollout_path=path,
            model=record.get("model") or "",
            reasoning_effort=record.get("reasoningEffort") or "",
            cwd=record.get("cwd") or "",
        )
        if not path or not path.is_file():
            state.status = "unavailable"
            return state

        stable_end = self._stable_end(path)
        latest_event, latest_completion = self._recent_task_events(path, stable_end)
        state.offset = stable_end
        if latest_event:
            state.status = "active" if latest_event[0] == "task_started" else "idle"
        else:
            state.status = "unknown"
        if latest_completion:
            state.latest_completed_turn_id = latest_completion[1].get("turn_id")
            state.latest_completed_at = latest_completion[1].get("completed_at")
        if state.status == "active":
            phase, label, started_at, model, effort, tool_kind = self._recent_activity(path, stable_end)
            state.phase = phase
            state.phase_label = label
            state.activity_started_at = started_at
            state.model = model or state.model
            state.reasoning_effort = effort or state.reasoning_effort
            state.tool_kind = tool_kind
        else:
            state.phase = "idle"
            state.phase_label = PHASE_LABELS["idle"]
        return state

    @staticmethod
    def _record_timestamp(message: dict[str, Any]) -> int | float | None:
        value = message.get("timestamp")
        if isinstance(value, (int, float)):
            return value / 1000 if value > 10_000_000_000 else value
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
            except ValueError:
                return None
        return None

    @staticmethod
    def _phase_for_item(item_type: str, *, completed: bool = False) -> tuple[str, str]:
        normalized = re.sub(r"[^a-z]", "", str(item_type).lower())
        if normalized in {"commandexecution", "customtoolcall", "shellcall"}:
            return ("reasoning", PHASE_LABELS["reasoning"]) if completed else ("executing", PHASE_LABELS["executing"])
        if normalized == "filechange":
            return ("reasoning", PHASE_LABELS["reasoning"]) if completed else ("changingFiles", PHASE_LABELS["changingFiles"])
        if normalized in {"mcptoolcall", "dynamictoolcall", "functioncall"}:
            return ("reasoning", PHASE_LABELS["reasoning"]) if completed else ("usingTool", PHASE_LABELS["usingTool"])
        if normalized in {"websearch", "extension"}:
            return ("reasoning", PHASE_LABELS["reasoning"]) if completed else ("searching", PHASE_LABELS["searching"])
        if normalized in {"agentmessage", "message"}:
            return "outputting", PHASE_LABELS["outputting"]
        return "reasoning", PHASE_LABELS["reasoning"]

    @staticmethod
    def _tool_kind(item: dict[str, Any], item_type: str) -> str:
        normalized = re.sub(r"[^a-z]", "", str(item_type).lower())
        if normalized in {"commandexecution", "customtoolcall", "shellcall"}:
            return str(item.get("name") or "命令")[:32]
        if normalized in {"mcptoolcall", "dynamictoolcall", "functioncall"}:
            return str(item.get("tool") or item.get("name") or "工具")[:32]
        if normalized in {"websearch", "extension"}:
            return "搜索"
        if normalized == "filechange":
            return "文件变更"
        return ""

    @classmethod
    def _activity_signal(
        cls, message: dict[str, Any]
    ) -> tuple[str, str, int | float | None, str, str, str] | None:
        timestamp = cls._record_timestamp(message)
        record_type = message.get("type")
        payload = message.get("payload") or {}
        if record_type == "turn_context":
            return "reasoning", PHASE_LABELS["reasoning"], timestamp, str(payload.get("model") or ""), str(payload.get("effort") or payload.get("reasoning_effort") or ""), ""
        if record_type == "response_item":
            item_type = str(payload.get("type") or "")
            if item_type == "custom_tool_call_output" or item_type.endswith("_call_output"):
                phase, label = "reasoning", PHASE_LABELS["reasoning"]
            elif item_type == "message" and payload.get("role") != "assistant":
                return None
            else:
                phase, label = cls._phase_for_item(item_type, completed=False)
            return phase, label, timestamp, "", "", cls._tool_kind(payload, item_type)
        if record_type != "event_msg":
            return None
        event_type = payload.get("type")
        if event_type == "task_started":
            started_at = payload.get("started_at")
            return "reasoning", PHASE_LABELS["reasoning"], started_at if isinstance(started_at, (int, float)) else timestamp, "", "", ""
        if event_type in {"task_complete", "turn_aborted"}:
            return "idle", PHASE_LABELS["idle"], timestamp, "", "", ""
        if event_type in {"agent_message", "item_started", "item_completed"}:
            item = payload.get("item") or {}
            item_type = item.get("type") or ("AgentMessage" if event_type == "agent_message" else "")
            phase, label = cls._phase_for_item(str(item_type), completed=event_type == "item_completed")
            return phase, label, timestamp, "", "", cls._tool_kind(item, str(item_type))
        return None

    @classmethod
    def _recent_activity(
        cls, path: Path, end: int
    ) -> tuple[str, str, int | float | None, str, str, str]:
        start = max(0, end - 512 * 1024)
        with path.open("rb") as file:
            file.seek(start)
            data = file.read(end - start)
        if start > 0:
            newline = data.find(b"\n")
            data = data[newline + 1 :] if newline >= 0 else b""
        current: tuple[str, str, int | float | None, str, str, str] = (
            "reasoning", PHASE_LABELS["reasoning"], None, "", "", ""
        )
        model = ""
        effort = ""
        for raw_line in data.splitlines():
            try:
                message = json.loads(raw_line)
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue
            signal = cls._activity_signal(message)
            if not signal:
                continue
            phase, label, started_at, next_model, next_effort, tool_kind = signal
            model = next_model or model
            effort = next_effort or effort
            current = phase, label, started_at, model, effort, tool_kind
        return current

    @staticmethod
    def _stable_end(path: Path) -> int:
        with path.open("rb") as file:
            file.seek(0, 2)
            size = file.tell()
            if size == 0:
                return 0
            file.seek(size - 1)
            if file.read(1) == b"\n":
                return size
            position = size
            while position > 0:
                chunk_size = min(64 * 1024, position)
                position -= chunk_size
                file.seek(position)
                chunk = file.read(chunk_size)
                newline = chunk.rfind(b"\n")
                if newline >= 0:
                    return position + newline + 1
            return 0

    def _recent_task_events(
        self, path: Path, end: int
    ) -> tuple[tuple[str, dict[str, Any]] | None, tuple[str, dict[str, Any]] | None]:
        if end <= 0:
            return None, None
        window = 64 * 1024
        latest_event = None
        latest_completion = None
        with path.open("rb") as file:
            while True:
                start = max(0, end - window)
                file.seek(start)
                data = file.read(end - start)
                if start > 0:
                    first_newline = data.find(b"\n")
                    data = data[first_newline + 1 :] if first_newline >= 0 else b""
                events = self._parse_task_events(data.splitlines())
                if events:
                    latest_event = events[-1]
                    latest_completion = next(
                        (event for event in reversed(events) if event[0] == "task_complete"),
                        None,
                    )
                if start == 0 or (latest_event and latest_completion):
                    return latest_event, latest_completion
                window *= 2

    @staticmethod
    def _parse_task_events(lines: Iterable[bytes]) -> list[tuple[str, dict[str, Any]]]:
        events: list[tuple[str, dict[str, Any]]] = []
        for line in lines:
            if not line or b'"type"' not in line:
                continue
            try:
                message = json.loads(line)
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue
            if message.get("type") != "event_msg":
                continue
            payload = message.get("payload") or {}
            event_type = payload.get("type")
            if event_type in TASK_EVENT_TYPES:
                events.append((event_type, payload))
        return events

    def _watch_loop(self) -> None:
        while not self._stop_event.wait(self.poll_interval):
            with self._condition:
                candidates = [
                    (state.id, state.rollout_path, state.offset)
                    for state in self._states.values()
                    if state.exists and state.rollout_path
                ]
            for thread_id, path, offset in candidates:
                try:
                    size = path.stat().st_size
                except OSError:
                    self._mark_unavailable(thread_id, path)
                    continue
                if size < offset:
                    self._reinitialize(thread_id)
                elif size > offset:
                    self._consume_new_bytes(thread_id, path, offset, size)

    def _mark_unavailable(self, thread_id: str, path: Path) -> None:
        with self._condition:
            state = self._states.get(thread_id)
            if not state or state.rollout_path != path or state.status == "unavailable":
                return
            state.status = "unavailable"
            self._revision += 1
            self._condition.notify_all()

    def _reinitialize(self, thread_id: str) -> None:
        try:
            records = self._read_thread_records([thread_id])
            if not records:
                return
            replacement = self._initialize_state(records[0])
        except CodexStateUnavailable:
            return
        with self._condition:
            self._states[thread_id] = replacement
            self._revision += 1
            self._condition.notify_all()

    def _consume_new_bytes(self, thread_id: str, path: Path, offset: int, size: int) -> None:
        try:
            with path.open("rb") as file:
                file.seek(offset)
                data = file.read(size - offset)
        except OSError:
            return
        last_newline = data.rfind(b"\n")
        if last_newline < 0:
            return
        consumed = data[: last_newline + 1]
        new_offset = offset + len(consumed)
        parsed_messages: list[dict[str, Any]] = []
        for raw_line in consumed.splitlines():
            try:
                message = json.loads(raw_line)
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue
            if isinstance(message, dict):
                parsed_messages.append(message)
        events = self._parse_task_events(consumed.splitlines())

        with self._condition:
            state = self._states.get(thread_id)
            if not state or state.rollout_path != path or state.offset != offset:
                return
            state.offset = new_offset
            changed = False
            for message in parsed_messages:
                signal = self._activity_signal(message)
                if signal:
                    phase, label, started_at, model, effort, tool_kind = signal
                    state.phase = phase
                    state.phase_label = label
                    state.activity_started_at = started_at
                    state.tool_kind = tool_kind
                    if model:
                        state.model = model
                    if effort:
                        state.reasoning_effort = effort
                    if phase != "idle":
                        state.status = "active"
                    changed = True
            for event_type, payload in events:
                if event_type == "task_started":
                    if state.status != "active":
                        state.status = "active"
                        changed = True
                    state.phase = "reasoning"
                    state.phase_label = PHASE_LABELS["reasoning"]
                    state.activity_started_at = payload.get("started_at")
                elif event_type == "turn_aborted":
                    if state.status != "idle":
                        state.status = "idle"
                        changed = True
                    state.phase = "idle"
                    state.phase_label = PHASE_LABELS["idle"]
                    state.activity_started_at = None
                elif event_type == "task_complete":
                    turn_id = payload.get("turn_id")
                    completed_at = payload.get("completed_at")
                    if (
                        state.status != "idle"
                        or state.latest_completed_turn_id != turn_id
                        or state.latest_completed_at != completed_at
                    ):
                        state.status = "idle"
                        state.latest_completed_turn_id = turn_id
                        state.latest_completed_at = completed_at
                        changed = True
                    state.phase = "idle"
                    state.phase_label = PHASE_LABELS["idle"]
                    state.activity_started_at = None
            if changed:
                self._revision += 1
                self._condition.notify_all()
