import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import run
from state_store import BusinessStateStore, TASK_SYNC, StateConflict
from task_sync import (
    analysis_prompt,
    decision_prompt,
    normalize_analysis,
    parse_analysis_text,
    write_json_atomic,
)


class TaskSyncHelpersTest(unittest.TestCase):
    def test_task_sync_page_uses_shared_entropy_visual_system(self):
        root = Path(__file__).resolve().parent
        page = (root / "task-sync.html").read_text(encoding="utf-8")
        styles = (root / "task-sync.css").read_text(encoding="utf-8")
        script = (root / "task-sync.js").read_text(encoding="utf-8")

        self.assertIn('href="styles.css"', page)
        self.assertIn('class="page task-sync-page"', page)
        self.assertIn('class="source-search"', page)
        self.assertIn('id="waitingText"', page)
        self.assertIn(".source-thread-option.is-selected", styles)
        self.assertIn('[data-status="completed"]', styles)
        self.assertIn("prefers-reduced-motion", styles)
        self.assertIn('runStatus.dataset.status = run.status', script)
        self.assertIn('class="source-thread-option ${selectedSourceRefs.has(ref) ? "is-selected" : ""}"', script)

    def test_normalize_analysis_adds_stable_ids_and_keeps_human_selection(self):
        payload = {
            "summary": "同步结论",
            "linearUpdates": [
                {
                    "issueId": "MOTION-1",
                    "title": "更新",
                    "reason": "有新结论",
                    "sourceThreadIds": ["thread-1"],
                    "recommended": True,
                    "selected": False,
                }
            ],
            "newLinearTasks": [],
            "feishuTasks": [],
            "ignored": [],
        }
        result = normalize_analysis(payload)
        self.assertEqual(result["summary"], "同步结论")
        self.assertTrue(result["linearUpdates"][0]["id"].startswith("linearUpdates-1-"))
        self.assertFalse(result["linearUpdates"][0]["selected"])

    def test_parse_analysis_accepts_json_fence(self):
        payload = {
            "summary": "没有任务",
            "linearUpdates": [],
            "newLinearTasks": [],
            "feishuTasks": [],
            "ignored": [],
        }
        result = parse_analysis_text(f"```json\n{json.dumps(payload)}\n```")
        self.assertEqual(result["summary"], "没有任务")

    def test_artifact_write_and_prompts_reference_private_files(self):
        with tempfile.TemporaryDirectory() as directory:
            bundle = Path(directory) / "input.json"
            decision = Path(directory) / "decision.json"
            write_json_atomic(bundle, {"threads": []})
            write_json_atomic(decision, {"analysis": {}})
            self.assertEqual(json.loads(bundle.read_text()), {"threads": []})
            self.assertIn(str(bundle), analysis_prompt(bundle, 1, 2))
            prompt = decision_prompt("sync-1", bundle, decision, 2)
            self.assertIn(str(bundle), prompt)
            self.assertIn(str(decision), prompt)
            self.assertIn("第 2 次", prompt)

    def test_codex_bridge_starts_structured_turn_on_idle_thread(self):
        bridge = run.CodexBridge(["unused"])
        bridge.read_thread = Mock(return_value={"turns": []})
        bridge.request = Mock(return_value={"turn": {"id": "turn-1", "status": "inProgress"}})
        schema = {"type": "object"}
        turn = bridge.start_turn("thread-1", "分析", output_schema=schema)
        self.assertEqual(turn["id"], "turn-1")
        method, params = bridge.request.call_args.args
        self.assertEqual(method, "turn/start")
        self.assertEqual(params["threadId"], "thread-1")
        self.assertEqual(params["input"][0]["text"], "分析")
        self.assertEqual(params["outputSchema"], schema)

    def test_codex_bridge_refuses_to_interrupt_active_thread(self):
        bridge = run.CodexBridge(["unused"])
        bridge.read_thread = Mock(return_value={"turns": [{"id": "active", "status": "inProgress"}]})
        bridge.request = Mock()
        with self.assertRaisesRegex(RuntimeError, "正在处理"):
            bridge.start_turn("thread-1", "分析")
        bridge.request.assert_not_called()


class ManualTaskSyncTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = BusinessStateStore(Path(self.temp.name))
        self.store.initialize({})
        self.store_patch = patch.object(run, "BUSINESS_STORE", self.store)
        self.store_patch.start()
        self.addCleanup(self.store_patch.stop)
        self.payload = {"summary": "已分析", "linearUpdates": [], "newLinearTasks": [], "feishuTasks": [], "ignored": []}

    def create_run(self):
        threads = [{"id": "manager", "hostId": "local", "name": "统管"}]
        logs = [{"id": "source", "turns": [{"id": "turn-1"}]}]
        with patch.object(run, "list_all_codex_threads", return_value=threads), patch.object(
            run, "_read_task_sync_window", return_value=logs
        ), patch.object(run.CODEX_BRIDGE, "start_turn", side_effect=AssertionError("不应自动发消息")):
            return run.start_task_sync_analysis("manager", 1)

    def test_manual_full_cycle_and_repeated_receipt_rejected(self):
        batch = self.create_run()
        self.assertEqual(batch["status"], "awaiting_analysis")
        detail = run.task_sync_detail(batch["id"])
        self.assertEqual(detail["bundle"]["threads"][0]["id"], "source")
        self.assertIn("/result", run.task_sync_request(batch["id"], "analysis")["prompt"])
        reviewed = run.save_task_sync_result({"runId": batch["id"], "phase": "analysis", "expectedRevision": 1, "analysis": self.payload})
        with patch.object(run.CODEX_BRIDGE, "start_turn", side_effect=AssertionError("不应自动发消息")):
            confirmed = run.submit_task_sync_decision(batch["id"], reviewed["analysis"], 2)
        self.assertEqual(confirmed["status"], "awaiting_execution")
        self.assertIn("executionHistory", run.task_sync_request(batch["id"], "execution")["prompt"])
        body = {"runId": batch["id"], "phase": "execution", "expectedRevision": 3, "decisionRevision": 1, "result": "已完成，无外部写入"}
        completed = run.save_task_sync_result(body)
        self.assertEqual(completed["status"], "completed")
        self.assertEqual(len(completed["executionHistory"]), 1)
        with self.assertRaises(StateConflict):
            run.save_task_sync_result(body)

    def test_failed_legacy_batch_reuses_original_bundle(self):
        batch = self.create_run()
        run._update_task_sync_run(batch["id"], lambda value: {**value, "status": "failed", "error": "thread not found"})
        prompt = run.task_sync_request(batch["id"], "analysis")["prompt"]
        self.assertIn(batch["id"], prompt)
        reviewed = run.save_task_sync_result({"runId": batch["id"], "phase": "analysis", "expectedRevision": 1, "analysis": self.payload})
        self.assertEqual(reviewed["error"], "")
        self.assertEqual(reviewed["bundlePath"], batch["bundlePath"])

    def test_stale_decision_does_not_replace_review(self):
        batch = self.create_run()
        run.save_task_sync_result({"runId": batch["id"], "phase": "analysis", "expectedRevision": 1, "analysis": self.payload})
        with self.assertRaises(StateConflict):
            run.submit_task_sync_decision(batch["id"], self.payload, 1)
        self.assertEqual(run.task_sync_detail(batch["id"])["run"]["status"], "review")


if __name__ == "__main__":
    unittest.main()
