"""Authoritative local business state, stored outside the HTTP document root."""

from __future__ import annotations

import copy
import contextlib
import json
import os
import sqlite3
import threading
from pathlib import Path
from typing import Any

CARDS = "lumen-reminder-cards-v1"
SESSION = "lumen-reminder-work-session-v1"
HISTORY = "lumen-reminder-work-history-v1"
CLIPBOARD = "lumen-multi-clipboard-v1"
DEFAULTS = {
    CARDS: [],
    SESSION: {"active": False, "startedAt": None, "endedAt": None, "countsByCardId": {}, "countedTurnIdsByCardId": {}},
    HISTORY: {"version": 2, "updatedAt": 0, "entries": []},
    CLIPBOARD: {"version": 1, "updatedAt": 0, "items": []},
}
MISSING = object()


class StateConflict(ValueError):
    pass


def _merge(base: Any, incoming: Any, current: Any, path: str = "") -> Any:
    if incoming == base:
        return current
    if current == base or current == incoming:
        return incoming
    if path.endswith(".updatedAt") and all(isinstance(value, (int, float)) for value in (incoming, current)):
        return max(incoming, current)
    if all(isinstance(value, dict) for value in (base, incoming, current)):
        result = {}
        for key in set(base) | set(incoming) | set(current):
            value = _merge(base.get(key, MISSING), incoming.get(key, MISSING), current.get(key, MISSING), f"{path}.{key}")
            if value is not MISSING:
                result[key] = value
        return result
    if all(isinstance(value, list) for value in (base, incoming, current)):
        if all(isinstance(row, dict) and isinstance(row.get("id"), str) for rows in (base, incoming, current) for row in rows):
            before, after, live = ({row["id"]: row for row in rows} for rows in (base, incoming, current))
            order = list(after) + [key for key in live if key not in after]
            result = []
            for key in order:
                value = _merge(before.get(key, MISSING), after.get(key, MISSING), live.get(key, MISSING), f"{path}.{key}")
                if value is not MISSING:
                    result.append(value)
            return result
    raise StateConflict(f"数据已在另一个页面更新：{path}")


def _validate(key: str, value: Any) -> None:
    if key not in DEFAULTS:
        raise ValueError("不支持的数据类型")
    json.dumps(value, ensure_ascii=False, allow_nan=False)
    if key == CARDS:
        rows = value
    elif key in {HISTORY, CLIPBOARD}:
        expected = 2 if key == HISTORY else 1
        if not isinstance(value, dict) or value.get("version") != expected:
            raise ValueError("不支持的数据版本")
        rows = value.get("entries" if key == HISTORY else "items")
    else:
        if not isinstance(value, dict) or not isinstance(value.get("active"), bool):
            raise ValueError("班次数据无效")
        for field in ("countsByCardId", "countedTurnIdsByCardId"):
            if not isinstance(value.get(field, {}), dict):
                raise ValueError("班次计数无效")
        return
    if not isinstance(rows, list):
        raise ValueError("记录列表无效")
    ids = [row.get("id") if isinstance(row, dict) else None for row in rows]
    if any(not isinstance(identifier, str) or not identifier for identifier in ids) or len(set(ids)) != len(ids):
        raise ValueError("记录 ID 缺失或重复")


class BusinessStateStore:
    def __init__(self, directory: Path | None = None):
        self.directory = Path(directory or os.environ.get("ENTROPYCAMP_DATA_DIR", Path.home() / ".local/share/entropycamp"))
        self.directory.mkdir(parents=True, exist_ok=True)
        os.chmod(self.directory, 0o700)
        self.path = self.directory / "state.sqlite3"
        self._lock = threading.RLock()
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("CREATE TABLE IF NOT EXISTS documents (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            connection.execute("CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            connection.execute("INSERT OR IGNORE INTO metadata VALUES ('revision', '0')")
        self._protect()

    def _protect(self):
        for path in (self.path, Path(str(self.path) + "-wal"), Path(str(self.path) + "-shm")):
            try:
                os.chmod(path, 0o600)
            except FileNotFoundError:
                pass

    @contextlib.contextmanager
    def _connect(self):
        connection = sqlite3.connect(self.path, timeout=10)
        connection.execute("PRAGMA synchronous=FULL")
        self._protect()
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    @staticmethod
    def _snapshot(connection):
        data = copy.deepcopy(DEFAULTS)
        data.update({key: json.loads(value) for key, value in connection.execute("SELECT key, value FROM documents")})
        metadata = dict(connection.execute("SELECT key, value FROM metadata"))
        return {"data": data, "revision": int(metadata.get("revision", 0)), "initialized": metadata.get("initialized") == "1"}

    def snapshot(self):
        with self._lock, self._connect() as connection:
            connection.execute("BEGIN")
            return self._snapshot(connection)

    def revision(self):
        with self._lock, self._connect() as connection:
            return int(connection.execute("SELECT value FROM metadata WHERE key='revision'").fetchone()[0])

    def initialize(self, values: dict, source: str = "browser"):
        if not isinstance(values, dict) or set(values) - set(DEFAULTS):
            raise ValueError("迁移数据类型无效")
        for key, value in values.items():
            _validate(key, value)
        with self._lock, self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            if self._snapshot(connection)["initialized"]:
                return {**self._snapshot(connection), "imported": False}
            for key, value in {**DEFAULTS, **values}.items():
                connection.execute("INSERT OR REPLACE INTO documents VALUES (?, ?)", (key, json.dumps(value, ensure_ascii=False)))
            connection.execute("INSERT OR REPLACE INTO metadata VALUES ('initialized', '1')")
            connection.execute("INSERT OR REPLACE INTO metadata VALUES ('source', ?)", (source[:200],))
            connection.execute("UPDATE metadata SET value='1' WHERE key='revision'")
            result = {**self._snapshot(connection), "imported": True}
        self._protect()
        return result

    def update(self, updates: dict):
        if not isinstance(updates, dict) or not updates or set(updates) - set(DEFAULTS):
            raise ValueError("更新数据类型无效")
        with self._lock, self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            snapshot = self._snapshot(connection)
            if not snapshot["initialized"]:
                raise StateConflict("请先完成旧数据迁移")
            for key, change in updates.items():
                if not isinstance(change, dict) or "base" not in change or "value" not in change:
                    raise ValueError("更新缺少原始版本")
                base, incoming, current = change["base"], change["value"], snapshot["data"][key]
                _validate(key, base)
                _validate(key, incoming)
                if key == SESSION and current.get("startedAt") != base.get("startedAt") and incoming != current:
                    raise StateConflict("班次已改变，请重新读取")
                merged = _merge(base, incoming, current, key)
                _validate(key, merged)
                connection.execute("UPDATE documents SET value=? WHERE key=?", (json.dumps(merged, ensure_ascii=False), key))
            connection.execute("UPDATE metadata SET value=CAST(value AS INTEGER)+1 WHERE key='revision'")
            result = self._snapshot(connection)
        self._protect()
        return result
