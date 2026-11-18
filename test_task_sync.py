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
    validate_wbs_selection,
)


class TaskSyncHelpersTest(unittest.TestCase):
    def test_wbs_requires_parent_and_contract_evidence(self):
        raw = {"newLinearTasks": [{"id": "child", "title": "推进", "selected": True}]}
        self.assertFalse(normalize_analysis(raw)["newLinearTasks"][0]["selected"])
        with self.assertRaisesRegex(ValueError, "父TASK"):
            validate_wbs_selection(raw)
        raw["newLinearTasks"][0].update(parentIssueId="MOTION-294", parentTitle="候选提速",
                                       scopeEvidence="父任务要求候选提速", project="算法验证",
                                       module="轨迹规划", taskType="优化",
                                       description="## 工作方向\n候选\n## 工作要求\n提速\n## 时间与分工\n待确认\n## 推进记录\n评论")
        validate_wbs_selection(raw)
        self.assertTrue(normalize_analysis(raw)["newLinearTasks"][0]["selected"])

    def test_wbs_questions_and_parent_requests_cannot_execute(self):
        payload = {
            "parentTaskRequests": [{"title": "待确认父任务", "selected": True}],
            "newLinearTasks": [{"id": "child", "title": "子工作", "selected": True,
                                "parentIssueId": "MOTION-294", "scopeEvidence": "候选提速"}],
            "questions": [{"question": "范围是否确认？", "relatedItemIds": ["child"], "status": "ignored"}],
        }
        normalized = normalize_analysis(payload)
        self.assertFalse(normalized["parentTaskRequests"][0]["selected"])
        self.assertFalse(normalized["newLinearTasks"][0]["selected"])
        with self.assertRaises(ValueError):
            validate_wbs_selection(payload)
        validate_wbs_selection(normalized)

    def test_child_requires_readable_parent_and_template(self):
        row = {"title": "提速", "selected": True, "parentIssueId": "MOTION-294",
               "scopeEvidence": "候选提速", "project": "算法", "module": "规划", "taskType": "优化"}
        with self.assertRaisesRegex(ValueError, "父TASK标题"):
            validate_wbs_selection({"newLinearTasks": [row]})
        row["parentTitle"] = "候选提速"
        with self.assertRaisesRegex(ValueError, "工作方向"):
            validate_wbs_selection({"newLinearTasks": [row]})
        self.assertFalse(normalize_analysis({"newLinearTasks": [row]})["newLinearTasks"][0]["selected"])

    def test_parent_progress_and_acceptance_are_distinct(self):
        row = {"id": "accept1", "issueId": "MOTION-294", "parentIssueId": "MOTION-294",
               "parentTitle": "提速", "scopeEvidence": "整体对照已完成", "selected": True}
        with self.assertRaisesRegex(ValueError, "日常推进"):
            validate_wbs_selection({"linearUpdates": [row]})
        with self.assertRaisesRegex(ValueError, "推进子Issue"):
            validate_wbs_selection({"acceptanceRequests": [row]})
        row["childIssueIds"] = ["MOTION-298", "MOTION-299"]
        validate_wbs_selection({"acceptanceRequests": [row]})
        saved = normalize_analysis({"acceptanceRequests": [row]})
        self.assertEqual(saved["acceptanceRequests"][0]["childIssueIds"], row["childIssueIds"])
        self.assertTrue(saved["acceptanceRequests"][0]["selected"])
        saved["questions"] = [{"question": "范围确认？", "relatedItemIds": ["accept1"], "status": "pending"}]
        self.assertFalse(normalize_analysis(saved)["acceptanceRequests"][0]["selected"])

    def test_scope_changes_default_off_and_ids_do_not_collide(self):
        row = {"id": "same", "issueId": "MOTION-294", "parentIssueId": "MOTION-294",
               "parentTitle": "提速", "scopeEvidence": "合同变更", "updateKind": "scope_change"}
        self.assertFalse(normalize_analysis({"linearUpdates": [row]})["linearUpdates"][0]["selected"])
        with self.assertRaisesRegex(ValueError, "ID重复"):
            normalize_analysis({"linearUpdates": [row], "parentTaskRequests": [{"id": "same", "title": "新任务"}]})

    def test_questions_keep_answers_and_ignore(self):
        value = normalize_analysis({"questions": [
            {"id": "q1", "question": "归属哪个项目？", "options": ["A", "B"], "relatedItemIds": ["task1"], "status": "answered", "answer": "A"},
            {"id": "q2", "question": "截止日期？", "status": "ignored", "answer": ""},
        ]})
        again = normalize_analysis(value)
        self.assertEqual(again["questions"][0]["answer"], "A")
        self.assertEqual(again["questions"][0]["relatedItemIds"], ["task1"])
        self.assertEqual(again["questions"][1]["status"], "ignored")
        self.assertEqual(normalize_analysis({})["questions"], [])
        with self.assertRaises(ValueError):
            normalize_analysis({"questions": [{"question": "日期？", "status": "answered", "answer": ""}]})

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
    def test_new_claude_selection_backfills_from_last_collection_and_is_frozen(self):
        from claude_sessions import ClaudeSessions
        from test_claude_sessions import UUID
        home=Path(self.temp.name)/'claude'
        project=home/'projects'/'-test'
        project.mkdir(parents=True)
        rows=[{'type':'user','uuid':'older-prompt','timestamp':'2026-10-23T10:00:01Z','message':{'content':'Earlier work'}},
              {'type':'assistant','uuid':'older-answer','timestamp':'2026-10-23T10:00:05Z','message':{'content':[{'type':'text','text':'Earlier answer'}],'stop_reason':'end_turn'}}]
        (project/(UUID+'.jsonl')).write_text(''.join(json.dumps(row)+'\n' for row in rows))
        client=ClaudeSessions(home)
        since=1792749600000  # 2026-10-23 10:00 UTC, before the selection was made.
        run._task_sync_mutate(lambda d:{**d,'lastTriggeredAt':since,'selectedSourceRefs':['manager','ssh-old::remote']})
        before=self.store.snapshot()['data'][TASK_SYNC]['lastTriggeredAt']
        with patch.object(run,'CLAUDE_SESSIONS',client), patch.object(run,'list_all_codex_threads',return_value=[{'id':'manager','hostId':'local','name':'Manager'}]), \
             patch.object(run.CODEX_BRIDGE,'start_turn',side_effect=AssertionError('No automatic send')):
            # Session is absent from recent list; resolve the explicitly selected log.
            batch=run.start_task_sync_analysis('manager',source_thread_refs=['claude-'+UUID,'ssh-old::remote'])
        detail=run.task_sync_detail(batch['id'])
        self.assertEqual(batch['windowStart'],before)
        thread=detail['bundle']['threads'][0]
        self.assertEqual(thread['provider'],'claude')
        self.assertEqual(thread['turns'][0]['items'][-1]['text'],'Earlier answer')
        self.assertEqual(detail['bundle']['selectedSourceRefs'],['claude-'+UUID])
        saved=self.store.snapshot()['data'][TASK_SYNC]
        self.assertEqual(saved['selectedSourceRefs'],['claude-'+UUID])
        self.assertTrue(Path(batch['bundlePath']).is_file())

    def test_saved_selection_is_used_and_ssh_is_excluded(self):
        run._task_sync_mutate(lambda d:{**d,'lastTriggeredAt':1000,'selectedSourceRefs':['claude-test','ssh-old::remote']})
        threads=[{'id':'manager','hostId':'local'},{'id':'claude-test','hostId':'local'}, {'id':'remote','hostId':'ssh-old'}]
        with patch.object(run,'list_all_codex_threads',return_value=threads), patch.object(run,'_read_task_sync_window',return_value=[]) as reader:
            batch=run.start_task_sync_analysis('manager')
        self.assertEqual(reader.call_args.args[0],[threads[1]])
        self.assertEqual(batch['windowStart'],1000)

    def test_failed_source_read_does_not_advance_collection_cursor(self):
        run._task_sync_mutate(lambda d:{**d,'lastTriggeredAt':1000})
        threads=[{'id':'manager','hostId':'local'},{'id':'claude-test','hostId':'local'}]
        with patch.object(run,'list_all_codex_threads',return_value=threads), patch.object(run,'local_ai_work_logs',return_value=[{'id':'claude-test','error':'log missing','turns':[]}]):
            with self.assertRaisesRegex(ValueError,'未推进'):
                run.start_task_sync_analysis('manager',source_thread_refs=['claude-test'])
        saved=self.store.snapshot()['data'][TASK_SYNC]
        self.assertEqual(saved['lastTriggeredAt'],1000)
        self.assertEqual(saved['runs'],[])

    def test_window_reader_never_contacts_ssh(self):
        with patch.object(run,'local_ai_work_logs',return_value=[]) as reader:
            self.assertEqual(run._read_task_sync_window([{'id':'remote','hostId':'ssh-old'}],1,2),[])
            reader.assert_not_called()

    def test_execution_receipt_keeps_comment_ids_and_rejects_unconfirmed_items(self):
        batch = self.create_run()
        payload = {**self.payload, "linearUpdates": [{
            "id": "progress-1", "issueId": "MOTION-298", "title": "补录",
            "parentIssueId": "MOTION-294", "parentTitle": "候选提速",
            "scopeEvidence": "候选筛选实现", "selected": True,
        }]}
        reviewed = run.save_task_sync_result({
            "runId": batch["id"], "phase": "analysis", "expectedRevision": 1, "analysis": payload,
        })
        confirmed = run.submit_task_sync_decision(batch["id"], reviewed["analysis"], reviewed["revision"])
        body = {"runId": batch["id"], "phase": "execution", "expectedRevision": confirmed["revision"],
                "decisionRevision": 1, "result": "已补录", "operations": [
                    {"itemId": "other", "status": "success", "issueId": "MOTION-298"},
                ]}
        with self.assertRaisesRegex(ValueError, "本版确认"):
            run.save_task_sync_result(body)
        self.assertEqual(run.task_sync_detail(batch["id"])["run"]["revision"], confirmed["revision"])
        body["operations"] = [{"itemId": "progress-1", "status": "success", "issueId": "MOTION-298",
                               "commentIds": ["comment-123"], "url": "https://linear.app/sevenova/issue/MOTION-298"}]
        result = run.save_task_sync_result(body)
        self.assertEqual(result["executionOperations"][0]["commentIds"], ["comment-123"])
        self.assertEqual(result["executionHistory"][0]["operations"], result["executionOperations"])

    def test_missing_parent_does_not_freeze_execution_decision(self):
        batch = self.create_run()
        reviewed = run.save_task_sync_result({
            "runId": batch["id"], "phase": "analysis", "expectedRevision": 1,
            "analysis": self.payload,
        })
        unsafe = {**self.payload, "newLinearTasks": [
            {"title": "无父任务", "selected": True, "parentIssueId": None},
        ]}
        with self.assertRaisesRegex(ValueError, "父TASK"):
            run.submit_task_sync_decision(batch["id"], unsafe, reviewed["revision"])
        self.assertEqual(run.task_sync_detail(batch["id"])["run"]["decisionRevisions"], [])
        prompt = run.task_sync_request(batch["id"], "analysis")["prompt"]
        self.assertIn("parentTaskRequests", prompt)
        self.assertIn("标题相似", prompt)
        self.assertIn("/api/performance/records", prompt)

    def test_answers_are_frozen_in_decision(self):
        batch = self.create_run()
        payload = {**self.payload, "questions": [{"id": "q1", "question": "截止日期？", "status": "pending", "answer": "", "relatedItemIds": []}]}
        reviewed = run.save_task_sync_result({"runId": batch["id"], "phase": "analysis", "expectedRevision": 1, "analysis": payload})
        reviewed["analysis"]["questions"][0].update(status="answered", answer="10月15日")
        confirmed = run.submit_task_sync_decision(batch["id"], reviewed["analysis"], 2)
        self.assertEqual(confirmed["decisionRevisions"][0]["analysis"]["questions"][0]["answer"], "10月15日")
        self.assertIn("ignored不代表同意", run.task_sync_request(batch["id"], "execution")["prompt"])

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
