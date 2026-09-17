import subprocess
import unittest
from pathlib import Path


class StateClientTests(unittest.TestCase):
    def test_queue_cross_client_refresh_and_failure_recovery(self):
        script = r"""
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const source=fs.readFileSync('state-client.js','utf8');
const key='lumen-reminder-cards-v1';
let state={initialized:true,revision:1,data:{[key]:[{id:'a',title:'original'}],
 'lumen-reminder-work-session-v1':{active:false},
 'lumen-reminder-work-history-v1':{version:2,entries:[]},
 'lumen-multi-clipboard-v1':{version:1,items:[]}}};
const clone=x=>JSON.parse(JSON.stringify(x));
let failNext=false,posts=0;
async function fetch(path,options){
 if(options.body){
  posts++;
  if(failNext){failNext=false;return {ok:false,json:async()=>({error:'offline'})};}
  const updates=JSON.parse(options.body).updates;
  for(const [key,change] of Object.entries(updates)){
   assert.deepStrictEqual(change.base,state.data[key]);
   state.data[key]=clone(change.value);
  }
  state.revision++;
 }
 return {ok:true,json:async()=>clone(state)};
}
function client(){
 const window={addEventListener(){}};
 const document={hidden:false,querySelector:()=>null,createElement:()=>({setAttribute(){},style:{}}),body:{append(){}},addEventListener(){}};
 const context={window,document,fetch,AbortSignal,setInterval(){},console:{warn(){},error(){}},
  localStorage:{getItem(){throw Error('Initialized server must not read old browser data');},setItem(){throw Error('Business state must not write localStorage');}}};
 vm.createContext(context);vm.runInContext(source,context);
 return window.EntropyState;
}
(async()=>{
 const a=client(),b=client();await Promise.all([a.ready,b.ready]);
 const unchanged=Object.fromEntries(Object.entries(JSON.parse(a.getItem(key))[0]).reverse());
 assert.strictEqual(await a.setItem(key,JSON.stringify([unchanged])),true);
 assert.strictEqual(posts,0);
 const first=a.setItem(key,JSON.stringify([{id:'a',title:'first'}]));
 const second=a.setItem(key,JSON.stringify([{id:'a',title:'second'}]));
 assert.strictEqual(await first,true);assert.strictEqual(await second,true);
 assert.strictEqual(state.data[key][0].title,'second');
 await b.refresh();assert.strictEqual(JSON.parse(b.getItem(key))[0].title,'second');
 failNext=true;
 assert.strictEqual(await a.setItem(key,JSON.stringify([{id:'a',title:'failed'}])),false);
 assert.strictEqual(JSON.parse(a.getItem(key))[0].title,'second');
 assert.strictEqual(await a.setItem(key,a.getItem(key)),true);
 assert.strictEqual(await a.setItem(key,JSON.stringify([{id:'a',title:'recovered'}])),true);
 assert.strictEqual(state.data[key][0].title,'recovered');
 assert.strictEqual(posts,4);
})().catch(e=>{console.error(e);process.exitCode=1;});
"""
        subprocess.run(["node", "-e", script], cwd=Path(__file__).parent, check=True, capture_output=True, text=True)
