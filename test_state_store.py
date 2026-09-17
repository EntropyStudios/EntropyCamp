import copy
import tempfile
import unittest
from pathlib import Path

from state_store import BusinessStateStore, StateConflict, DEFAULTS, CARDS, SESSION, HISTORY, CLIPBOARD


class BusinessStateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = BusinessStateStore(Path(self.temp.name) / "state")
        self.store.initialize({CARDS: [{"id": "a", "title": "A"}]}, "test")

    def tearDown(self):
        self.temp.cleanup()

    def test_persistent_and_private(self):
        reopened = BusinessStateStore(self.store.directory)
        self.assertEqual(reopened.snapshot()["data"][CARDS][0]["title"], "A")
        self.assertEqual(self.store.directory.stat().st_mode & 0o777, 0o700)
        self.assertEqual(self.store.path.stat().st_mode & 0o777, 0o600)
        result = reopened.initialize({CARDS: []}, "another-browser")
        self.assertFalse(result["imported"])
        self.assertEqual(len(result["data"][CARDS]), 1)

    def test_non_conflicting_edits_from_stale_clients_merge(self):
        base = self.store.snapshot()["data"][CARDS]
        self.store.update({CARDS: {"base": base, "value": base + [{"id": "b", "title": "B"}]}})
        result = self.store.update({CARDS: {"base": base, "value": [{"id": "a", "title": "edited"}]}})
        self.assertEqual({r["id"]: r["title"] for r in result["data"][CARDS]}, {"a": "edited", "b": "B"})

    def test_conflict_rolls_back_whole_transaction(self):
        base = self.store.snapshot()["data"]
        self.store.update({CARDS: {"base": base[CARDS], "value": [{"id": "a", "title": "first"}]}})
        with self.assertRaises(StateConflict):
            self.store.update({CLIPBOARD: {"base": base[CLIPBOARD], "value": {"version": 1, "updatedAt": 1, "items": [{"id": "x"}]}},
                               CARDS: {"base": base[CARDS], "value": [{"id": "a", "title": "second"}]}})
        self.assertEqual(self.store.snapshot()["data"][CLIPBOARD]["items"], [])

    def test_old_shift_cannot_stop_a_new_shift(self):
        base = copy.deepcopy(DEFAULTS[SESSION])
        first = {**base, "active": True, "startedAt": 10}
        self.store.update({SESSION: {"base": base, "value": first}})
        with self.assertRaises(StateConflict):
            self.store.update({SESSION: {"base": base, "value": {**base, "endedAt": 20}}})

    def test_deleted_record_cannot_erase_concurrent_edit(self):
        base = self.store.snapshot()["data"][CARDS]
        self.store.update({CARDS: {"base": base, "value": [{"id": "a", "title": "edited"}]}})
        with self.assertRaises(StateConflict):
            self.store.update({CARDS: {"base": base, "value": []}})

    def test_invalid_versions_and_unknown_keys_rejected(self):
        for updates in ({"private-token": {}}, {HISTORY: {"base": DEFAULTS[HISTORY], "value": {"version": 99, "entries": []}}}):
            with self.assertRaises(ValueError):
                self.store.update(updates)
