"""Run the real header-clock scheduler on a deterministic 240 Hz display."""
import subprocess
import unittest
from pathlib import Path


class ClockEfficiencyTests(unittest.TestCase):
    def test_clock_style_updates_are_scoped_and_stable_values_do_not_rewrite(self):
        script = r'''
const fs=require('fs'),vm=require('vm'),assert=require('assert/strict');
const source=fs.readFileSync('app.js','utf8');
const a=source.indexOf('function setHeaderClockStyle('),b=source.indexOf('\nfunction ',a+1);
let writes=0;function svg(){const values=new Map();return {style:{getPropertyValue:key=>values.get(key)||'',setProperty(key,value){writes++;values.set(key,value);}}};}
const context={corpusClock:svg(),corpusClockSkin:svg(),bigBenClock:svg(),pragueOrlojClock:svg(),bernZytgloggeClock:svg()};
vm.createContext(context);vm.runInContext(source.slice(a,b),context);
for(let i=0;i<600;i++)context.setHeaderClockStyle('--cc-body-angle','1.000deg');
assert.equal(writes,1,'stable SVG property was rewritten every frame');
assert.equal(context.corpusClock.style.getPropertyValue('--cc-body-angle'),'');
assert.equal(context.corpusClockSkin.style.getPropertyValue('--cc-body-angle'),'1.000deg');
context.setHeaderClockStyle('--cc-body-angle','1.001deg');assert.equal(writes,2);
for(const [prefix,target] of [['bb','bigBenClock'],['orloj','pragueOrlojClock'],['zyt','bernZytgloggeClock']]){
 context.setHeaderClockStyle('--'+prefix+'-angle','2deg');
 assert.equal(context[target].style.getPropertyValue('--'+prefix+'-angle'),'2deg');
}
'''
        result = subprocess.run(['node', '-e', script], cwd=Path(__file__).parent, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_idle_clocks_tick_once_a_second_and_mechanisms_keep_sixty_fps(self):
        script = r'''
const fs=require('fs'),vm=require('vm'),assert=require('assert/strict');
const source=fs.readFileSync('app.js','utf8');
function extract(name){const a=source.indexOf('function '+name+'(');if(a<0)return '';return source.slice(a,source.indexOf('\nfunction ',a+1));}
function run(skin,mechanism,hidden=false){
 let clock=0,next=0,calls=0;const timers=new Map(),frames=new Map();
 const context={document:{visibilityState:hidden?'hidden':'visible'},corpusClock:{},activeHeaderClockId:skin,
  HEADER_CLOCK_FRAME_INTERVAL_MS:1000/60,HEADER_CLOCK_WAKE_AHEAD_MS:1,
  corpusClockAnimationFrame:null,corpusClockAnimationTimer:null,corpusClockLastFrameAt:null,
  shouldReduceMotion:()=>false,displayTimeParts:date=>({millisecond:date.getTime()%1000}),
  corpusClockRenderDate:()=>new Date(clock),
  pragueOrlojAutomatonState:()=>({active:mechanism}),bernZytgloggeAutomatonState:()=>({active:mechanism}),
  HEADER_CLOCK_RUNTIMES:{[skin]:{frame(){calls++;}}},
  requestAnimationFrame(fn){const id=++next;frames.set(id,fn);return id;},cancelAnimationFrame(id){frames.delete(id);},
  setTimeout(fn,wait){const id=++next;timers.set(id,{fn,due:clock+wait});return id;},clearTimeout(id){timers.delete(id);}};
 vm.createContext(context);vm.runInContext(['headerClockFrameInterval','scheduleCorpusClockFrame','runCorpusClockFrame','startCorpusClockAnimation','stopCorpusClockAnimation'].map(extract).join('\n'),context);
 context.startCorpusClockAnimation();
 for(let tick=0;tick<=2400;tick++){
  clock=tick*1000/240;
  for(const [id,timer] of [...timers])if(timer.due<=clock){timers.delete(id);timer.fn();}
  const batch=[...frames.values()];frames.clear();batch.forEach(fn=>fn(clock));
  assert.ok(timers.size+frames.size<=1,'clock created duplicate loops');
 }
 context.stopCorpusClockAnimation();assert.equal(timers.size+frames.size,0);
 return calls;
}
const idle=run('prague-orloj',false),bern=run('bern-zytglogge',false);
const parade=run('prague-orloj',true),corpus=run('corpus',false),bigBen=run('big-ben',false);
console.log(JSON.stringify({idle,bern,parade,corpus,bigBen}));
assert.ok(idle>=10&&idle<=12,`idle Prague performed ${idle} updates in 10 seconds`);
assert.ok(bern>=10&&bern<=12,`idle Bern performed ${bern} updates in 10 seconds`);
for(const value of [parade,corpus,bigBen])assert.ok(value>=580&&value<=610,'continuous mechanism no longer smooth');
assert.equal(run('corpus',false,true),0);
'''
        result = subprocess.run(['node', '-e', script], cwd=Path(__file__).parent, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
