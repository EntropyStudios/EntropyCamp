#!/usr/bin/env python3
"""Start the reminder-card prototype with a local Codex bridge."""

from __future__ import annotations

import contextlib
import concurrent.futures
import http.server
import json
import os
import re
import select
import socket
import subprocess
import threading
import time
import urllib.parse
import webbrowser
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from codex_monitor import CodexRolloutMonitor, CodexStateUnavailable
from feishu_notify import FeishuNotificationError, FeishuNotifier
from widget_service import WidgetSnapshotStore, create_widget_server
from state_store import BusinessStateStore, StateConflict


APP_DIRECTORY = Path(__file__).resolve().parent
CODEX_HOME = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
WIDGET_DIRECTORY = Path(
    os.environ.get("LUMEN_WIDGET_DIRECTORY", APP_DIRECTORY / "private" / "widget")
)
WIDGET_SCRIPT_PATH = APP_DIRECTORY / "scriptable" / "LumenToday.js"
WIDGET_STORE = WidgetSnapshotStore(WIDGET_DIRECTORY)
BUSINESS_STORE = None


def get_business_store():
    global BUSINESS_STORE
    if BUSINESS_STORE is None:
        BUSINESS_STORE = BusinessStateStore()
    return BUSINESS_STORE
MAX_REPORT_THREADS = 20
WORK_LOG_EVENT_TYPES = {
    "task_started",
    "task_complete",
    "turn_aborted",
    "thread_rolled_back",
    "user_message",
    "agent_message",
}
WORK_LOG_SCAN_CHUNK_SIZE = 256 * 1024


def _normalized_timestamp(value: Any) -> float | None:
    if not isinstance(value, (int, float)):
        return None
    timestamp = float(value)
    if timestamp > 10_000_000_000:
        timestamp /= 1000
    return timestamp


def _item_text(item: dict[str, Any]) -> str:
    item_type = item.get("type")
    if item_type == "userMessage":
        texts: list[str] = []
        for part in item.get("content") or []:
            if isinstance(part, str):
                texts.append(part)
            elif isinstance(part, dict):
                text = part.get("text") or part.get("inputText")
                if isinstance(text, str):
                    texts.append(text)
        return "\n".join(text.strip() for text in texts if text and text.strip())
    text = item.get("text")
    return text.strip() if isinstance(text, str) else ""


def _report_item(item: dict[str, Any], include_process: bool) -> dict[str, Any] | None:
    item_type = item.get("type")
    if item_type not in {"userMessage", "agentMessage"}:
        return None
    phase = item.get("phase")
    if item_type == "agentMessage" and not include_process and phase != "final_answer":
        return None
    text = _item_text(item)
    if not text:
        return None
    return {
        "type": item_type,
        "role": "user" if item_type == "userMessage" else "assistant",
        "phase": phase if isinstance(phase, str) else None,
        "text": text,
    }


def _turn_timestamp(turn: dict[str, Any]) -> float | None:
    return (
        _normalized_timestamp(turn.get("completedAt"))
        or _normalized_timestamp(turn.get("startedAt"))
    )


def _thread_work_log(
    thread: dict[str, Any],
    since: float | None,
    until: float | None,
    include_process: bool,
) -> dict[str, Any]:
    turns: list[dict[str, Any]] = []
    for turn in thread.get("turns") or []:
        if not isinstance(turn, dict):
            continue
        timestamp = _turn_timestamp(turn)
        if timestamp is None:
            continue
        if since is not None and timestamp < since:
            continue
        if until is not None and timestamp > until:
            continue
        items = [
            report_item
            for item in turn.get("items") or []
            if isinstance(item, dict)
            for report_item in [_report_item(item, include_process)]
            if report_item
        ]
        if not items:
            continue
        turns.append(
            {
                "id": turn.get("id"),
                "status": turn.get("status"),
                "startedAt": _normalized_timestamp(turn.get("startedAt")),
                "completedAt": _normalized_timestamp(turn.get("completedAt")),
                "items": items,
            }
        )
    return {
        "id": thread.get("id"),
        "name": thread.get("name") or thread.get("preview") or "未命名对话",
        "preview": thread.get("preview") or "",
        "turns": turns,
    }


@dataclass(frozen=True)
class RolloutScan:
    records: list[dict[str, Any]]
    bytes_read: int
    stable_end: int
    reached_boundary: bool


