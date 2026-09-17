"""Minimal authenticated read-only service for the iPhone widget."""

from __future__ import annotations

import hmac
import hashlib
import http.server
import json
import math
import os
import secrets
import tempfile
import threading
import urllib.parse
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


BEIJING = ZoneInfo("Asia/Shanghai")
ALLOWED_REMINDER_STATES = {
    "due",
    "processing",
    "countdown",
    "attention",
    "idle",
    "paused",
}


def _now_beijing() -> datetime:
    return datetime.now(BEIJING)


def _clean_text(value: Any, max_length: int) -> str:
    return str(value or "").strip()[:max_length]


def _finite_number(value: Any, default: float = 0) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return default
    number = float(value)
    return number if math.isfinite(number) else default


def ensure_widget_token(path: Path) -> str:
    """Create a stable 32-byte token without printing or rotating it."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        token = path.read_text(encoding="utf-8").strip()
        if not token:
            raise RuntimeError("小组件令牌文件为空，请删除后重新生成")
        os.chmod(path, 0o600)
        return token
    except FileNotFoundError:
        token = secrets.token_urlsafe(32)
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as file:
            file.write(f"{token}\n")
        return token


class WidgetSnapshotStore:
    """Persist only the small projection that may leave this computer."""

    def __init__(self, directory: Path, *, token_path: Path | None = None) -> None:
        self.directory = Path(directory)
        self.snapshot_path = self.directory / "today.json"
        self.token_path = Path(token_path) if token_path else self.directory / "access-token"
        self.sources_directory = self.directory / "sources"
        self.preferred_source_path = self.directory / "preferred-source"
        self._lock = threading.RLock()

    def token(self) -> str:
        return ensure_widget_token(self.token_path)

    def _write_private_json(self, path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        descriptor, temporary_name = tempfile.mkstemp(prefix=f"{path.stem}-", suffix=".tmp", dir=path.parent)
        temporary = Path(temporary_name)
        try:
            os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as file:
                json.dump(payload, file, ensure_ascii=False, separators=(",", ":"))
                file.write("\n")
                file.flush()
                os.fsync(file.fileno())
            os.replace(temporary, path)
            os.chmod(path, 0o600)
        finally:
            if temporary.exists():
                temporary.unlink()

    def _preferred_source(self) -> str:
        try:
            return self.preferred_source_path.read_text(encoding="utf-8").strip()
        except OSError:
            return ""

    def _write_preferred_source(self, source_id: str) -> None:
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        descriptor, temporary_name = tempfile.mkstemp(prefix="preferred-", suffix=".tmp", dir=self.directory)
        temporary = Path(temporary_name)
        try:
            os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as file:
                file.write(f"{source_id}\n")
                file.flush()
                os.fsync(file.fileno())
            os.replace(temporary, self.preferred_source_path)
            os.chmod(self.preferred_source_path, 0o600)
        finally:
            if temporary.exists():
                temporary.unlink()

    def _source_path(self, source_id: str) -> Path:
        digest = hashlib.sha256(source_id.encode("utf-8")).hexdigest()
        return self.sources_directory / f"{digest}.json"

    def save_snapshot(self, payload: dict[str, Any], now: datetime | None = None) -> dict[str, Any]:
        current = (now or _now_beijing()).astimezone(BEIJING)
        source_id = _clean_text(payload.get("sourceId"), 128)
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", source_id):
            source_id = "legacy"
        work_source = payload.get("work") if isinstance(payload.get("work"), dict) else {}
        started_at = max(0, int(_finite_number(work_source.get("startedAt")))) or None
        ended_at = max(0, int(_finite_number(work_source.get("endedAt")))) or None
        duration_ms = int(max(0, min(7 * 24 * 60 * 60 * 1000, _finite_number(work_source.get("durationMs")))))
        completion_count = int(max(0, min(1_000_000, _finite_number(work_source.get("completionCount")))))
        active = work_source.get("active") is True
        if active:
            status = "working"
            status_label = "上班中"
        elif started_at:
            status = "finished"
            status_label = "已下班"
        else:
            status = "not-started"
            status_label = "未上班"

        reminders: list[dict[str, Any]] = []
        sources = payload.get("reminders") if isinstance(payload.get("reminders"), list) else []
        for source in sources[:4]:
            if not isinstance(source, dict):
                continue
            title = _clean_text(source.get("title"), 120)
            if not title:
                continue
            state = source.get("state")
            if state not in ALLOWED_REMINDER_STATES:
                state = "idle"
            due_at_value = _finite_number(source.get("dueAt"), -1)
            reminders.append(
                {
                    "title": title,
                    "tag": _clean_text(source.get("tag"), 32),
                    "state": state,
                    "dueAt": int(due_at_value) if due_at_value >= 0 else None,
                }
            )

        quote_source = payload.get("quote") if isinstance(payload.get("quote"), dict) else {}
        quote_text = _clean_text(quote_source.get("text"), 80)
        quote = {
            "text": quote_text,
            "source": _clean_text(quote_source.get("source"), 40),
        } if quote_text else None
        weather_source = payload.get("weather") if isinstance(payload.get("weather"), dict) else {}
        weather_type = _clean_text(weather_source.get("type"), 24)
        weather = None
        if weather_type:
            weather = {
                "location": _clean_text(weather_source.get("location"), 24),
                "type": weather_type,
                "current": round(_finite_number(weather_source.get("current")), 1),
                "min": round(_finite_number(weather_source.get("min")), 1),
                "max": round(_finite_number(weather_source.get("max")), 1),
                "rain": int(max(0, min(100, _finite_number(weather_source.get("rain"))))),
            }

        snapshot = {
            "version": 1,
            "date": current.strftime("%Y-%m-%d"),
            "updatedAt": current.isoformat(timespec="seconds"),
            "work": {
                "status": status,
                "statusLabel": status_label,
                "active": active,
                "startedAt": started_at,
                "endedAt": ended_at,
                "durationMs": duration_ms,
                "completionCount": completion_count,
            },
            "reminders": reminders,
            "quote": quote,
            "weather": weather,
        }
        with self._lock:
            self._write_private_json(self._source_path(source_id), snapshot)
            preferred_source = self._preferred_source()
            if active or payload.get("claimSource") is True or not preferred_source:
                preferred_source = source_id
                self._write_preferred_source(source_id)
            if preferred_source == source_id:
                self._write_private_json(self.snapshot_path, snapshot)
        return snapshot

    @staticmethod
    def _empty_work() -> dict[str, Any]:
        return {
            "status": "not-started",
            "statusLabel": "等待主页同步",
            "active": False,
            "startedAt": None,
            "endedAt": None,
            "durationMs": 0,
            "completionCount": 0,
        }

    def summary(self, now: datetime | None = None) -> dict[str, Any]:
        current = (now or _now_beijing()).astimezone(BEIJING)
        today = current.strftime("%Y-%m-%d")
        with self._lock:
            try:
                preferred_source = self._preferred_source()
                source_path = self._source_path(preferred_source) if preferred_source else self.snapshot_path
                snapshot = json.loads(source_path.read_text(encoding="utf-8"))
            except (FileNotFoundError, json.JSONDecodeError, UnicodeDecodeError):
                try:
                    snapshot = json.loads(self.snapshot_path.read_text(encoding="utf-8"))
                except (FileNotFoundError, json.JSONDecodeError, UnicodeDecodeError):
                    snapshot = {}
            active_snapshots: list[dict[str, Any]] = []
            for candidate_path in self.sources_directory.glob("*.json"):
                try:
                    candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError, UnicodeDecodeError):
                    continue
                if candidate.get("date") != today:
                    continue
                if (candidate.get("work") or {}).get("active") is True:
                    active_snapshots.append(candidate)
            if active_snapshots:
                snapshot = max(active_snapshots, key=lambda item: str(item.get("updatedAt") or ""))
        same_day = snapshot.get("date") == today
        return {
            "ok": True,
            "date": today,
            "updatedAt": snapshot.get("updatedAt") if same_day else None,
            "generatedAt": current.isoformat(timespec="seconds"),
            "stale": not same_day,
            "work": snapshot.get("work") if same_day else self._empty_work(),
            "reminders": snapshot.get("reminders", []) if same_day else [],
            "quote": snapshot.get("quote") if same_day else None,
            "weather": snapshot.get("weather") if same_day else None,
        }


class WidgetSummaryServer(http.server.ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(
        self,
        server_address: tuple[str, int],
        store: WidgetSnapshotStore,
        script_path: Path,
    ) -> None:
        self.widget_store = store
        self.widget_token = store.token()
        self.script_path = Path(script_path)
        self.widget_app = WidgetPublicApp(store, self.widget_token, self.script_path)
        super().__init__(server_address, WidgetSummaryHandler)


@dataclass(frozen=True)
class WidgetResponse:
    status: int
    content_type: str
    body: bytes


class WidgetPublicApp:
    """Pure request router shared by the HTTP handler and unit tests."""

    def __init__(self, store: WidgetSnapshotStore, token: str, script_path: Path) -> None:
        self.store = store
        self.token = token
        self.script_path = Path(script_path)

    @staticmethod
    def _json(status: int, payload: dict[str, Any]) -> WidgetResponse:
        return WidgetResponse(
            status,
            "application/json; charset=utf-8",
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
        )

    def _authorized(self, authorization: str) -> bool:
        prefix = "Bearer "
        candidate = authorization[len(prefix) :] if authorization.startswith(prefix) else ""
        return len(candidate) == len(self.token) and hmac.compare_digest(candidate, self.token)

    def handle(self, method: str, target: str, authorization: str = "") -> WidgetResponse:
        if method != "GET":
            return self._json(404, {"ok": False, "error": "接口不存在"})
        path = urllib.parse.urlsplit(target).path
        if path == "/api/today":
            if not self._authorized(authorization):
                return self._json(401, {"ok": False, "error": "未授权"})
            return self._json(200, self.store.summary())
        if path == "/LumenToday.js":
            try:
                body = self.script_path.read_bytes()
            except OSError:
                return self._json(404, {"ok": False, "error": "脚本不存在"})
            return WidgetResponse(200, "text/javascript; charset=utf-8", body)
        return self._json(404, {"ok": False, "error": "接口不存在"})


class WidgetSummaryHandler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "LumenWidget/1.0"
    sys_version = ""

    @property
    def widget_server(self) -> WidgetSummaryServer:
        return self.server  # type: ignore[return-value]

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'none'")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, payload: dict[str, Any]) -> None:
        self._send(
            status,
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
            "application/json; charset=utf-8",
        )

    def do_GET(self) -> None:
        response = self.widget_server.widget_app.handle(
            "GET", self.path, self.headers.get("Authorization", "")
        )
        self._send(response.status, response.body, response.content_type)

    def do_POST(self) -> None:
        response = self.widget_server.widget_app.handle(
            "POST", self.path, self.headers.get("Authorization", "")
        )
        self._send(response.status, response.body, response.content_type)


def create_widget_server(
    host: str,
    port: int,
    *,
    store: WidgetSnapshotStore,
    script_path: Path,
) -> WidgetSummaryServer:
    if host not in {"127.0.0.1", "::1", "localhost"}:
        raise ValueError("小组件源服务只能绑定本机回环地址")
    return WidgetSummaryServer((host, port), store, script_path)
