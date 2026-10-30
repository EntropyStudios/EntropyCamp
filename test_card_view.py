import subprocess
import unittest
from pathlib import Path


class CardViewTests(unittest.TestCase):
    def test_default_cards_render_without_webgl_and_reuse_unchanged_markup(self):
        script=r'''
const fs=require('fs'),vm=require('vm'),assert=require('node:assert/strict');
const source=fs.readFileSync('app.js','utf8');
const start=source.indexOf('function render(options');
const render=source.slice(start,source.indexOf('\nasync function updateClocks',start));
let writes=0,html='',disposed=0;
const grid={dataset:{},classList:{toggle(){},add(){},remove(){}},setAttribute(){},get innerHTML(){return html;},set innerHTML(v){html=v;writes++;}};
const context={REMINDER_PRESENTATION:'cards',grid,Map,Date,cards:[{id:'a'}],workSession:{active:true},cardOrderCore:{sortCards:c=>c},getCardState:()=> 'codex',snapshotCardRects:()=>new Map(),ensureActiveWorkBaselines(){},renderWorkSession(){},queueWidgetSnapshotSync(){},document:{body:{classList:{toggle(){}}}},reminderCardsMarkup:()=>'<article>Task</article>',animateCardLayout(){},cancelAnimationFrame(){},requestAnimationFrame(){throw Error('Cards must not mount graph');}};
vm.createContext(context);
vm.runInContext('let conversationGraphController={dispose(){}};let conversationGraphMountVersion=0,conversationGraphRenderFrame=0,conversationGraphPending=null;'+render,context);
vm.runInContext('render();render();',context);
assert.equal(writes,1);assert.equal(html,'<article>Task</article>');
assert.equal(vm.runInContext('conversationGraphController',context),null);
assert.ok(source.includes('get("view") === "cosmos" ? "cosmos" : "cards"'));
'''
        result=subprocess.run(['node','-e',script],cwd=Path(__file__).parent,capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
