import copy
import tempfile
import unittest
import subprocess
from pathlib import Path
from unittest.mock import patch

from ai_discovery import AIDiscovery, MONTH_MS
from background_events import BackgroundEventMonitor
from state_store import BusinessStateStore, CARDS, SESSION, HISTORY


class AIDiscoveryTests(unittest.TestCase):
    def test_source_selection_is_previous_selection_intersect_current_window(self):
        source=Path(__file__).with_name('task-sync.js').read_text()
        start=source.index('  async function loadSources()')
        end=source.index('\n  function schedulePoll',start)
        harness=r'''
const assert=require('assert/strict');
let sourceRequestVersion=0,sourcesLoading=false,sourceThreads=[],managerThreads=[],sourcesInitialized=false;
let selectedSourceRefs=new Set(),windowStartDirty=false;
const analyzeButton={},sourceSelectionSummary={},windowStartInput={value:'2026-11-23T00:00'};
let state={lastTriggeredAt:1,selectedSourceRefs:['a','b','ssh-old::z']};
const sourceRef=t=>t.id;function render(){}
let response={threads:[{id:'b',hostId:'local'},{id:'c',hostId:'local'}],managerThreads:[]};
async function request(path){assert.ok(path.startsWith('/api/task-sync/candidates?since=1'));return response;}
'''
        cases=r'''
(async()=>{
await loadSources();assert.deepEqual([...selectedSourceRefs],['b']);
selectedSourceRefs.add('c');response.threads=[{id:'c',hostId:'local'},{id:'d',hostId:'local'}];
await loadSources();assert.deepEqual([...selectedSourceRefs],['c']);
sourcesInitialized=false;state.selectedSourceRefs=null;await loadSources();assert.equal(selectedSourceRefs.size,0);
assert.equal(sourcesLoading,false);
})().catch(e=>{console.error(e);process.exitCode=1;});
'''
        result=subprocess.run(['node','-e',harness+source[start:end]+cases],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_discovery_reuses_cards_preserves_timers_and_hides_then_revives(self):
        now=1800000000000
        threads=[{'id':'a','name':'Codex task','updatedAt':now/1000,'hostId':'local'},
                 {'id':'claude-b','name':'Claude task','updatedAt':now,'hostId':'local'},
                 {'id':'old','updatedAt':now-MONTH_MS-1}, {'id':'ssh','hostId':'ssh-old','updatedAt':now}]
        discovery=AIDiscovery(lambda:threads,interval=0)
        cards=[{'id':'timer','title':'Timer','intervalMs':10},
               {'id':'existing','title':'My name','codexThreadId':'a','codexHost':'local','codexDue':True}]
        self.assertTrue(discovery.reconcile(cards,now))
        self.assertEqual(len(cards),3)
        self.assertEqual(cards[1]['title'],'My name')
        self.assertTrue(cards[1]['codexDue'])
        self.assertFalse(discovery.reconcile(cards,now))
        self.assertTrue(discovery.reconcile(cards,now+MONTH_MS+1))
        self.assertTrue(cards[1]['aiHidden'])
        self.assertNotIn('aiHidden',cards[0])
        threads[0]['updatedAt']=(now+MONTH_MS+1000)/1000
        discovery.reconcile(cards,now+MONTH_MS+1000)
        self.assertFalse(cards[1]['aiHidden'])
        self.assertEqual(cards[1]['id'],'existing')

    def test_background_discovery_persists_without_a_browser_and_keeps_history(self):
        with tempfile.TemporaryDirectory() as directory:
            store=BusinessStateStore(Path(directory))
            store.initialize({SESSION:{'active':True,'startedAt':1,'endedAt':None,'countsByCardId':{},'countedTurnIdsByCardId':{}}})
            monitor=BackgroundEventMonitor(store=store,status_provider=lambda refs:[],notifier=None,clock=lambda:1800000000)
            monitor._enqueue=lambda events:None
            monitor.discovery=AIDiscovery(lambda:[{'id':'claude-test','name':'Test','updatedAt':1800000000}],interval=0)
            original=copy.deepcopy(store.snapshot()['data'][HISTORY])
            monitor.run_once()
            data=store.snapshot()['data']
            self.assertEqual(len(data[CARDS]),1)
            self.assertEqual(data[CARDS][0]['codexThreadId'],'claude-test')
            self.assertEqual(data[HISTORY],original)
            monitor.run_once()
            self.assertEqual(len(store.snapshot()['data'][CARDS]),1)

    def test_window_candidates_only_include_actual_turns_and_keep_manager_separate(self):
        import run
        threads=[{'id':'manager','updatedAt':2000,'hostId':'local'},
                 {'id':'claude-b','updatedAt':2000,'hostId':'local'},
                 {'id':'old','updatedAt':1,'hostId':'local'}]
        def read(rows,since,until):
            return [{'id':'claude-b','turns':[{'id':'turn'}]}] if rows[0]['id']=='claude-b' else []
        with patch.object(run,'discover_local_ai_threads',return_value=threads),patch.object(run,'_read_task_sync_window',side_effect=read):
            result=run.task_sync_candidates(1500000,2500000)
        self.assertEqual([t['id'] for t in result['threads']],['claude-b'])
        self.assertIn('manager',[t['id'] for t in result['managerThreads']])


if __name__=='__main__':
    unittest.main()
