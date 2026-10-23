"""Read local Claude Code transcripts without launching or controlling Claude.

Public IDs are prefixed so persisted cards/history can use the existing thread
reference contract without collisions with Codex UUIDs. Subagent logs are not
listed as independent user conversations.
"""
from __future__ import annotations

import copy
import json
import re
import sqlite3
import threading
import time
from datetime import datetime
from pathlib import Path

PREFIX = "claude-"
SESSION = re.compile(r"^[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}$")


def is_claude(identifier):
    return isinstance(identifier, str) and identifier.startswith(PREFIX)


def timestamp(value):
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except (ValueError, TypeError):
        return None


class ClaudeSessions:
    def __init__(self, home, cloudcli_db=None):
        self.root = Path(home).expanduser() / "projects"
        self.lock = threading.RLock()
        self.paths = {}
        self.cache = {}
        self.scanned = 0
        self.cloudcli_db = Path(cloudcli_db) if cloudcli_db else Path.home() / ".cloudcli" / "auth.db"
        self.names = {}

    def _discover(self):
        if time.monotonic() - self.scanned < 3:
            return
        paths = {}
        if self.root.is_dir():
            for path in self.root.glob("*/*.jsonl"):
                if SESSION.fullmatch(path.stem) and path.is_file() and not path.is_symlink():
                    # Never follow a project symlink outside the transcript root.
                    if path.resolve().is_relative_to(self.root.resolve()):
                        paths[PREFIX + path.stem] = path
        self.paths = paths
        # Read only optional session names, never CloudCLI auth/account tables.
        self.names = {}
        if self.cloudcli_db.is_file():
            try:
                with sqlite3.connect(self.cloudcli_db.as_uri() + "?mode=ro", uri=True, timeout=1) as db:
                    for sid, name in db.execute("SELECT provider_session_id, custom_name FROM sessions WHERE provider='claude' AND custom_name IS NOT NULL ORDER BY updated_at"):
                        if isinstance(sid, str) and SESSION.fullmatch(sid) and isinstance(name, str) and name.strip():
                            self.names[PREFIX + sid] = name.strip()[:160]
            except sqlite3.Error:
                pass
        self.scanned = time.monotonic()

    @staticmethod
    def _empty(identifier):
        return {"id": identifier, "name": "Claude Code 对话", "preview": "", "provider": "claude",
                "hostId": "local", "sourceLabel": "Claude Code · 本机", "exists": False,
                "status": "unavailable", "model": "", "reasoningEffort": "", "cwd": "",
                "phase": "unavailable", "phaseLabel": "日志不可用", "activityStartedAt": None,
                "toolKind": "", "updatedAt": None, "latestCompletedTurnId": None,
                "latestCompletedAt": None, "turns": []}

    def _read(self, identifier):
        self._discover()
        path = self.paths.get(identifier)
        if path is None:
            return self._empty(identifier)
        try:
            stat = path.stat()
            signature = (stat.st_ino, stat.st_size, stat.st_mtime_ns)
            cached = self.cache.get(identifier)
            if cached and cached[0] == signature:
                if identifier in self.names:
                    cached[1]["name"] = self.names[identifier]
                return cached[1]
            # Append-only logs: consume complete new lines, retain a partial tail
            # for the next poll. Rebuild only after truncation/replacement.
            if cached and cached[0][0] == stat.st_ino and cached[2] <= stat.st_size and stat.st_size > cached[0][1]:
                result = cached[1]
                offset = cached[2]
                seen = cached[3]
            else:
                result = self._empty(identifier)
                result.update(exists=True, status="idle", phase="idle", phaseLabel="保持关注")
                offset, seen = 0, set()
            with path.open("rb") as handle:
                handle.seek(offset)
                while True:
                    line_start = handle.tell()
                    line = handle.readline()
                    if not line or not line.endswith(b"\n"):
                        offset = line_start
                        break
                    offset = handle.tell()
                    try:
                        row = json.loads(line)
                    except (ValueError, UnicodeDecodeError):
                        continue
                    if not isinstance(row, dict) or row.get("isSidechain"):
                        continue
                    uid = row.get("uuid")
                    if uid and uid in seen:
                        continue
                    if uid:
                        seen.add(uid)
                    self._apply(result, row)
            if identifier in self.names:
                result["name"] = self.names[identifier]
            self.cache[identifier] = (signature, result, offset, seen)
            return result
        except OSError:
            return self._empty(identifier)

    @staticmethod
    def _apply(result, row):
        kind = row.get("type")
        if kind == "custom-title" and isinstance(row.get("customTitle"), str):
            result["name"] = row["customTitle"][:160]
            result["customTitle"] = True
        when = timestamp(row.get("timestamp"))
        if when is None:
            return
        result["updatedAt"] = max(result.get("updatedAt") or 0, when)
        if row.get("cwd"):
            result["cwd"] = str(row["cwd"])
        message = row.get("message") if isinstance(row.get("message"), dict) else {}
        content = message.get("content")
        parts = [{"type": "text", "text": content}] if isinstance(content, str) else content if isinstance(content, list) else []
        texts = [p.get("text", "") for p in parts if isinstance(p, dict) and p.get("type") == "text"]
        turns = result["turns"]
        if kind == "user":
            # Tool results and injected system/compact messages are not prompts.
            if row.get("isMeta") or not texts or any(p.get("type") == "tool_result" for p in parts if isinstance(p, dict)):
                return
            prompt = "\n".join(texts)
            if prompt.startswith("[Request interrupted by user"):
                if turns and turns[-1]["status"] == "inProgress":
                    turns[-1]["status"] = "interrupted"
                result.update(status="idle", phase="idle", phaseLabel="已中断", toolKind="", activityStartedAt=None)
                return
            if prompt.startswith(("<local-command", "<command-name>", "<local-command-stdout>")):
                return
            if turns and turns[-1]["status"] == "inProgress":
                turns[-1]["status"] = "interrupted"
            turn = {"id": str(row.get("uuid") or f"prompt-{when}"), "startedAt": when,
                    "completedAt": None, "status": "inProgress", "items": [
                        {"role": "user", "phase": "user", "text": prompt}]}
            turns.append(turn)
            if not result["preview"]:
                result["preview"] = prompt[:160]
                if not result.get("customTitle"):
                    result["name"] = prompt.splitlines()[0][:100] or "Claude Code 对话"
            result.update(status="active", phase="reasoning", phaseLabel="处理中",
                          activityStartedAt=when, toolKind="")
        elif kind == "assistant" and turns:
            turn = turns[-1]
            if message.get("model") and not str(message["model"]).startswith("<"):
                result["model"] = message["model"]
            if isinstance(row.get("effort"), str):
                result["reasoningEffort"] = row["effort"]
            tools = [p for p in parts if isinstance(p, dict) and p.get("type") == "tool_use"]
            terminal = message.get("stop_reason") in {"end_turn", "stop_sequence"} and bool(texts) and not tools
            for text in texts:
                turn["items"].append({"role": "assistant", "phase": "final_answer" if terminal else "commentary", "text": text, "timestamp": when})
            for tool in tools:
                turn["items"].append({"role": "assistant", "phase": "tool", "text": "调用工具：" + str(tool.get("name") or "Tool"), "timestamp": when})
            if row.get("isApiErrorMessage"):
                turn["status"] = "failed"
                result.update(status="idle", phase="idle", phaseLabel="请求失败", toolKind="", activityStartedAt=None)
            elif terminal:
                turn.update(completedAt=when, status="completed")
                result.update(status="idle", phase="idle", phaseLabel="保持关注", toolKind="", activityStartedAt=None,
                              latestCompletedTurnId=turn["id"], latestCompletedAt=when)
            else:
                phase = "executing" if tools else "outputting" if texts else "reasoning"
                result.update(status="active", phase=phase, phaseLabel={"executing": "执行工具", "outputting": "AI 输出", "reasoning": "处理中"}[phase],
                              toolKind=str(tools[-1].get("name") or "") if tools else "")
        elif kind == "system" and row.get("subtype") in {"turn_duration", "stop_hook_summary"} and turns:
            # A summary alone is not proof of a successful final assistant answer.
            if turns[-1]["status"] != "completed":
                turns[-1]["status"] = "interrupted"
            result.update(status="idle", phase="idle", phaseLabel="保持关注", toolKind="", activityStartedAt=None)

    def list_threads(self):
        with self.lock:
            self._discover()
            rows = []
            for identifier in self.paths:
                row = self._read(identifier)
                if row["turns"]:
                    rows.append({k: v for k, v in row.items() if k not in {"turns", "customTitle"}})
            return sorted(rows, key=lambda r: r.get("updatedAt") or 0, reverse=True)[:200]

    def thread_statuses(self, identifiers):
        with self.lock:
            return [{k: v for k, v in self._read(i).items() if k not in {"turns", "customTitle"}} for i in identifiers]

    def work_logs(self, identifiers, since=None, until=None, include_process=True):
        with self.lock:
            logs = []
            for identifier in identifiers:
                row = self._read(identifier)
                turns = []
                for turn in row["turns"]:
                    end = turn.get("completedAt") or turn["startedAt"]
                    if since is not None and end < since:
                        continue
                    if until is not None and turn["startedAt"] > until:
                        continue
                    value = copy.deepcopy(turn)
                    value["items"] = [item for item in value["items"] if include_process or item["role"] == "user" or item["phase"] == "final_answer"]
                    if until is not None:
                        value["items"] = [item for item in value["items"] if item.get("timestamp", turn["startedAt"]) <= until]
                    if until is not None and end > until:
                        value.update(completedAt=None, status="inProgress")
                    turns.append(value)
                logs.append({"id": identifier, "name": row["name"], "hostId": "local", "provider": "claude",
                             "turns": turns, **({"error": "Claude Code 日志不可用"} if not row["exists"] else {})})
            return logs
