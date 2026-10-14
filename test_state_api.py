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
    def test_sync_saved_results_do_not_wait_for_codex_thread_scan(self):
        with mock.patch.object(run.ReminderHandler, "_list_codex_threads", side_effect=RuntimeError("SSH列表不可用")):
            result = self.request("/api/task-sync?stateOnly=1")
        self.assertTrue(result["available"])
        self.assertIn("runs", result["state"])

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

    def test_manual_sync_http_roundtrip_and_stale_write(self):
        self.store.initialize({})
        with mock.patch.object(run, "list_all_codex_threads", return_value=[{"id": "manager", "hostId": "local"}]), mock.patch.object(
            run, "_read_task_sync_window", return_value=[{"id": "source", "turns": [{"id": "one"}]}]
        ), mock.patch.object(run.CODEX_BRIDGE, "start_turn", side_effect=AssertionError("不得自动发送")):
            batch = self.request("/api/task-sync/analyze", {"managerThreadId": "manager", "since": 1})["run"]
            run_id = batch["id"]
            detail = self.request(f"/api/task-sync/run?id={run_id}")
            self.assertEqual(detail["bundle"]["threads"][0]["id"], "source")
            self.assertIn("expectedRevision", self.request(f"/api/task-sync/request?id={run_id}")["prompt"])
            body = {"runId": run_id, "phase": "analysis", "expectedRevision": 1,
                    "analysis": {"summary": "可审核", "linearUpdates": [], "newLinearTasks": [], "feishuTasks": [], "ignored": []}}
            self.assertEqual(self.request("/api/task-sync/result", body)["run"]["status"], "review")
            with self.assertRaises(urllib.error.HTTPError) as caught:
                self.request("/api/task-sync/result", body)
            self.assertEqual(caught.exception.code, 409)
            with self.assertRaises(urllib.error.HTTPError) as caught:
                self.request("/api/task-sync/result", {**body, "expectedRevision": 2}, {"Content-Type": "application/json"})
            self.assertEqual(caught.exception.code, 403)