def _rollout_record_timestamp(record: dict[str, Any]) -> float | None:
    value = record.get("timestamp")
    normalized = _normalized_timestamp(value)
    if normalized is not None:
        return normalized
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def _scan_rollout_window(
    path: Path,
    since: float | None,
    *,
    end: int | None = None,
    chunk_size: int = WORK_LOG_SCAN_CHUNK_SIZE,
) -> RolloutScan:
    """Read complete JSONL records backwards through the first turn before since."""
    path = Path(path)
    stable_end = CodexRolloutMonitor._stable_end(path) if end is None else max(0, int(end))
    position = stable_end
    carry = b""
    records_reversed: list[dict[str, Any]] = []
    bytes_read = 0
    reached_boundary = False
    chunk_size = max(64, int(chunk_size))

    with path.open("rb") as file:
        while position > 0 and not reached_boundary:
            read_size = min(chunk_size, position)
            position -= read_size
            file.seek(position)
            data = file.read(read_size) + carry
            bytes_read += read_size
            lines = data.split(b"\n")
            if position > 0:
                carry = lines.pop(0)
            else:
                carry = b""

            for raw_line in reversed(lines):
                if not raw_line:
                    continue
                try:
                    record = json.loads(raw_line)
                except (json.JSONDecodeError, UnicodeDecodeError):
                    continue
                if record.get("type") != "event_msg":
                    continue
                payload = record.get("payload") or {}
                event_type = payload.get("type")
                if event_type not in WORK_LOG_EVENT_TYPES:
                    continue
                records_reversed.append(record)
                timestamp = (
                    _normalized_timestamp(payload.get("started_at"))
                    if event_type == "task_started"
                    else None
                ) or _rollout_record_timestamp(record)
                if (
                    since is not None
                    and timestamp is not None
                    and timestamp < since
                    and event_type == "task_started"
                ):
                    reached_boundary = True
                    break

    records_reversed.reverse()
    return RolloutScan(
        records=records_reversed,
        bytes_read=bytes_read,
        stable_end=stable_end,
        reached_boundary=reached_boundary,
    )


def _rollout_event_item(payload: dict[str, Any]) -> dict[str, Any] | None:
    event_type = payload.get("type")
    message = payload.get("message")
    if event_type not in {"user_message", "agent_message"} or not isinstance(message, str):
        return None
    message = message.strip()
    if not message:
        return None
    if event_type == "user_message":
        return {
            "type": "userMessage",
            "content": [{"type": "input_text", "text": message}],
        }
    phase = payload.get("phase")
    return {
        "type": "agentMessage",
        "phase": phase if isinstance(phase, str) else None,
        "text": message,
    }


def _thread_from_rollout_records(
    source: dict[str, Any], records: list[dict[str, Any]]
) -> dict[str, Any]:
    turns: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None

    def finish_current() -> None:
        nonlocal current
        if current is not None:
            turns.append(current)
            current = None

    for record in records:
        payload = record.get("payload") or {}
        event_type = payload.get("type")
        event_time = _rollout_record_timestamp(record)
        if event_type == "task_started":
            finish_current()
            current = {
                "id": payload.get("turn_id"),
                "status": "inProgress",
                "startedAt": _normalized_timestamp(payload.get("started_at")) or event_time,
                "completedAt": None,
                "items": [],
            }
            continue

        if event_type in {"user_message", "agent_message"}:
            item = _rollout_event_item(payload)
            if item is None:
                continue
            if current is None:
                current = {
                    "id": None,
                    "status": "inProgress",
                    "startedAt": event_time,
                    "completedAt": None,
                    "items": [],
                }
            current["items"].append(item)
            continue

        if event_type == "thread_rolled_back":
            finish_current()
            count = payload.get("num_turns")
            count = count if isinstance(count, int) and count > 0 else 0
            if count:
                del turns[max(0, len(turns) - count) :]
            continue

        if event_type not in {"task_complete", "turn_aborted"}:
            continue
        if current is None:
            current = {
                "id": payload.get("turn_id"),
                "status": "inProgress",
                "startedAt": _normalized_timestamp(payload.get("started_at")) or event_time,
                "completedAt": None,
                "items": [],
            }
        current["id"] = payload.get("turn_id") or current.get("id")
        current["startedAt"] = (
            _normalized_timestamp(payload.get("started_at")) or current.get("startedAt")
        )
        current["completedAt"] = (
            _normalized_timestamp(payload.get("completed_at")) or event_time
        )
        if event_type == "turn_aborted":
            current["status"] = "aborted"
        else:
            current["status"] = "failed" if payload.get("error") else "completed"
        finish_current()

    finish_current()
    return {
        "id": source.get("id"),
        "name": source.get("name") or source.get("preview") or "未命名对话",
        "preview": source.get("preview") or "",
        "turns": turns,
    }


def _rollout_work_log(
    source: dict[str, Any],
    since: float | None,
    until: float | None,
    include_process: bool,
    *,
    end: int | None = None,
    chunk_size: int = WORK_LOG_SCAN_CHUNK_SIZE,
) -> dict[str, Any]:
    path = source.get("rolloutPath")
    if not path:
        raise FileNotFoundError("Codex 对话没有本地记录文件")
    scan = _scan_rollout_window(Path(path), since, end=end, chunk_size=chunk_size)
    thread = _thread_from_rollout_records(source, scan.records)
    return _thread_work_log(thread, since, until, include_process)


