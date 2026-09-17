import json
import tempfile
import threading
import unittest
import urllib.request
import urllib.error
from pathlib import Path
from unittest import mock

import run
from state_store import BusinessStateStore, CARDS, SESSION, HISTORY, DEFAULTS


class StateAPITests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.store = BusinessStateStore(Path(self.temporary.name))
        self.patch = mock.patch.object(run, "BUSINESS_STORE", self.store)
        self.patch.start()
        self.server = run.ReminderServer(("127.0.0.1", 0), run.ReminderHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.patch.stop()
        self.temporary.cleanup()

    def request(self, path="/api/state", body=None, headers=None):
        request = urllib.request.Request(self.base + path, data=json.dumps(body).encode() if body is not None else None,
                                         headers=headers or {"Content-Type": "application/json", "X-Lumen-Request": "1"})
        with urllib.request.urlopen(request, timeout=5) as response:
            return json.load(response)

    def test_import_shared_updates_revision_and_restart(self):
        self.assertFalse(self.request()["initialized"])
        first = self.request("/api/state/import", {"data": {CARDS: [{"id": "a", "title": "from Zen"}]}})
        result = self.request(body={"updates": {CARDS: {"base": first["data"][CARDS], "value": first["data"][CARDS] + [{"id": "b"}]}}})
        self.assertEqual(len(self.request()["data"][CARDS]), 2)
        self.assertTrue(self.request(f"/api/state?revision={result['revision']}")["unchanged"])
        self.assertEqual(len(BusinessStateStore(self.store.directory).snapshot()["data"][CARDS]), 2)
        self.assertFalse(self.request("/api/state/import", {"data": {CARDS: []}})["imported"])

    def test_no_cross_site_write_or_rebinding_host(self):
        for headers in ({"Content-Type": "application/json"},
                        {"Content-Type": "application/json", "X-Lumen-Request": "1", "Origin": "https://example.com"},
                        {"Content-Type": "application/json", "X-Lumen-Request": "1", "Host": "example.com"}):
            with self.assertRaises(urllib.error.HTTPError) as caught:
                self.request("/api/state/import", {"data": {}}, headers)
            self.assertEqual(caught.exception.code, 403)

    def test_shift_history_and_cards_commit_together(self):
        first = self.request("/api/state/import", {"data": {}})["data"]
        session = {**first[SESSION], "startedAt": 10, "endedAt": 20, "active": False}
        history = {**first[HISTORY], "entries": [{"id": "shift", "startedAt": 10, "endedAt": 20}]}
        result = self.request(body={"updates": {SESSION: {"base": first[SESSION], "value": session},
                                               HISTORY: {"base": first[HISTORY], "value": history}}})
        self.assertEqual(result["data"][SESSION]["endedAt"], 20)
        self.assertEqual(result["data"][HISTORY]["entries"][0]["id"], "shift")
