import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from claude_sessions import ClaudeSessions, PREFIX

UUID = "12345678-1234-1234-1234-123456789abc"


class ClaudeSessionsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.project = self.home / "projects" / "-test-project"
        self.project.mkdir(parents=True)
        self.path = self.project / (UUID + ".jsonl")
        self.client = ClaudeSessions(self.home)
        self.id = PREFIX + UUID

    def append(self, kind, second, content=None, **kwargs):
        row = {"type": kind, "uuid": f"{kind}-{second}", "timestamp": f"2026-10-23T10:00:{second:02d}Z", "cwd": "/project", **kwargs}
        if content is not None:
            row["message"] = {"role": kind, "content": content, "model": "claude-opus-test", "stop_reason": row.pop("stop_reason", None)}
        with self.path.open("a") as f:
            f.write(json.dumps(row) + "\n")

    def status(self):
        return self.client.thread_statuses([self.id])[0]

    def test_tool_results_and_split_final_count_one_user_turn(self):
        self.append("user", 1, "First task")
        self.append("assistant", 2, [{"type":"tool_use", "name":"Bash"}], stop_reason="tool_use")
        self.assertEqual(self.status()["phase"], "executing")
        self.assertIsNone(self.status()["latestCompletedTurnId"])
        self.append("user", 3, [{"type":"tool_result", "content":"ok"}])
        self.append("assistant", 4, [{"type":"thinking", "thinking":"private reasoning"}], stop_reason="end_turn")
        self.assertIsNone(self.status()["latestCompletedTurnId"])
        self.append("assistant", 5, [{"type":"text", "text":"Done"}], stop_reason="end_turn")
        self.assertEqual(self.status()["latestCompletedTurnId"], "user-1")
        self.assertEqual(self.status()["status"], "idle")
        turns = self.client.work_logs([self.id])[0]["turns"]
        self.assertEqual(len(turns), 1)
        self.assertNotIn("private reasoning", json.dumps(turns))

    def test_new_prompt_retains_previous_completion_until_new_final(self):
        self.append("user",1,"One")
        self.append("assistant",2,[{"type":"text","text":"Done"}],stop_reason="end_turn")
        self.assertEqual(self.status()["latestCompletedTurnId"],"user-1")
        self.append("user",3,"Two")
        self.assertEqual(self.status()["status"],"active")
        self.assertEqual(self.status()["latestCompletedTurnId"],"user-1")
        self.append("assistant",4,[{"type":"text","text":"Done again"}],stop_reason="end_turn")
        self.assertEqual(self.status()["latestCompletedTurnId"],"user-3")

    def test_report_window_and_process_filter(self):
        self.append("user",1,"Task")
        self.append("assistant",2,[{"type":"text","text":"Working"}],stop_reason="tool_use")
        self.append("assistant",5,[{"type":"text","text":"Final"}],stop_reason="end_turn")
        turn=self.client.work_logs([self.id],include_process=False)[0]["turns"][0]
        self.assertEqual([i['text'] for i in turn['items']],["Task","Final"])
        end=turn['completedAt']
        self.assertEqual(len(self.client.work_logs([self.id],since=end-1)[0]['turns']),1)
        self.assertEqual(self.client.work_logs([self.id],since=end+1)[0]['turns'],[])
        early=self.client.work_logs([self.id],until=end-1)[0]['turns'][0]
        self.assertIsNone(early['completedAt'])
        self.assertNotIn('Final',json.dumps(early))

    def test_partial_tail_duplicate_and_truncation(self):
        self.append("user",1,"Task")
        self.status()
        raw=json.dumps({"type":"assistant","uuid":"answer","timestamp":"2026-10-23T10:00:02Z","message":{"content":[{"type":"text","text":"done"}],"stop_reason":"end_turn"}})
        with self.path.open('a') as f:f.write(raw)
        self.assertIsNone(self.status()['latestCompletedTurnId'])
        with self.path.open('a') as f:f.write('\n'+raw+'\n')
        self.assertEqual(self.status()['latestCompletedTurnId'],'user-1')
        self.assertEqual(len(self.client.work_logs([self.id])[0]['turns'][0]['items']),2)
        self.path.write_text('')
        self.assertIsNone(self.status()['latestCompletedTurnId'])

    def test_missing_files_sidechains_and_paths(self):
        self.append("user",1,"Ignore",isSidechain=True)
        self.assertEqual(self.client.list_threads(),[])
        self.assertFalse(self.client.thread_statuses(['claude-../../secret'])[0]['exists'])
        self.assertFalse(self.client.thread_statuses(['claude-no-file'])[0]['exists'])

    def test_interruption_and_api_failure_never_complete(self):
        self.append('user',1,'Task')
        self.append('user',2,'[Request interrupted by user for tool use]')
        self.assertEqual(self.status()['status'],'idle')
        self.assertIsNone(self.status()['latestCompletedTurnId'])
        self.append('user',3,'Retry')
        self.append('assistant',4,[{'type':'text','text':'API error'}],stop_reason='end_turn',isApiErrorMessage=True)
        self.assertEqual(self.status()['status'],'idle')
        self.assertIsNone(self.status()['latestCompletedTurnId'])

    def test_unchanged_status_does_not_reread_file(self):
        self.append('user',1,'Task');self.status()
        with patch.object(Path,'open',side_effect=AssertionError('should use cached transcript')):
            self.assertEqual(self.status()['status'],'active')

    def test_shared_routes_do_not_send_claude_ids_to_codex(self):
        import run
        self.append('user',1,'Task')
        self.append('assistant',2,[{'type':'text','text':'Done'}],stop_reason='end_turn')
        with patch.object(run,'CLAUDE_SESSIONS',self.client), patch.object(run.CODEX_MONITOR,'thread_statuses',side_effect=AssertionError('Codex must not receive Claude ID')):
            result=run.codex_statuses([{'hostId':'local','id':self.id}])
            self.assertEqual(result[0]['latestCompletedTurnId'],'user-1')
        with patch.object(run,'CLAUDE_SESSIONS',self.client), patch.object(run.CODEX_WORK_LOGS,'work_logs',side_effect=AssertionError('No Codex read')):
            self.assertEqual(len(run.local_ai_work_logs([self.id])[0]['turns']),1)

    def test_background_count_notification_and_history_reference(self):
        from background_events import BackgroundEventMonitor
        from state_store import BusinessStateStore, CARDS, SESSION, HISTORY
        from test_background_events import FakeNotifier
        self.append('user',1,'First');self.append('assistant',2,[{'type':'text','text':'Done'}],stop_reason='end_turn')
        self.status()
        store=BusinessStateStore(self.home/'business')
        card={'id':'claude-card','title':'Claude task','codexThreadId':self.id,'codexHost':'local','codexArmed':True,'codexLastSeenTurnId':'user-1'}
        session={'active':True,'startedAt':1,'endedAt':None,'countsByCardId':{'claude-card':0},'countedTurnIdsByCardId':{'claude-card':'user-1'}}
        store.initialize({CARDS:[card],SESSION:session})
        notifier=FakeNotifier()
        monitor=BackgroundEventMonitor(store=store,status_provider=lambda refs:self.client.thread_statuses([r['id'] for r in refs]),notifier=notifier)
        self.append('user',3,'Next');self.append('assistant',4,[{'type':'tool_use','name':'Bash'}],stop_reason='tool_use')
        monitor.run_once();self.assertEqual(notifier.events,[])
        self.append('assistant',5,[{'type':'text','text':'Final'}],stop_reason='end_turn')
        monitor.run_once();monitor.run_once()
        state=store.snapshot()['data']
        self.assertEqual(state[SESSION]['countsByCardId']['claude-card'],1)
        self.assertTrue(state[CARDS][0]['codexDue'])
        self.assertEqual(len(notifier.events),1)
        # Saved references retain prefixed IDs without needing a new storage migration.
        self.assertEqual(self.client.work_logs([state[CARDS][0]['codexThreadId']])[0]['turns'][-1]['id'],'user-3')