class CodexWorkLogReader:
    """Build work logs from the recent tail of append-only rollout files."""

    def __init__(
        self,
        monitor: CodexRolloutMonitor,
        fallback_bridge: Any,
        *,
        max_workers: int = 4,
        max_cache_entries: int = 16,
        chunk_size: int = WORK_LOG_SCAN_CHUNK_SIZE,
    ) -> None:
        self.monitor = monitor
        self.fallback_bridge = fallback_bridge
        self.max_workers = max(1, int(max_workers))
        self.max_cache_entries = max(1, int(max_cache_entries))
        self.chunk_size = max(64, int(chunk_size))
        self._cache: OrderedDict[tuple[Any, ...], dict[str, Any]] = OrderedDict()
        self._cache_lock = threading.RLock()

    def _read_source(
        self,
        source: dict[str, Any],
        since: float | None,
        until: float | None,
        include_process: bool,
    ) -> dict[str, Any]:
        path_value = source.get("rolloutPath")
        if not path_value:
            raise FileNotFoundError("Codex 对话没有本地记录文件")
        path = Path(path_value)
        stat = path.stat()
        stable_end = CodexRolloutMonitor._stable_end(path)
        cache_key = (
            source.get("id"),
            str(path),
            stat.st_mtime_ns,
            stable_end,
            source.get("name"),
            source.get("preview"),
            since,
            until,
            include_process,
        )
        with self._cache_lock:
            cached = self._cache.get(cache_key)
            if cached is not None:
                self._cache.move_to_end(cache_key)
                return cached

        log = _rollout_work_log(
            source,
            since,
            until,
            include_process,
            end=stable_end,
            chunk_size=self.chunk_size,
        )
        with self._cache_lock:
            self._cache[cache_key] = log
            self._cache.move_to_end(cache_key)
            while len(self._cache) > self.max_cache_entries:
                self._cache.popitem(last=False)
        return log

    @staticmethod
    def _error_log(thread_id: str, error: Exception) -> dict[str, Any]:
        return {
            "id": thread_id,
            "name": "Codex 对话",
            "preview": "",
            "turns": [],
            "error": str(error),
        }

    def work_logs(
        self,
        thread_ids: list[str],
        since: float | None,
        until: float | None,
        include_process: bool,
    ) -> list[dict[str, Any]]:
        ordered_ids = list(dict.fromkeys(thread_ids))[:MAX_REPORT_THREADS]
        if since is None:
            return self.fallback_bridge.work_logs(
                ordered_ids, since, until, include_process
            )
        try:
            sources = self.monitor.rollout_sources(ordered_ids)
        except CodexStateUnavailable:
            return self.fallback_bridge.work_logs(
                ordered_ids, since, until, include_process
            )

        cached_summaries_method = getattr(
            self.fallback_bridge, "cached_thread_summaries", None
        )
        cached_summaries = (
            cached_summaries_method(ordered_ids)
            if callable(cached_summaries_method)
            else {}
        )
        for source in sources:
            summary = cached_summaries.get(source.get("id"))
            if summary:
                source["name"] = summary.get("name") or source.get("name")
                source["preview"] = summary.get("preview") or source.get("preview")

        source_by_id = {source.get("id"): source for source in sources}
        direct_sources = [
            source_by_id[thread_id]
            for thread_id in ordered_ids
            if source_by_id.get(thread_id, {}).get("rolloutPath")
        ]
        results: dict[str, dict[str, Any]] = {}
        failed_ids = [
            thread_id
            for thread_id in ordered_ids
            if not source_by_id.get(thread_id, {}).get("rolloutPath")
        ]

        def read_one(source: dict[str, Any]) -> tuple[str, dict[str, Any] | Exception]:
            thread_id = str(source.get("id") or "")
            try:
                return thread_id, self._read_source(
                    source, since, until, include_process
                )
            except Exception as error:
                return thread_id, error

        if direct_sources:
            with concurrent.futures.ThreadPoolExecutor(
                max_workers=min(self.max_workers, len(direct_sources)),
                thread_name_prefix="codex-work-log",
            ) as executor:
                for thread_id, value in executor.map(read_one, direct_sources):
                    if isinstance(value, Exception):
                        failed_ids.append(thread_id)
                    else:
                        results[thread_id] = value

        if failed_ids:
            try:
                fallback_logs = self.fallback_bridge.work_logs(
                    failed_ids, since, until, include_process
                )
                results.update({str(log.get("id")): log for log in fallback_logs})
            except Exception as error:
                for thread_id in failed_ids:
                    results[thread_id] = self._error_log(thread_id, error)

        return [
            results.get(thread_id)
            or self._error_log(thread_id, RuntimeError("无法读取 Codex 对话"))
            for thread_id in ordered_ids
        ]


