import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

import run
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


if __name__ == "__main__":
    unittest.main()
