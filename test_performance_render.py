"""Exercise card reconciliation without touching real business data."""
import subprocess
import unittest
from pathlib import Path


class PerformanceRenderTests(unittest.TestCase):
    def test_refresh_preserves_nodes_and_only_changes_updated_cards(self):
        script = Path(__file__).with_name("performance.js").read_text()
        render = script[script.index("  function renderRecords(items)"):script.index("  async function load(")]
        harness = r'''
const assert = require('node:assert/strict');
let writes = 0, moves = 0;
class Card {
  constructor(){this.dataset={};this.content='';}
  set innerHTML(value){writes++;this.content=value;}
  get nextElementSibling(){return list.children[list.children.indexOf(this)+1] || null;}
  remove(){list.children.splice(list.children.indexOf(this),1);}
}
const list={children:[],get firstElementChild(){return this.children[0] || null;},
 insertBefore(node,before){moves++;if(this.children.includes(node))node.remove();const i=before ? this.children.indexOf(before) : this.children.length;this.children.splice(i,0,node);}};
const document={createElement:()=>new Card()};
const empty={hidden:false}, $=()=>empty;
const ids={status:'s',due:'d',department:'dept',title:'t',people:'p'};
const field=(r,id)=>r.fields[id], text=v=>String(v ?? '—'), esc=v=>String(v ?? ''), date=v=>String(v), today=()=> '2026-10-09';
'''
        cases = r'''
const a={record_id:'a',fields:{t:'A',s:'进行中'}},b={record_id:'b',fields:{t:'B',s:'进行中'}};
renderRecords([a,b]);const originals=[...list.children];
assert.equal(writes,2);assert.equal(moves,2);
renderRecords(JSON.parse(JSON.stringify([a,b])));
assert.equal(writes,2);assert.equal(moves,2);assert.deepEqual(list.children,originals);
renderRecords([a,{...b,fields:{...b.fields,t:'Updated'}}]);
assert.equal(writes,3);assert.deepEqual(list.children,originals);
renderRecords([b,a]);assert.equal(list.children[0],originals[1]);assert.equal(list.children[1],originals[0]);
renderRecords([a]);assert.deepEqual(list.children,[originals[0]]);
renderRecords([]);assert.equal(list.children.length,0);assert.equal(empty.hidden,false);
'''
        result = subprocess.run(["node", "-e", harness + render + cases],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