class CodexBridge:
    """Small serialized JSON-RPC client for the local Codex app-server."""

    def __init__(self, command: list[str] | None = None) -> None:
        self.command = list(command or ["codex", "app-server", "--stdio"])
        self._process: subprocess.Popen[bytes] | None = None
        self._request_id = 0
        self._lock = threading.RLock()
        self._status_cache: dict[str, dict[str, Any]] = {}
        self._thread_summaries: dict[str, dict[str, Any]] = {}

    def _stop(self) -> None:
        process = self._process
        self._process = None
        if process and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=1)

    def close(self) -> None:
        with self._lock:
            self._stop()

    def _send(self, message: dict[str, Any]) -> None:
        if not self._process or not self._process.stdin:
            raise RuntimeError("Codex 服务未启动")
        payload = (json.dumps(message, separators=(",", ":")) + "\n").encode("utf-8")
        self._process.stdin.write(payload)
        self._process.stdin.flush()

    def _read_response(self, request_id: int, timeout: float = 12) -> dict[str, Any]:
        if not self._process or not self._process.stdout:
            raise RuntimeError("Codex 服务未启动")

        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("Codex 响应超时")
            ready, _, _ = select.select([self._process.stdout], [], [], remaining)
            if not ready:
                raise TimeoutError("Codex 响应超时")
            line = self._process.stdout.readline()
            if not line:
                raise RuntimeError("Codex 服务已停止")
            payload = json.loads(line.decode("utf-8"))
            if payload.get("id") != request_id:
                continue
            if "error" in payload:
                message = payload["error"].get("message", "Codex 请求失败")
                raise RuntimeError(message)
            return payload.get("result", {})

    def _start(self) -> None:
        self._stop()
        try:
            self._process = subprocess.Popen(
                self.command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                bufsize=0,
            )
        except FileNotFoundError as error:
            raise RuntimeError("没有找到 Codex CLI") from error

        self._request_id += 1
        initialize_id = self._request_id
        self._send(
            {
                "id": initialize_id,
                "method": "initialize",
                "params": {
                    "clientInfo": {
                        "name": "reminder-cards",
                        "title": "Reminder Cards",
                        "version": "0.2.0",
                    },
                    "capabilities": {"experimentalApi": True},
                },
            }
        )
        self._read_response(initialize_id)
        self._send({"method": "initialized", "params": {}})

    def request(self, method: str, params: dict[str, Any], timeout: float = 12) -> dict[str, Any]:
        with self._lock:
            if not self._process or self._process.poll() is not None:
                self._start()
            self._request_id += 1
            request_id = self._request_id
            try:
                self._send({"id": request_id, "method": method, "params": params})
                return self._read_response(request_id, timeout=timeout)
            except Exception:
                self._stop()
                raise

    def list_threads(self, timeout: float = 12) -> list[dict[str, Any]]:
        result = self.request(
            "thread/list",
            {
                "limit": 100,
                "sortKey": "updated_at",
                "sortDirection": "desc",
                "sourceKinds": [],
                "useStateDbOnly": True,
            },
            timeout=timeout,
        )
        summaries = [self._thread_summary(thread) for thread in result.get("data", [])]
        with self._lock:
            self._thread_summaries = {
                summary["id"]: summary for summary in summaries if summary.get("id")
            }
        return summaries

    def cached_thread_summaries(
        self, thread_ids: list[str]
    ) -> dict[str, dict[str, Any]]:
        with self._lock:
            return {
                thread_id: dict(self._thread_summaries[thread_id])
                for thread_id in thread_ids
                if thread_id in self._thread_summaries
            }

    def thread_statuses(self, thread_ids: list[str]) -> list[dict[str, Any]]:
        with self._lock:
            summaries = {thread["id"]: thread for thread in self.list_threads()}
            statuses = []
            for thread_id in thread_ids[:50]:
                summary = summaries.get(thread_id)
                cached = self._status_cache.get(thread_id)
                if cached and (
                    not summary or cached.get("updatedAt") == summary.get("updatedAt")
                ):
                    statuses.append({**cached, **(summary or {})})
                    continue
                try:
                    result = self.request(
                        "thread/read",
                        {"threadId": thread_id, "includeTurns": True},
                    )
                    thread = result["thread"]
                    latest_turn = max(
                        (turn for turn in thread.get("turns", []) if isinstance(turn, dict)),
                        key=lambda turn: (turn.get("startedAt") or 0, turn.get("id") or ""),
                        default=None,
                    )
                    completed_turns = [
                        turn for turn in thread.get("turns", []) if turn.get("status") == "completed"
                    ]
                    latest = max(
                        completed_turns,
                        key=lambda turn: (turn.get("completedAt") or 0, turn.get("id") or ""),
                        default=None,
                    )
                    status = self._thread_summary(thread)
                    active = bool(latest_turn and latest_turn.get("status") == "inProgress")
                    status.update(
                        {
                            "exists": True,
                            "status": "active" if active else status.get("status", "unknown"),
                            "phase": "reasoning" if active else "idle",
                            "phaseLabel": "推理中" if active else "保持关注",
                            "activityStartedAt": latest_turn.get("startedAt") if active else None,
                            "toolKind": "",
                            "latestCompletedTurnId": latest.get("id") if latest else None,
                            "latestCompletedAt": latest.get("completedAt") if latest else None,
                        }
                    )
                    self._status_cache[thread_id] = status
                    statuses.append(status)
                except Exception as error:
                    statuses.append(
                        {
                            "id": thread_id,
                            "exists": False,
                            "error": str(error),
                        }
                    )
            return statuses

    def work_logs(
        self,
        thread_ids: list[str],
        since: float | None,
        until: float | None,
        include_process: bool,
    ) -> list[dict[str, Any]]:
        logs: list[dict[str, Any]] = []
        for thread_id in list(dict.fromkeys(thread_ids))[:MAX_REPORT_THREADS]:
            try:
                result = self.request(
                    "thread/read",
                    {"threadId": thread_id, "includeTurns": True},
                    timeout=30,
                )
                logs.append(_thread_work_log(result["thread"], since, until, include_process))
            except Exception as error:
                logs.append(
                    {
                        "id": thread_id,
                        "name": "Codex 对话",
                        "preview": "",
                        "turns": [],
                        "error": str(error),
                    }
                )
        return logs

    @staticmethod
    def _thread_summary(thread: dict[str, Any]) -> dict[str, Any]:
        status = thread.get("status") or {}
        return {
            "id": thread.get("id"),
            "name": thread.get("name") or thread.get("preview") or "未命名对话",
            "preview": thread.get("preview") or "",
            "updatedAt": thread.get("updatedAt"),
            "status": status.get("type", "unknown") if isinstance(status, dict) else "unknown",
            "model": thread.get("model") or "",
            "reasoningEffort": thread.get("reasoningEffort") or thread.get("effort") or "",
            "cwd": thread.get("cwd") or "",
        }


