import tempfile
import unittest
from pathlib import Path

from background_events import BackgroundEventMonitor
from state_store import BusinessStateStore, CARDS, SESSION


class FakeNotifier:
    def __init__(self):
        self.events = []

    def enqueue(self, event_id, event_type, data):
        self.events.append((event_id, event_type, data))
        return {"accepted": True}


class BackgroundEventMonitorTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.store = BusinessStateStore(Path(self.temporary.name) / "state")
        self.notifier = FakeNotifier()
        self.statuses = []
        self.now = 1_800_000_000.0

    def tearDown(self):
        self.temporary.cleanup()

    def initialize(self, *, active=True, timer=False):
        cards = [
            {
                "id": "card-1",
                "title": "架构",
                "codexThreadId": "thread-1",
                "codexHost": "local",
                "codexThreadName": "架构讨论",
                "codexArmed": True,
                "codexDue": False,
                "codexLastSeenTurnId": "turn-old",
                "codexLatestTurnId": "turn-old",
            }
        ]
        if timer:
            cards.append(
                {
                    "id": "timer-1",
                    "title": "喝水",
                    "codexThreadId": "",
                    "started": True,
                    "nextAt": int(self.now * 1000) - 1000,
                    "visualShatteredToken": "",
                }
            )
        session = {
            "active": active,
            "startedAt": int(self.now * 1000) - 60_000 if active else None,
            "endedAt": None,
            "countsByCardId": {"card-1": 0},
            "countedTurnIdsByCardId": {"card-1": "turn-old"},
        }
        self.store.initialize({CARDS: cards, SESSION: session}, "test")

    def monitor(self):
        return BackgroundEventMonitor(
            store=self.store,
            status_provider=lambda refs: self.statuses,
            notifier=self.notifier,
            clock=lambda: self.now,
        )

    def test_codex_completion_is_recorded_and_enqueued_without_homepage(self):
        self.initialize()
        self.statuses = [
            {
                "id": "thread-1",
                "hostId": "local",
                "name": "架构讨论",
                "exists": True,
                "status": "idle",
                "phase": "idle",
                "phaseLabel": "保持关注",
                "latestCompletedTurnId": "turn-new",
                "latestCompletedAt": self.now,
            }
        ]

        monitor = self.monitor()
        monitor.run_once()
        monitor.run_once()

        state = self.store.snapshot()["data"]
        card = state[CARDS][0]
        self.assertEqual(state[SESSION]["countsByCardId"]["card-1"], 1)
        self.assertEqual(state[SESSION]["countedTurnIdsByCardId"]["card-1"], "turn-new")
        self.assertTrue(card["codexDue"])
        self.assertEqual(card["codexLatestTurnId"], "turn-new")
        self.assertEqual(card["visualShatteredToken"], "codex:turn-new")
        self.assertEqual(len(self.notifier.events), 1)
        self.assertEqual(self.notifier.events[0][0], "codex:thread-1:turn-new")
        self.assertEqual(self.notifier.events[0][1], "codex_completed")
        self.assertEqual(self.notifier.events[0][2]["completionCount"], 1)

    def test_completion_while_off_work_advances_baseline_without_notification(self):
        self.initialize(active=False)
        self.statuses = [
            {
                "id": "thread-1",
                "hostId": "local",
                "exists": True,
                "status": "idle",
                "latestCompletedTurnId": "turn-after-work",
                "latestCompletedAt": self.now,
            }
        ]

        self.monitor().run_once()

        state = self.store.snapshot()["data"]
        card = state[CARDS][0]
        self.assertEqual(card["codexLastSeenTurnId"], "turn-after-work")
        self.assertEqual(card["codexLatestTurnId"], "turn-after-work")
        self.assertFalse(card["codexDue"])
        self.assertEqual(self.notifier.events, [])

    def test_due_timer_is_enqueued_without_homepage(self):
        self.initialize(timer=True)

        monitor = self.monitor()
        monitor.run_once()
        monitor.run_once()

        cards = self.store.snapshot()["data"][CARDS]
        timer = next(card for card in cards if card["id"] == "timer-1")
        self.assertEqual(timer["visualShatteredToken"], f"timer:{timer['nextAt']}")
        timer_events = [event for event in self.notifier.events if event[1] == "reminder_due"]
        self.assertEqual(len(timer_events), 1)
        self.assertEqual(timer_events[0][0], f"reminder:timer-1:{timer['nextAt']}")


if __name__ == "__main__":
    unittest.main()
