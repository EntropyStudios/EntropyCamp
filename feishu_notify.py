#!/usr/bin/env python3
"""Reliable outbound Feishu notifications for the local reminder app."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import sqlite3
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable


FEISHU_EVENT_DEFAULTS = {
    "codex_completed": True,
    "work_ended": True,
    "work_started": False,
    "reminder_due": False,
    "card_read": False,
}
FEISHU_EVENT_TYPES = frozenset(FEISHU_EVENT_DEFAULTS)
RETRY_DELAYS = (5, 30, 120, 600, 1800, 3600, 10800, 21600)
MAX_VALUE_LENGTH = 1600


class FeishuNotificationError(RuntimeError):
    def __init__(self, message: str, *, retryable: bool = True) -> None:
        super().__init__(message)
        self.retryable = retryable


def feishu_signature(secret: str, timestamp: int) -> str:
    string_to_sign = f"{timestamp}\n{secret}".encode("utf-8")
    digest = hmac.new(string_to_sign, digestmod=hashlib.sha256).digest()
    return base64.b64encode(digest).decode("ascii")


def _clean_text(value: Any, limit: int = MAX_VALUE_LENGTH) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()[:limit]


def _format_message(event_type: str, data: dict[str, Any]) -> dict[str, Any]:
    title = "微光提醒"
    lines: list[str] = []
    if event_type == "codex_completed":
        title = "Codex 任务已完成"
        lines.append(f"任务：{_clean_text(data.get('cardTitle'), 80) or 'Codex 对话'}")
        thread_name = _clean_text(data.get("threadName"), 120)
        if thread_name and thread_name != lines[0][3:]:
            lines.append(f"对话：{thread_name}")
        count = max(0, int(data.get("completionCount") or 0))
        lines.append(f"本班已完成：{count} 次")
    elif event_type == "work_ended":
        title = "今日工作已收尾"
        lines.extend(
            [
                f"工作时长：{_clean_text(data.get('duration'), 40) or '--'}",
                f"完成对话：{max(0, int(data.get('completionCount') or 0))} 次",
            ]
        )
        mood = _clean_text(data.get("moodLabel"), 30)
        note = _clean_text(data.get("note"), 500)
        if mood:
            lines.append(f"今日状态：{mood}")
        if note:
            lines.append(f"想法：{note}")
    elif event_type == "work_started":
        title = "已开始工作"
        lines.append("提醒与对话计数已经恢复。")
    elif event_type == "reminder_due":
        title = "提醒时间到了"
        lines.append(f"提醒：{_clean_text(data.get('cardTitle'), 80) or '未命名提醒'}")
    elif event_type == "card_read":
        title = "提醒已处理"
        lines.append(f"提醒：{_clean_text(data.get('cardTitle'), 80) or '未命名提醒'}")
    else:
        raise ValueError("不支持的飞书事件类型")

    occurred_at = _clean_text(data.get("occurredAtLabel"), 40)
    if occurred_at:
        lines.append(f"时间：{occurred_at}")
    return {
        "msg_type": "post",
        "content": {
            "post": {
                "zh_cn": {
                    "title": title,
                    "content": [[{"tag": "text", "text": line}] for line in lines],
                }
            }
        },
    }


def send_feishu_webhook(
    webhook: str,
    secret: str,
    message: dict[str, Any],
    *,
    timeout: float = 8.0,
    now: Callable[[], float] = time.time,
) -> None:
    timestamp = int(now())
    body = dict(message)
    if secret:
        body["timestamp"] = str(timestamp)
        body["sign"] = feishu_signature(secret, timestamp)
    request = urllib.request.Request(
        webhook,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            response_body = response.read(128 * 1024)
            status = response.status
    except urllib.error.HTTPError as error:
        retryable = error.code == 429 or error.code >= 500
        raise FeishuNotificationError(
            f"飞书返回 HTTP {error.code}", retryable=retryable
        ) from error
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        raise FeishuNotificationError(f"连接飞书失败：{error}") from error

    if status < 200 or status >= 300:
        raise FeishuNotificationError(f"飞书返回 HTTP {status}", retryable=status >= 500)
    try:
        result = json.loads(response_body or b"{}")
    except json.JSONDecodeError as error:
        raise FeishuNotificationError("飞书返回了无法解析的响应") from error
    code = result.get("code", result.get("StatusCode", 0))
    if code not in (0, "0", None):
        message_text = result.get("msg") or result.get("StatusMessage") or f"错误码 {code}"
        retryable = str(code) in {"11232", "99991663"}
        raise FeishuNotificationError(f"飞书拒绝消息：{message_text}", retryable=retryable)


class FeishuNotifier:
    def __init__(
        self,
        *,
        data_directory: Path | None = None,
        transport: Callable[[str, str, dict[str, Any]], None] | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        root = data_directory or Path(
            os.environ.get(
                "LUMEN_REMINDER_DATA_DIR",
                Path.home() / ".local" / "share" / "lumen-reminder",
            )
        )
        self.data_directory = Path(root)
        self.config_path = self.data_directory / "feishu.json"
        self.database_path = self.data_directory / "feishu-outbox.sqlite3"
        self.transport = transport or send_feishu_webhook
        self.clock = clock
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._worker: threading.Thread | None = None
        self.data_directory.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self.data_directory, 0o700)
        except OSError:
            pass
        self._initialize_database()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=5)
        connection.row_factory = sqlite3.Row
        self._protect_database_files()
        return connection

    def _protect_database_files(self) -> None:
        for path in (
            self.database_path,
            self.database_path.with_name(self.database_path.name + "-wal"),
            self.database_path.with_name(self.database_path.name + "-shm"),
        ):
            try:
                os.chmod(path, 0o600)
            except OSError:
                pass

    def _initialize_database(self) -> None:
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS notifications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT NOT NULL UNIQUE,
                    event_type TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    attempts INTEGER NOT NULL DEFAULT 0,
                    next_attempt REAL NOT NULL DEFAULT 0,
                    created_at REAL NOT NULL,
                    sent_at REAL,
                    last_error TEXT NOT NULL DEFAULT ''
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS notifications_due ON notifications(status, next_attempt)"
            )
            connection.execute(
                "DELETE FROM notifications WHERE status IN ('sent', 'cancelled') AND created_at < ?",
                (self.clock() - 90 * 24 * 60 * 60,),
            )
        self._protect_database_files()

    def _default_config(self) -> dict[str, Any]:
        return {
            "enabled": False,
            "webhook": "",
            "secret": "",
            "events": dict(FEISHU_EVENT_DEFAULTS),
        }

    def _load_config(self) -> dict[str, Any]:
        config = self._default_config()
        try:
            stored = json.loads(self.config_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return config
        if not isinstance(stored, dict):
            return config
        config["enabled"] = stored.get("enabled") is True
        config["webhook"] = _clean_text(stored.get("webhook"), 1000)
        config["secret"] = _clean_text(stored.get("secret"), 500)
        stored_events = stored.get("events") if isinstance(stored.get("events"), dict) else {}
        config["events"] = {
            event_type: stored_events.get(event_type, default) is True
            for event_type, default in FEISHU_EVENT_DEFAULTS.items()
        }
        return config

    def _save_config(self, config: dict[str, Any]) -> None:
        temporary = self.config_path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        os.chmod(temporary, 0o600)
        temporary.replace(self.config_path)
        os.chmod(self.config_path, 0o600)

    @staticmethod
    def _valid_webhook(value: str) -> bool:
        return value.startswith("https://open.feishu.cn/open-apis/bot/v2/hook/")

    def update_settings(self, updates: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            config = self._load_config()
            webhook = _clean_text(updates.get("webhook"), 1000)
            secret = _clean_text(updates.get("secret"), 500)
            if webhook:
                if not self._valid_webhook(webhook):
                    raise ValueError("Webhook 地址不是飞书 V2 自定义机器人地址")
                config["webhook"] = webhook
            if secret:
                config["secret"] = secret
            events = updates.get("events")
            if isinstance(events, dict):
                for event_type in FEISHU_EVENT_TYPES:
                    if event_type in events:
                        config["events"][event_type] = events[event_type] is True
            requested_enabled = updates.get("enabled")
            if requested_enabled is not None:
                enabled = requested_enabled is True
                if enabled and not config["webhook"]:
                    raise ValueError("请先保存 Webhook 地址")
                config["enabled"] = enabled
                if not enabled:
                    with self._connect() as connection:
                        connection.execute(
                            "UPDATE notifications SET status='cancelled' WHERE status='pending'"
                        )
            self._save_config(config)
            self._wake.set()
            return self.status()

    def status(self) -> dict[str, Any]:
        with self._lock:
            config = self._load_config()
            with self._connect() as connection:
                pending = connection.execute(
                    "SELECT COUNT(*) FROM notifications WHERE status='pending'"
                ).fetchone()[0]
                last_sent = connection.execute(
                    "SELECT sent_at FROM notifications WHERE status='sent' ORDER BY sent_at DESC LIMIT 1"
                ).fetchone()
                last_failed = connection.execute(
                    """SELECT last_error, created_at FROM notifications
                       WHERE last_error != '' ORDER BY id DESC LIMIT 1"""
                ).fetchone()
            return {
                "available": True,
                "configured": bool(config["webhook"]),
                "hasSecret": bool(config["secret"]),
                "enabled": config["enabled"],
                "events": config["events"],
                "pending": pending,
                "lastSentAt": last_sent[0] if last_sent else None,
                "lastError": last_failed[0] if last_failed else "",
                "lastErrorAt": last_failed[1] if last_failed else None,
            }

    def test(self) -> dict[str, Any]:
        with self._lock:
            config = self._load_config()
        if not config["webhook"]:
            raise ValueError("请先保存 Webhook 地址")
        message = {
            "msg_type": "post",
            "content": {
                "post": {
                    "zh_cn": {
                        "title": "微光提醒连接成功",
                        "content": [
                            [{"tag": "text", "text": "这是一条来自本地工作台的测试消息。"}],
                            [{"tag": "text", "text": "之后的任务完成和下班总结会发送到这里。"}],
                        ],
                    }
                }
            },
        }
        self.transport(config["webhook"], config["secret"], message)
        with self._connect() as connection:
            connection.execute("UPDATE notifications SET last_error='' WHERE last_error != ''")
        return {"sent": True, "message": "测试消息已发送"}

    def enqueue(self, event_id: str, event_type: str, data: dict[str, Any]) -> dict[str, Any]:
        event_id = _clean_text(event_id, 240)
        if not event_id or event_type not in FEISHU_EVENT_TYPES or not isinstance(data, dict):
            raise ValueError("飞书事件参数无效")
        with self._lock:
            config = self._load_config()
            if not config["enabled"]:
                return {"accepted": False, "reason": "disabled"}
            if not config["events"].get(event_type, False):
                return {"accepted": False, "reason": "event_disabled"}
            payload = _format_message(event_type, data)
            try:
                with self._connect() as connection:
                    connection.execute(
                        """INSERT INTO notifications
                           (event_id, event_type, payload, status, next_attempt, created_at)
                           VALUES (?, ?, ?, 'pending', ?, ?)""",
                        (
                            event_id,
                            event_type,
                            json.dumps(payload, ensure_ascii=False),
                            self.clock(),
                            self.clock(),
                        ),
                    )
            except sqlite3.IntegrityError:
                return {"accepted": False, "reason": "duplicate"}
        self._wake.set()
        return {"accepted": True}

    def start(self) -> None:
        if self._worker and self._worker.is_alive():
            return
        self._stop.clear()
        self._worker = threading.Thread(
            target=self._run, name="feishu-notifier", daemon=True
        )
        self._worker.start()

    def close(self) -> None:
        self._stop.set()
        self._wake.set()
        if self._worker and self._worker.is_alive():
            self._worker.join(timeout=3)

    def _next_pending(self) -> sqlite3.Row | None:
        with self._connect() as connection:
            return connection.execute(
                """SELECT * FROM notifications
                   WHERE status='pending' AND next_attempt <= ?
                   ORDER BY id LIMIT 1""",
                (self.clock(),),
            ).fetchone()

    def _deliver(self, row: sqlite3.Row) -> None:
        with self._lock:
            config = self._load_config()
        if not config["enabled"] or not config["webhook"]:
            return
        try:
            payload = json.loads(row["payload"])
            self.transport(config["webhook"], config["secret"], payload)
        except FeishuNotificationError as error:
            attempts = int(row["attempts"]) + 1
            if error.retryable and attempts <= len(RETRY_DELAYS):
                status = "pending"
                next_attempt = self.clock() + RETRY_DELAYS[attempts - 1]
            else:
                status = "failed"
                next_attempt = self.clock()
            with self._connect() as connection:
                connection.execute(
                    """UPDATE notifications
                       SET status=?, attempts=?, next_attempt=?, last_error=? WHERE id=?""",
                    (status, attempts, next_attempt, str(error)[:500], row["id"]),
                )
            return
        except Exception as error:
            attempts = int(row["attempts"]) + 1
            status = "pending" if attempts <= len(RETRY_DELAYS) else "failed"
            delay = RETRY_DELAYS[min(attempts, len(RETRY_DELAYS)) - 1]
            with self._connect() as connection:
                connection.execute(
                    """UPDATE notifications
                       SET status=?, attempts=?, next_attempt=?, last_error=? WHERE id=?""",
                    (status, attempts, self.clock() + delay, str(error)[:500], row["id"]),
                )
            return
        with self._connect() as connection:
            connection.execute(
                "UPDATE notifications SET last_error='' WHERE last_error != ''"
            )
            connection.execute(
                """UPDATE notifications
                   SET status='sent', sent_at=?, last_error='' WHERE id=?""",
                (self.clock(), row["id"]),
            )

    def _run(self) -> None:
        while not self._stop.is_set():
            with self._lock:
                enabled = self._load_config()["enabled"]
            if not enabled:
                self._wake.wait(timeout=5)
                self._wake.clear()
                continue
            row = self._next_pending()
            if row is None:
                self._wake.wait(timeout=5)
                self._wake.clear()
                continue
            self._deliver(row)