CODEX_BRIDGE = CodexBridge()
CODEX_MONITOR = CodexRolloutMonitor(CODEX_HOME)
CODEX_WORK_LOGS = CodexWorkLogReader(CODEX_MONITOR, CODEX_BRIDGE)


def _load_remote_codex_specs() -> list[dict[str, str]]:
    config_path = Path(
        os.environ.get("LUMEN_CODEX_REMOTE_CONFIG", APP_DIRECTORY / "private" / "codex-remotes.json")
    )
    try:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, UnicodeDecodeError, OSError):
        return []
    specs = payload.get("hosts") if isinstance(payload, dict) else None
    if not isinstance(specs, list):
        return []
    valid: list[dict[str, str]] = []
    for item in specs:
        if not isinstance(item, dict):
            continue
        host_id = str(item.get("id") or "").strip()
        ssh_host = str(item.get("sshHost") or "").strip()
        ssh_user = str(item.get("sshUser") or "").strip()
        codex_path = str(item.get("codexPath") or "codex").strip()
        label = str(item.get("label") or ssh_host).strip()
        if not re.fullmatch(r"ssh-[A-Za-z0-9][A-Za-z0-9._-]{0,63}", host_id):
            continue
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", ssh_host):
            continue
        if ssh_user and not re.fullmatch(r"[A-Za-z0-9._-]{1,64}", ssh_user):
            continue
        if codex_path != "codex" and not re.fullmatch(r"/[A-Za-z0-9._/-]{1,200}", codex_path):
            continue
        if not label:
            label = ssh_host
        valid.append({"id": host_id, "sshHost": ssh_host, "sshUser": ssh_user, "codexPath": codex_path, "label": label[:80]})
    return valid


REMOTE_CODEX_SPECS = _load_remote_codex_specs()
REMOTE_CODEX_BRIDGES: dict[str, CodexBridge] = {
    spec["id"]: CodexBridge(
        [
            "ssh",
            "-T",
            "-o",
            "BatchMode=yes",
            "-o",
            "ConnectTimeout=5",
            "-o",
            "ServerAliveInterval=15",
            "-o",
            "ServerAliveCountMax=2",
            "-l",
            spec["sshUser"],
            spec["sshHost"],
            spec["codexPath"],
            "app-server",
            "--stdio",
        ]
    )
    for spec in REMOTE_CODEX_SPECS
}
REMOTE_CODEX_LABELS = {spec["id"]: spec["label"] for spec in REMOTE_CODEX_SPECS}
FEISHU_NOTIFIER: FeishuNotifier | None = None


def get_feishu_notifier() -> FeishuNotifier:
    global FEISHU_NOTIFIER
    if FEISHU_NOTIFIER is None:
        FEISHU_NOTIFIER = FeishuNotifier()
    return FEISHU_NOTIFIER


