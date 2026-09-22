"""Server-side reminder and Codex completion detection.

The browser renders state, but autonomous events must keep working when the user
navigates to another EntropyCamp page or closes the browser entirely.
"""

from __future__ import annotations

import copy
import threading
import time
from datetime import datetime
from typing import Any, Callable
from zoneinfo import ZoneInfo

from state_store import BusinessStateStore, CARDS, SESSION, StateConflict


ACTIVE_CODEX_STATUSES = frozenset({"active", "inProgress", "running", "working"})
BEIJING = ZoneInfo("Asia/Shanghai")


def _thread_ref(host_id: Any, thread_id: Any) -> str:
    host = str(host_id or "local").strip()
    identifier = str(thread_id or "").strip()
    return f"{host}::{identifier}" if identifier and host != "local" else identifier


def _time_label(timestamp: float) -> str:
    moment = datetime.fromtimestamp(timestamp, BEIJING)
    return moment.strftime("%Y-%m-%d %H:%M 北京时间")


class BackgroundEventMonitor:
    """Reconcile autonomous events into shared state without a browser page."""

    def __init__(
        self,
        *,
        store: BusinessStateStore,
        status_provider: Callable[[list[dict[str, str]]], list[dict[str, Any]]],
        notifier: Any,
        clock: Callable[[], float] = time.time,
        poll_interval: float = 1.0,
    ) -> None:
        self.store = store
        self.status_provider = status_provider
        self.notifier = notifier
        self.clock = clock
        self.poll_interval = max(0.1, float(poll_interval))
        self._stop = threading.Event()
        self._worker: threading.Thread | None = None
        self._attempted_event_ids: set[str] = set()
        self._last_error = ""

    def start(self) -> None:
        if self._worker and self._worker.is_alive():
            return
        self._stop.clear()
        self._worker = threading.Thread(
            target=self._run,
            name="entropycamp-background-events",
            daemon=True,
        )
        self._worker.start()

    def close(self) -> None:
        self._stop.set()
        if self._worker and self._worker.is_alive():
            self._worker.join(timeout=max(3.0, self.poll_interval + 1.0))

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self.run_once()
                self._last_error = ""
            except Exception as error:
                message = f"{type(error).__name__}: {error}"
                if message != self._last_error:
                    print(f"EntropyCamp 后台提醒暂时不可用：{message}", flush=True)
                    self._last_error = message
            self._stop.wait(self.poll_interval)

    def run_once(self) -> None:
        for _attempt in range(3):
            snapshot = self.store.snapshot()
            if not snapshot.get("initialized"):
                return
            base_cards = snapshot["data"][CARDS]
            base_session = snapshot["data"][SESSION]
            cards = copy.deepcopy(base_cards)
            session = copy.deepcopy(base_session)
            refs = self._linked_refs(cards)
            statuses = self.status_provider(refs) if refs else []
            changed_cards, changed_session, events = self._reconcile(
                cards, session, statuses, self.clock()
            )
            updates = {}
            if changed_cards:
                updates[CARDS] = {"base": base_cards, "value": cards}
            if changed_session:
                updates[SESSION] = {"base": base_session, "value": session}
            if updates:
                try:
                    self.store.update(updates)
                except StateConflict:
                    continue
            self._enqueue(events)
            return

    @staticmethod
    def _linked_refs(cards: list[dict[str, Any]]) -> list[dict[str, str]]:
        refs: list[dict[str, str]] = []
        seen: set[str] = set()
        for card in cards:
            thread_id = str(card.get("codexThreadId") or "").strip()
            if not thread_id:
                continue
            host_id = str(card.get("codexHost") or "local").strip()
            ref = _thread_ref(host_id, thread_id)
            if ref in seen:
                continue
            seen.add(ref)
            refs.append({"hostId": host_id, "id": thread_id, "ref": ref})
        return refs

    def _reconcile(
        self,
        cards: list[dict[str, Any]],
        session: dict[str, Any],
        statuses: list[dict[str, Any]],
        now: float,
    ) -> tuple[bool, bool, list[tuple[str, str, dict[str, Any]]]]:
        active = session.get("active") is True
        now_ms = int(now * 1000)
        counts = session.setdefault("countsByCardId", {})
        baselines = session.setdefault("countedTurnIdsByCardId", {})
        status_by_ref = {
            _thread_ref(status.get("hostId"), status.get("id")): status
            for status in statuses
            if status.get("id")
        }
        cards_changed = False
        session_changed = False
        events: list[tuple[str, str, dict[str, Any]]] = []

        for card in cards:
            thread_id = str(card.get("codexThreadId") or "").strip()
            if not thread_id:
                if (
                    active
                    and card.get("started") is True
                    and isinstance(card.get("nextAt"), (int, float))
                    and card["nextAt"] <= now_ms
                ):
                    token = f"timer:{card['nextAt']}"
                    if card.get("visualShatteredToken") != token:
                        card["visualShatteredToken"] = token
                        cards_changed = True
                    events.append(
                        (
                            f"reminder:{card.get('id')}:{card['nextAt']}",
                            "reminder_due",
                            {
                                "cardTitle": card.get("title") or "未命名提醒",
                                "occurredAtLabel": _time_label(now),
                            },
                        )
                    )
                continue

            host_id = str(card.get("codexHost") or "local").strip()
            ref = _thread_ref(host_id, thread_id)
            status = status_by_ref.get(ref)
            if not status:
                continue

            fields = self._status_fields(card, status)
            for key, value in fields.items():
                if card.get(key) != value:
                    card[key] = value
                    cards_changed = True

            latest = str(status.get("latestCompletedTurnId") or "").strip()
            if not latest:
                continue
            completed_at = status.get("latestCompletedAt")
            if isinstance(completed_at, (int, float)) and card.get("codexLatestCompletedAt") != completed_at:
                card["codexLatestCompletedAt"] = completed_at
                cards_changed = True

            if not active:
                for key, value in (
                    ("codexArmed", True),
                    ("codexLastSeenTurnId", latest),
                    ("codexLatestTurnId", latest),
                    ("codexDue", False),
                ):
                    if card.get(key) != value:
                        card[key] = value
                        cards_changed = True
                continue

            card_id = str(card.get("id") or "")
            has_baseline = card_id in baselines
            armed = card.get("codexArmed") is True
            if not has_baseline or not armed:
                if card_id not in counts:
                    counts[card_id] = 0
                baselines[card_id] = latest
                session_changed = True
                for key, value in (
                    ("codexArmed", True),
                    ("codexLastSeenTurnId", latest),
                    ("codexLatestTurnId", latest),
                    ("codexDue", False),
                ):
                    if card.get(key) != value:
                        card[key] = value
                        cards_changed = True
                continue

            if latest == card.get("codexLastSeenTurnId"):
                if card.get("codexLatestTurnId") != latest:
                    card["codexLatestTurnId"] = latest
                    cards_changed = True
                continue

            if baselines.get(card_id) != latest:
                baselines[card_id] = latest
                count = counts.get(card_id, 0)
                counts[card_id] = (count if isinstance(count, (int, float)) else 0) + 1
                session_changed = True
            for key, value in (
                ("codexDue", True),
                ("codexLatestTurnId", latest),
                ("visualShatteredToken", f"codex:{latest}"),
            ):
                if card.get(key) != value:
                    card[key] = value
                    cards_changed = True
            completion_count = sum(
                value
                for candidate in cards
                if candidate.get("codexThreadId")
                for value in [counts.get(str(candidate.get("id") or ""), 0)]
                if isinstance(value, (int, float))
            )
            events.append(
                (
                    f"codex:{ref}:{latest}",
                    "codex_completed",
                    {
                        "cardTitle": card.get("title") or "Codex 对话",
                        "threadName": card.get("codexThreadName") or status.get("name") or "Codex 对话",
                        "completionCount": int(completion_count),
                        "occurredAtLabel": _time_label(now),
                    },
                )
            )

        return cards_changed, session_changed, events

    @staticmethod
    def _status_fields(card: dict[str, Any], status: dict[str, Any]) -> dict[str, Any]:
        exists = status.get("exists", True) is not False
        current_status = status.get("status") if exists else "unavailable"
        current_status = str(current_status or "unknown")
        phase = str(status.get("phase") or "")
        active = exists and (
            current_status in ACTIVE_CODEX_STATUSES or (phase and phase != "idle")
        )
        next_phase = phase or ("reasoning" if active else "idle")
        started_at = status.get("activityStartedAt")
        fields = {
            "codexStatus": current_status,
            "codexPhase": next_phase if active else "idle",
            "codexPhaseLabel": status.get("phaseLabel") or ("处理中" if active else "保持关注"),
            "codexActivityStartedAt": started_at if isinstance(started_at, (int, float)) else None,
            "codexToolKind": str(status.get("toolKind") or ""),
        }
        for source, target in (
            ("name", "codexThreadName"),
            ("model", "codexModel"),
            ("reasoningEffort", "codexReasoningEffort"),
            ("cwd", "codexCwd"),
        ):
            value = status.get(source)
            if isinstance(value, str) and value:
                fields[target] = value
            elif target in {"codexModel", "codexReasoningEffort", "codexCwd"}:
                fields[target] = str(card.get(target) or "")
        return fields

    def _enqueue(self, events: list[tuple[str, str, dict[str, Any]]]) -> None:
        for event_id, event_type, data in events:
            if not event_id or event_id in self._attempted_event_ids:
                continue
            self.notifier.enqueue(event_id, event_type, data)
            self._attempted_event_ids.add(event_id)