class ReminderServer(http.server.ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True


class ReminderHandler(http.server.SimpleHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, directory=str(APP_DIRECTORY), **kwargs)

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        super().end_headers()

    def _local_host(self) -> bool:
        try:
            host = urllib.parse.urlsplit("//" + self.headers.get("Host", "")).hostname
        except ValueError:
            host = None
        if host not in {"localhost", "127.0.0.1", "::1"}:
            self.send_error(403, "Local host required")
            return False
        return True

    def send_head(self):
        if not self._local_host():
            return None
        path = Path(self.translate_path(self.path)).resolve()
        root = APP_DIRECTORY.resolve()
        try:
            parts = path.relative_to(root).parts
        except ValueError:
            parts = ("private",)
        if not parts:
            path = root / "index.html"
            parts = ("index.html",)
        public_extensions = {".html", ".js", ".css", ".svg", ".png", ".jpg", ".jpeg", ".webp", ".ico", ".woff", ".woff2", ".md"}
        allowed = not any(part.startswith(".") for part in parts)
        allowed = allowed and (len(parts) == 1 or parts[0] in {"assets", "docs"})
        allowed = allowed and path.suffix.lower() in public_extensions and path.is_file()
        if not allowed:
            self.send_error(404, "Not found")
            return None
        return super().send_head()

    def _json_response(self, payload: dict[str, Any], status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json_request(self, max_bytes: int = 64 * 1024) -> dict[str, Any]:
        origin = self.headers.get("Origin")
        if origin and urllib.parse.urlsplit(origin).netloc.lower() != self.headers.get("Host", "").lower():
            raise PermissionError("不允许跨站写入")
        if self.headers.get("X-Lumen-Request") != "1":
            raise PermissionError("缺少本地请求标记")
        content_type = self.headers.get_content_type()
        if content_type != "application/json":
            raise ValueError("请求必须使用 JSON")
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError as error:
            raise ValueError("Content-Length 无效") from error
        if content_length <= 0 or content_length > max_bytes:
            raise ValueError("请求内容为空或过大")
        try:
            body = json.loads(self.rfile.read(content_length))
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            raise ValueError("JSON 内容无效") from error
        if not isinstance(body, dict):
            raise ValueError("JSON 顶层必须是对象")
        return body

    @staticmethod
    def _thread_refs(parsed: urllib.parse.ParseResult) -> list[dict[str, str]]:
        refs: list[dict[str, str]] = []
        seen: set[tuple[str, str]] = set()
        for raw_value in urllib.parse.parse_qs(parsed.query).get("id", []):
            value = str(raw_value or "").strip()
            if not value or len(value) > 256:
                continue
            if "::" in value:
                host_id, thread_id = value.split("::", 1)
                if host_id in REMOTE_CODEX_BRIDGES:
                    host = host_id
                else:
                    host, thread_id = "local", value
            else:
                host, thread_id = "local", value
            if not thread_id or len(thread_id) > 128 or (host, thread_id) in seen:
                continue
            seen.add((host, thread_id))
            refs.append({"hostId": host, "id": thread_id, "ref": value})
        return refs[:50]

    @staticmethod
    def _query_timestamp(
        parsed: urllib.parse.ParseResult, key: str
    ) -> float | None:
        values = urllib.parse.parse_qs(parsed.query).get(key, [])
        if not values:
            return None
        try:
            return _normalized_timestamp(float(values[0]))
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _query_bool(
        parsed: urllib.parse.ParseResult, key: str, default: bool = False
    ) -> bool:
        values = urllib.parse.parse_qs(parsed.query).get(key, [])
        if not values:
            return default
        return values[0].lower() in {"1", "true", "yes", "on"}

    def _list_codex_threads(self) -> list[dict[str, Any]]:
        threads: list[dict[str, Any]] = []
        try:
            local_threads = CODEX_BRIDGE.list_threads()
        except Exception:
            local_threads = CODEX_MONITOR.list_threads()
        for thread in local_threads:
            threads.append({**thread, "hostId": "local", "sourceLabel": "本机"})

        def read_remote(item: tuple[str, CodexBridge]) -> list[dict[str, Any]]:
            host_id, bridge = item
            try:
                return [
                    {**thread, "hostId": host_id, "sourceLabel": REMOTE_CODEX_LABELS.get(host_id, host_id)}
                    for thread in bridge.list_threads(timeout=8)
                ]
            except Exception:
                return []

        remote_items = list(REMOTE_CODEX_BRIDGES.items())
        if remote_items:
            with concurrent.futures.ThreadPoolExecutor(
                max_workers=len(remote_items), thread_name_prefix="codex-remote-list"
            ) as executor:
                for remote_threads in executor.map(read_remote, remote_items):
                    threads.extend(remote_threads)
        return threads

    def _codex_statuses(self, refs: list[dict[str, str]]) -> list[dict[str, Any]]:
        refs = [
            ref if isinstance(ref, dict) else {"hostId": "local", "id": str(ref), "ref": str(ref)}
            for ref in refs
        ]
        grouped: dict[str, list[str]] = {}
        for ref in refs:
            grouped.setdefault(ref["hostId"], []).append(ref["id"])
        statuses_by_key: dict[tuple[str, str], dict[str, Any]] = {}
        for host_id, thread_ids in grouped.items():
            bridge = CODEX_BRIDGE if host_id == "local" else REMOTE_CODEX_BRIDGES.get(host_id)
            if bridge is None:
                continue
            try:
                if host_id == "local":
                    statuses = CODEX_MONITOR.thread_statuses(thread_ids)
                else:
                    statuses = bridge.thread_statuses(thread_ids)
            except CodexStateUnavailable:
                statuses = bridge.thread_statuses(thread_ids)
            statuses = self._merge_codex_thread_metadata(bridge, thread_ids, statuses)
            for status in statuses:
                status["hostId"] = host_id
                status["sourceLabel"] = "本机" if host_id == "local" else REMOTE_CODEX_LABELS.get(host_id, host_id)
                statuses_by_key[(host_id, str(status.get("id") or ""))] = status
        return [statuses_by_key[key] for key in ((ref["hostId"], ref["id"]) for ref in refs) if key in statuses_by_key]

    def _codex_work_log(self, parsed: urllib.parse.ParseResult) -> None:
        refs = self._thread_refs(parsed)[:MAX_REPORT_THREADS]
        if not refs:
            self._json_response({"available": False, "error": "没有选择 Codex 对话"}, 400)
            return
        since = self._query_timestamp(parsed, "since")
        until = self._query_timestamp(parsed, "until")
        include_process = self._query_bool(parsed, "includeProcess", default=True)
        try:
            grouped: dict[str, list[str]] = {}
            for ref in refs:
                grouped.setdefault(ref["hostId"], []).append(ref["id"])
            grouped_logs: dict[tuple[str, str], dict[str, Any]] = {}
            for host_id, thread_ids in grouped.items():
                bridge = CODEX_BRIDGE if host_id == "local" else REMOTE_CODEX_BRIDGES.get(host_id)
                if bridge is None:
                    continue
                logs = (
                    CODEX_WORK_LOGS.work_logs(thread_ids, since, until, include_process)
                    if host_id == "local"
                    else bridge.work_logs(thread_ids, since, until, include_process)
                )
                for log in logs:
                    log["hostId"] = host_id
                    grouped_logs[(host_id, str(log.get("id") or ""))] = log
            logs = [grouped_logs[key] for key in ((ref["hostId"], ref["id"]) for ref in refs) if key in grouped_logs]
            self._json_response(
                {
                    "available": True,
                    "since": since,
                    "until": until,
                    "includeProcess": include_process,
                    "threads": logs,
                }
            )
        except Exception as error:
            self._json_response({"available": False, "error": str(error), "threads": []}, 503)

    @staticmethod
    def _merge_codex_thread_metadata(
        bridge: CodexBridge, thread_ids: list[str], statuses: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        summaries = bridge.cached_thread_summaries(thread_ids)
        merged: list[dict[str, Any]] = []
        for status in statuses:
            current = dict(status)
            summary = summaries.get(status.get("id"))
            if summary:
                current["name"] = summary.get("name") or current.get("name")
                current["preview"] = summary.get("preview") or current.get("preview", "")
            else:
                current.pop("name", None)
            merged.append(current)
        return merged

    def _write_sse(self, revision: int, statuses: list[dict[str, Any]]) -> None:
        payload = json.dumps(
            {"available": True, "threads": statuses},
            ensure_ascii=False,
            separators=(",", ":"),
        )
        self.wfile.write(f"id: {revision}\ndata: {payload}\n\n".encode("utf-8"))
        self.wfile.flush()

    def _codex_events(self, refs: list[dict[str, str]]) -> None:
        refs = [
            ref if isinstance(ref, dict) else {"hostId": "local", "id": str(ref), "ref": str(ref)}
            for ref in refs
        ]
        thread_ids = [ref["id"] for ref in refs if ref["hostId"] == "local"]
        if not thread_ids:
            self._json_response({"available": False, "error": "没有关联的 Codex 对话"}, 400)
            return
        try:
            statuses = CODEX_MONITOR.thread_statuses(thread_ids)
            statuses = self._merge_codex_thread_metadata(CODEX_BRIDGE, thread_ids, statuses)
        except CodexStateUnavailable as error:
            self._json_response({"available": False, "error": str(error)}, 503)
            return

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Connection", "keep-alive")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()
        revision = CODEX_MONITOR.revision
        try:
            self._write_sse(revision, statuses)
            while True:
                next_revision, statuses = CODEX_MONITOR.wait_for_change(
                    thread_ids,
                    after_revision=revision,
                    timeout=15,
                )
                if CODEX_MONITOR.stopped:
                    return
                if next_revision > revision:
                    revision = next_revision
                    statuses = self._merge_codex_thread_metadata(CODEX_BRIDGE, thread_ids, statuses)
                    self._write_sse(revision, statuses)
                else:
                    self.wfile.write(b": ping\n\n")
                    self.wfile.flush()
        except OSError:
            return

    def do_GET(self) -> None:
        if not self._local_host():
            return
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/state":
            try:
                store = get_business_store()
                revision = urllib.parse.parse_qs(parsed.query).get("revision", [None])[0]
                current = store.revision()
                self._json_response({"unchanged": True, "revision": current} if revision == str(current) else store.snapshot())
            except Exception:
                self._json_response({"error": "无法读取本地数据库"}, 503)
            return
        if parsed.path == "/api/codex/threads":
            try:
                self._json_response({"available": True, "threads": self._list_codex_threads()})
            except Exception as error:
                self._json_response({"available": False, "error": str(error), "threads": []}, 503)
            return

        if parsed.path == "/api/codex/status":
            refs = self._thread_refs(parsed)
            try:
                self._json_response(
                    {"available": True, "threads": self._codex_statuses(refs)}
                )
            except Exception as error:
                self._json_response({"available": False, "error": str(error), "threads": []}, 503)
            return

        if parsed.path == "/api/codex/events":
            self._codex_events(self._thread_refs(parsed))
            return

        if parsed.path == "/api/codex/work-log":
            self._codex_work_log(parsed)
            return

        if parsed.path == "/api/feishu/status":
            self._json_response(get_feishu_notifier().status())
            return

        super().do_GET()

    def do_POST(self) -> None:
        if not self._local_host():
            return
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path in {"/api/state", "/api/state/import"}:
            try:
                body = self._json_request(max_bytes=32 * 1024 * 1024)
                store = get_business_store()
                result = store.initialize(body.get("data"), "browser") if parsed.path.endswith("/import") else store.update(body.get("updates"))
                self._json_response(result)
            except StateConflict as error:
                self._json_response({"error": str(error)}, 409)
            except PermissionError as error:
                self._json_response({"error": str(error)}, 403)
            except (ValueError, TypeError) as error:
                self._json_response({"error": str(error)}, 400)
            except Exception:
                self._json_response({"error": "本地数据库保存失败"}, 503)
            return
        if parsed.path == "/api/widget/snapshot":
            try:
                snapshot = WIDGET_STORE.save_snapshot(self._json_request(max_bytes=32 * 1024))
                self._json_response(
                    {
                        "available": True,
                        "date": snapshot["date"],
                        "updatedAt": snapshot["updatedAt"],
                    }
                )
            except PermissionError as error:
                self._json_response({"available": False, "error": str(error)}, 403)
            except ValueError as error:
                self._json_response({"available": False, "error": str(error)}, 400)
            except Exception as error:
                self._json_response({"available": False, "error": str(error)}, 500)
            return
        if not parsed.path.startswith("/api/feishu/"):
            self._json_response({"available": False, "error": "接口不存在"}, 404)
            return
        try:
            body = self._json_request()
            notifier = get_feishu_notifier()
            if parsed.path == "/api/feishu/settings":
                self._json_response(notifier.update_settings(body))
                return
            if parsed.path == "/api/feishu/test":
                self._json_response({"available": True, **notifier.test()})
                return
            if parsed.path == "/api/feishu/events":
                result = notifier.enqueue(
                    str(body.get("eventId") or ""),
                    str(body.get("eventType") or ""),
                    body.get("data") if isinstance(body.get("data"), dict) else {},
                )
                self._json_response({"available": True, **result}, 202 if result.get("accepted") else 200)
                return
            self._json_response({"available": False, "error": "接口不存在"}, 404)
        except PermissionError as error:
            self._json_response({"available": False, "error": str(error)}, 403)
        except ValueError as error:
            self._json_response({"available": False, "error": str(error)}, 400)
        except FeishuNotificationError as error:
            self._json_response({"available": False, "error": str(error)}, 502)
        except Exception as error:
            self._json_response({"available": False, "error": str(error)}, 500)


def available_port(preferred: int = 8765) -> int:
    with contextlib.closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind(("127.0.0.1", preferred))
            return preferred
        except OSError:
            probe.bind(("127.0.0.1", 0))
            return int(probe.getsockname()[1])


def main() -> None:
    port = available_port()
    server = ReminderServer(("127.0.0.1", port), ReminderHandler)
    try:
        widget_port = int(os.environ.get("LUMEN_WIDGET_PORT", "8003"))
    except ValueError as error:
        raise RuntimeError("LUMEN_WIDGET_PORT 必须是端口号") from error
    widget_server = create_widget_server(
        "127.0.0.1",
        widget_port,
        store=WIDGET_STORE,
        script_path=WIDGET_SCRIPT_PATH,
    )
    widget_thread = threading.Thread(
        target=widget_server.serve_forever,
        name="lumen-widget-summary",
        daemon=True,
    )
    url = f"http://127.0.0.1:{port}/"

    print(f"微光提醒已启动：{url}")
    print(f"iPhone 小组件摘要已启动：http://127.0.0.1:{widget_port}/api/today")
    print("关闭这个窗口即可停止。")
    CODEX_MONITOR.start()
    get_feishu_notifier().start()
    widget_thread.start()
    threading.Timer(0.5, lambda: webbrowser.open(url)).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        widget_server.shutdown()
        widget_server.server_close()
        widget_thread.join(timeout=3)
        CODEX_MONITOR.close()
        CODEX_BRIDGE.close()
        for bridge in REMOTE_CODEX_BRIDGES.values():
            bridge.close()
        get_feishu_notifier().close()
        server.server_close()


if __name__ == "__main__":
    main()
