import subprocess
import unittest
from pathlib import Path


class HomeGraphLifecycleTests(unittest.TestCase):
    def test_repeated_home_renders_keep_one_canvas_and_controller(self):
        script = r"""
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const source=fs.readFileSync('app.js','utf8');
function extract(name){
 let start=source.indexOf('function '+name+'(');
 if(source.slice(start-6,start)==='async ')start-=6;
 return source.slice(start,source.indexOf('\nfunction ',start+1));
}
const classes=()=>{const values=new Set();return {add:(...v)=>v.forEach(x=>values.add(x)),remove:(...v)=>v.forEach(x=>values.delete(x)),
 contains:x=>values.has(x),toggle:(x,v)=>v?values.add(x):values.delete(x)};};
let canvases=0,controllers=0,updates=0,disposed=0,attempts=0;
let shell=null,canvas=null;
const fallback={innerHTML:''};
const grid={classList:classes(),dataset:{},querySelector(selector){
 if(selector==='[data-graph-3d-shell]')return shell;
 if(selector==='.graph-fallback')return fallback;
 return null;
}};
Object.defineProperty(grid,'innerHTML',{set(value){
 if(shell)shell.isConnected=false;
 canvas={id:++canvases};
 shell={isConnected:true,querySelector:selector=>selector==='canvas'?canvas:null};
}});
let next=0;const frames=new Map();
const context={grid,document:{hidden:false,body:{classList:classes()}},Date,Map,
 cards:[{id:'t',kind:'thread',state:'processing'}],workSession:{active:true},
 cardOrderCore:{sortCards:cards=>cards},getCardState:()=> 'processing',
 graph3DMarkup:()=>'<canvas>',graphMarkup:()=>'<article>',graph3DNodes:cards=>cards,
 graph3DSolarState:()=>({mode:'working',event:'none',token:'start:1',dayProgress:.5,cycleOffsetMs:8*60*60*1000,sampledAt:Date.now()}),
 shouldReduceMotion:()=>false,snapshotCardRects:()=>new Map(),ensureActiveWorkBaselines(){},renderWorkSession(){},
 queueWidgetSnapshotSync(){},animateCardLayout(){},updateGraphConnections(){},showGraphNodeInspector(){},
 recycleCompletedCard(){return true;},
 requestAnimationFrame:cb=>{const id=++next;frames.set(id,cb);return id;},cancelAnimationFrame:id=>frames.delete(id),
 console:{warn(){}},
 loadGraphModule:async()=>({createConversationGraph(){
   attempts++;controllers++;
   return {camera:{angle:0},update(){updates++;},dispose(){disposed++;},getSelectedNode:()=>null,setActive(){}};
 }}),
};
vm.createContext(context);
vm.runInContext('let reminderViewMode="cosmos",conversationGraphController=null,conversationGraphMountVersion=0,conversationGraphMountPromise=null,conversationGraphPending=null,conversationGraphRenderFrame=0,conversationGraphDisposed=false;\n'+
 extract('mountConversationGraph').replace('await import("./graph-3d.js")','await loadGraphModule()')+'\n'+extract('render'),context);
async function paint(){const batch=[...frames.values()];frames.clear();batch.forEach(cb=>cb(16));await new Promise(setImmediate);}
(async()=>{
 vm.runInContext('render()',context);await paint();
 vm.runInContext('conversationGraphController.camera.angle=1.2',context);
 for(let i=0;i<200;i++){
  context.cards[0].phaseLabel=i%2?'tool':'reasoning';
  vm.runInContext('render();render()',context);await paint();
 }
 console.log(JSON.stringify({canvases,controllers,updates,disposed}));
 assert.strictEqual(canvases,1,'home render replaced the canvas');
 assert.strictEqual(controllers,1,'home render created additional WebGL controllers');
 assert.strictEqual(disposed,0,'live controller was torn down');
 assert.strictEqual(vm.runInContext('conversationGraphController.camera.angle',context),1.2);
 assert.ok(updates>=200);
 assert.ok(updates<=201,'same-frame renders were not coalesced');
 console.log(JSON.stringify({canvases,controllers,updates,disposed}));
})().catch(e=>{console.error(e);process.exitCode=1;});
"""
        result = subprocess.run(["node", "-e", script], cwd=Path(__file__).parent, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


GRAPH_MOCKS = r"""
import fs from 'node:fs';
import assert from 'node:assert/strict';
import * as actualThree from './assets/vendor/three.module.js';
let rendererCount=0,disposeCount=0,lossCount=0,renderTargetCount=0,renderTargetDisposeCount=0,sizeCalls=0,observers=0,failTexture=false,failObserve=false;
class Element {
 constructor(tag='div'){this.tag=tag;this.children=[];this.dataset={};this.style={setProperty(){}};
  this.classList={toggle(){}};this.handlers=new Map();this.offsetWidth=120;this.offsetHeight=28;}
 append(...items){items.forEach(item=>{item.parent=this;this.children.push(item);});}
 remove(){if(this.parent)this.parent.children=this.parent.children.filter(item=>item!==this);this.parent=null;}
 replaceChildren(){this.children.forEach(item=>item.parent=null);this.children=[];}
 setAttribute(){} focus(){} setPointerCapture(){} releasePointerCapture(){}
 addEventListener(type,handler){this.handlers.set(type,handler);}
 removeEventListener(type){this.handlers.delete(type);}
 querySelector(tag){return this.children.find(item=>item.tag===tag)||null;}
 getBoundingClientRect(){return {width:1200,height:680,left:0,top:0};}
 getContext(){return failTexture?null:{createImageData:(w,h)=>({data:new Uint8ClampedArray(w*h*4)}),putImageData(){}};}
}
globalThis.document={createElement:tag=>new Element(tag),hidden:false};
globalThis.window={devicePixelRatio:1.3};
const frames=new Map();let nextFrame=0;
globalThis.requestAnimationFrame=fn=>{const id=++nextFrame;frames.set(id,fn);return id;};
globalThis.cancelAnimationFrame=id=>frames.delete(id);
globalThis.ResizeObserver=class {
 observe(){if(failObserve)throw new Error('observe failed');if(!this.observed){this.observed=true;observers++;}}
 disconnect(){if(this.observed){this.observed=false;observers--;}}
};
class TrackballControls {
 constructor(camera,canvas){this.object=camera;this.canvas=canvas;this.target=new actualThree.Vector3();this.autoRotate=false;
  this.minDistance=0;this.maxDistance=Infinity;this.minPolarAngle=0;this.maxPolarAngle=Math.PI;
  this.minAzimuthAngle=-Infinity;this.maxAzimuthAngle=Infinity;}
 update(){this.object.lookAt(this.target);return true;}
 handleResize(){}
 dispose(){}
}
globalThis.__TrackballControls=TrackballControls;
function step(now){const callbacks=[...frames.values()];frames.clear();callbacks.forEach(fn=>fn(now));}
class Renderer {
 constructor({canvas}){rendererCount++;this.canvas=canvas;this.ratio=1;this.geometries=new Set();this.textures=new Set();
  this.info={memory:{geometries:0,textures:0},programs:[]};this.context={lost:false,isContextLost(){return this.lost;}};}
 setPixelRatio(ratio){this.ratio=ratio;}
 getPixelRatio(){return this.ratio;}
 setClearColor(){}
 setSize(w,h){sizeCalls++;this.canvas.width=w*this.ratio;this.canvas.height=h*this.ratio;}
 getContext(){return this.context;}
 setRenderTarget(target){this.target=target;}
 render(scene,camera){
  scene.updateMatrixWorld(true);camera.updateMatrixWorld(true);
  scene.traverse(object=>{
   if(object.geometry&&!this.geometries.has(object.geometry)){
    const geometry=object.geometry;this.geometries.add(geometry);
    geometry.addEventListener('dispose',()=>{this.geometries.delete(geometry);this.info.memory.geometries=this.geometries.size;});
   }
   const texture=object.material?.map;
   if(texture&&!this.textures.has(texture)){
    this.textures.add(texture);texture.addEventListener('dispose',()=>{this.textures.delete(texture);this.info.memory.textures=this.textures.size;});
   }
  });
  this.info.memory={geometries:this.geometries.size,textures:this.textures.size};
 }
 dispose(){disposeCount++;this.geometries.clear();this.textures.clear();this.info.memory={geometries:0,textures:0};}
 forceContextLoss(){lossCount++;this.context.lost=true;}
}
class RenderTarget extends actualThree.WebGLRenderTarget {
 constructor(...args){super(...args);renderTargetCount++;this.disposedForTest=false;}
 dispose(){if(!this.disposedForTest){this.disposedForTest=true;renderTargetDisposeCount++;}super.dispose();}
}
globalThis.__three={...actualThree,WebGLRenderer:Renderer,WebGLRenderTarget:RenderTarget};
const source=fs.readFileSync('graph-3d.js','utf8').replace('import * as THREE from "./assets/vendor/three.module.js";', 'const THREE=globalThis.__three;');
const executableSource=source.replace('import { TrackballControls } from "./assets/vendor/addons/controls/TrackballControls.js";', 'const TrackballControls=globalThis.__TrackballControls;');
const {createConversationGraph}=await import('data:text/javascript;base64,'+Buffer.from(executableSource).toString('base64'));
const original=[
 {id:'t0',kind:'thread',cardId:'t0',label:'Task 0',state:'processing',working:true,shattered:false,
  planetKey:'timber-hearth',planetSequence:0,effort:'low',statusLabel:'Working',phaseLabel:'Reasoning'},
 {id:'t1',kind:'thread',cardId:'t1',label:'Task 1',state:'attention',working:false,shattered:false,
  planetKey:'giants-deep',planetSequence:1,effort:'',statusLabel:'Watching',phaseLabel:'Watching'}];
"""


class RendererGraphLifecycleTests(unittest.TestCase):
    def run_graph(self, script):
        result = subprocess.run(["node", "--input-type=module", "-e", GRAPH_MOCKS + script], cwd=Path(__file__).parent,
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_metadata_update_keeps_gpu_objects_view_and_selection(self):
        self.run_graph(r"""
const canvas=new Element('canvas'),container=new Element();container.append(canvas);
const selected=[];
const graph=createConversationGraph({canvas,container,nodes:original,onNodeSelect:node=>selected.push(node?.label||null)});
step(16);step(32);
canvas.handlers.get('pointerdown')({clientX:0,clientY:0,pointerId:1});
canvas.handlers.get('pointermove')({clientX:40,clientY:20,pointerId:1});
canvas.handlers.get('pointerup')({pointerId:1});
graph.selectNode('t0');
const before=graph.getDiagnostics(),initialSizeCalls=sizeCalls;
const objects=[...graph.scene.children[0].children[0].children];
for(let i=0;i<500;i++){
 graph.update({nodes:original.map(node=>({...node,label:node.id==='t0'?'Updated '+i:node.label,
  phaseLabel:i%2?'Tool':'Reasoning',effort:i%2?'low':'max'}))});
 graph.renderOnce();
}
const after=graph.getDiagnostics();
assert.equal(rendererCount,1);assert.equal(lossCount,0);
assert.equal(container.dataset.graphRendererGeneration,'1');
assert.equal(Number(container.dataset.graphUpdateCount),501);
assert.equal(after.geometries,before.geometries);assert.equal(after.textures,before.textures);
assert.deepEqual(after.rotation,before.rotation);assert.deepEqual(after.camera,before.camera);
assert.equal(after.elapsed,before.elapsed);assert.equal(after.selectedId,'t0');
assert.deepEqual([...graph.scene.children[0].children[0].children],objects);
assert.equal(sizeCalls,initialSizeCalls,'metadata update resized the drawing buffer');
assert.equal(graph.getSelectedNode().label,'Updated 499');
assert.equal(selected.at(-1),'Updated 499');
graph.dispose();graph.dispose();
assert.equal(disposeCount,1);assert.equal(lossCount,1);assert.equal(observers,0);assert.equal(frames.size,0);
assert.equal(renderTargetCount,1);assert.equal(renderTargetDisposeCount,1);
assert.equal(canvas.handlers.size,0);assert.equal(canvas.width,1);assert.equal(canvas.height,1);
assert.equal(container.children.length,1);
""")

    def test_active_phase_is_shown_on_sun_not_working_planet(self):
        self.run_graph(r"""
const canvas=new Element('canvas'),container=new Element();container.append(canvas);
const nodes=original.map(node=>node.id==='t0'
 ? {...node,statusLabel:'处理中',phaseLabel:'推理中',modelLabel:'GPT-5.6-sol',runtimeLabel:'8秒'}
 : node);
const graph=createConversationGraph({canvas,container,nodes});graph.renderOnce(.05);
assert.equal(graph.getDiagnostics().sunRadius,2.5,'sun is not 1.25x its previous radius');
function descendants(node){return [node,...(node.children||[]).flatMap(descendants)]}
const elements=descendants(container);
const planetLabel=elements.find(item=>item.className?.includes('is-thread')&&item.dataset.graphLabel==='t0');
const sunLabel=elements.find(item=>item.className?.includes('is-sun'));
assert.ok(planetLabel);assert.ok(sunLabel);
assert.equal(planetLabel.children[0].textContent,'Task 0');
assert.equal(planetLabel.children[1].textContent,'','working planet repeated the active phase');
assert.equal(sunLabel.children[1].textContent,'推理中 · 1 个任务');
assert.equal(container.dataset.graphSunStatus,'推理中 · 1 个任务');
graph.dispose();
""")

    def test_planet_rebirth_updates_one_node_without_rebuilding_scene(self):
        self.run_graph(r"""
const canvas=new Element('canvas'),container=new Element();container.append(canvas);
const completed=original.map((node,index)=>({...node,working:false,state:'due',shattered:true,
  completionToken:`turn-${index}`,statusLabel:'Done'}));
const graph=createConversationGraph({canvas,container,nodes:completed});graph.renderOnce(.05);
function descendants(node){return [node,...(node.children||[]).flatMap(descendants)]}
const beforeLabel=descendants(container).find(item=>item.className?.includes('is-thread')&&item.dataset.graphLabel==='t0');
const before=graph.getDiagnostics();
const reborn=completed.map(node=>node.id==='t0'?{...node,shattered:false,state:'attention',completionToken:'',
  planetKey:'dark-bramble',planetSequence:9,rebirthAt:Date.now(),statusLabel:'Watching'}:node);
graph.update({nodes:reborn});graph.renderOnce(.05);
const afterLabel=descendants(container).find(item=>item.className?.includes('is-thread')&&item.dataset.graphLabel==='t0');
const after=graph.getDiagnostics(),state=after.nodeStates.find(node=>node.id==='t0');
assert.equal(afterLabel,beforeLabel,'planet change rebuilt every graph label');
assert.equal(rendererCount,1);assert.equal(lossCount,0);
assert.deepEqual(after.camera,before.camera,'planet rebirth reset the camera');
assert.equal(state.planetKey,'dark-bramble');
assert.equal(state.lifecycle,'eject');
graph.dispose();
""")

    def test_work_end_finale_and_next_start_rewind_without_renderer_rebuild(self):
        self.run_graph(r"""
const canvas=new Element('canvas'),container=new Element();container.append(canvas);
const sampledAt=Date.now();
const graph=createConversationGraph({canvas,container,nodes:original,
 solarState:{mode:'working',event:'work-started',token:'start:1',dayProgress:.25,cycleOffsetMs:4*60*60*1000,sampledAt}});
graph.renderOnce(.05);
let state=graph.getDiagnostics();
assert.equal(state.solarMode,'working');assert.ok(Math.abs(state.sunScale-2.8125)<.01);assert.equal(state.globalExplode,0);
const beforeCamera=state.camera;
graph.update({nodes:original,solarState:{mode:'destroyed',event:'work-ended',token:'end:2',dayProgress:.25,cycleOffsetMs:4*60*60*1000,sampledAt}});
for(let index=0;index<170;index++)graph.renderOnce(.05);
state=graph.getDiagnostics();
assert.equal(state.solarMode,'destroyed');assert.equal(state.globalExplode,1);assert.ok(state.sunScale<.3);
assert.ok(state.nodeStates.every(node=>node.explode>.99));
graph.update({nodes:original.map(node=>({...node,shattered:false,completionToken:''})),
 solarState:{mode:'working',event:'work-started',token:'start:3',dayProgress:.5,cycleOffsetMs:8*60*60*1000,sampledAt}});
for(let index=0;index<170;index++)graph.renderOnce(.05);
state=graph.getDiagnostics();
assert.equal(state.solarMode,'working');assert.ok(Math.abs(state.sunScale-3.125)<.01);assert.equal(state.globalExplode,0);
assert.ok(state.nodeStates.every(node=>node.explode<.01));
assert.equal(rendererCount,1);assert.equal(lossCount,0);assert.deepEqual(state.camera,beforeCamera);
graph.dispose();
""")

    def test_structure_and_state_churn_disposes_old_scene_resources(self):
        self.run_graph(r"""
const canvas=new Element('canvas'),container=new Element();container.append(canvas);
const graph=createConversationGraph({canvas,container,nodes:original});graph.renderOnce();
const before=graph.getDiagnostics();
assert.equal(container.dataset.graphSunStatus,'Reasoning · 1 个任务');
for(let i=0;i<60;i++){
 graph.update({nodes:[original[0],{...original[1],state:'attention',modelId:null},
  {id:'new-'+i,kind:'thread',label:'Countdown',state:'countdown',statusLabel:'Waiting'}]});
 graph.renderOnce();
 graph.update({nodes:original});graph.renderOnce();
 assert.equal(graph.getDiagnostics().geometries,before.geometries);
 assert.equal(graph.getDiagnostics().textures,before.textures);
}
assert.equal(rendererCount,1);assert.equal(lossCount,0);
graph.selectNode('t0');graph.update({nodes:[original[1]]});
assert.equal(graph.getSelectedNode(),null);
graph.setActive(false);assert.equal(frames.size,0);
graph.setActive(true);graph.setActive(true);assert.equal(frames.size,1);
graph.dispose();assert.equal(lossCount,1);assert.equal(observers,0);
""")

    def test_failed_initialization_releases_context_and_partial_resources(self):
        self.run_graph(r"""
const canvas=new Element('canvas'),container=new Element();container.append(canvas);
failObserve=true;
assert.throws(()=>createConversationGraph({canvas,container,nodes:original}));
assert.equal(rendererCount,1);assert.equal(disposeCount,1);assert.equal(lossCount,1);
assert.equal(renderTargetCount,1);assert.equal(renderTargetDisposeCount,1);
assert.equal(frames.size,0);assert.equal(observers,0);assert.equal(canvas.handlers.size,0);
assert.equal(container.children.length,1);assert.equal(canvas.width,1);
""")

    def test_completion_persists_as_cloud_until_recycled(self):
        self.run_graph(r"""
const canvas=new Element('canvas'),container=new Element();container.append(canvas);
const recycled=[];
const graph=createConversationGraph({canvas,container,nodes:original,onNodeRecycle:node=>{recycled.push(node.id);return true;}});
graph.renderOnce(0.05);
let initial=graph.getDiagnostics().nodeStates;
assert.equal(initial.find(node=>node.id==='t0').scale,.5625,'working planet is not 1.5x its idle display size');
assert.ok(Math.abs(initial.find(node=>node.id==='t1').scale-1.06875)<1e-9,'Giant Deep idle display scale is not 0.75x');
const completed=original.map(node=>node.id==='t0'
 ? {...node,state:'due',working:false,shattered:true,completionToken:'codex:turn-1',statusLabel:'Done'} : node);
graph.update({nodes:completed});
for(let i=0;i<40;i++)graph.renderOnce(0.05);
let state=graph.getDiagnostics().nodeStates.find(node=>node.id==='t0');
assert.equal(state.shattered,true);assert.ok(state.explode>.99);assert.equal(state.lifecycle,'');
assert.ok(Math.abs(state.scale-.46875)<.001,'fragment cloud is not scaled proportionally to 1.875x');
graph.update({nodes:completed.map(node=>node.id==='t0'?{...node,state:'attention'}:node)});
for(let i=0;i<10;i++)graph.renderOnce(0.05);
state=graph.getDiagnostics().nodeStates.find(node=>node.id==='t0');
assert.equal(state.shattered,true,'clearing due incorrectly restored the cloud');
assert.equal(graph.recycleNode('t0'),true);
for(let i=0;i<24;i++)graph.renderOnce(0.05);
await new Promise(setImmediate);
assert.deepEqual(recycled,['t0']);
graph.dispose();
""")

    def test_two_fragment_clouds_can_be_absorbed_concurrently(self):
        self.run_graph(r"""
const canvas=new Element('canvas'),container=new Element();container.append(canvas);
const completed=original.map((node,index)=>({...node,working:false,state:'due',shattered:true,
  completionToken:`turn-${index}`,statusLabel:'Done'}));
const recycled=[];
const graph=createConversationGraph({canvas,container,nodes:completed,onNodeRecycle:node=>{recycled.push(node.id);return true;}});
graph.renderOnce(.05);
assert.equal(graph.recycleNode('t0'),true);assert.equal(graph.recycleNode('t1'),true);
let states=graph.getDiagnostics().nodeStates;
assert.equal(states.find(node=>node.id==='t0').lifecycle,'absorbing');
assert.equal(states.find(node=>node.id==='t1').lifecycle,'absorbing');
for(let index=0;index<24;index++)graph.renderOnce(.05);
await new Promise(setImmediate);
assert.deepEqual(recycled.sort(),['t0','t1']);
assert.equal(rendererCount,1);assert.equal(lossCount,0);
graph.dispose();
""")

    def test_giants_deep_display_scale_is_halved_in_every_state(self):
        self.run_graph(r"""
const canvas=new Element('canvas'),container=new Element();container.append(canvas);
const graph=createConversationGraph({canvas,container,nodes:original});graph.renderOnce(.05);
let state=graph.getDiagnostics().nodeStates.find(node=>node.id==='t1');
assert.ok(Math.abs(state.scale-1.06875)<1e-9,'idle scale');
graph.update({nodes:original.map(node=>node.id==='t1'?{...node,working:true,state:'processing'}:node)});
for(let i=0;i<60;i++)graph.renderOnce(.05);
state=graph.getDiagnostics().nodeStates.find(node=>node.id==='t1');
assert.ok(Math.abs(state.scale-1.603125)<.001,'working scale');
graph.update({nodes:original.map(node=>node.id==='t1'?{...node,working:false,shattered:true,state:'due',completionToken:'timer:1'}:node)});
for(let i=0;i<60;i++)graph.renderOnce(.05);
state=graph.getDiagnostics().nodeStates.find(node=>node.id==='t1');
assert.ok(Math.abs(state.scale-1.3359375)<.001,'fragment scale');
graph.dispose();
""")

    def test_stranger_display_scale_is_three_quarters_in_every_state(self):
        self.run_graph(r"""
const canvas=new Element('canvas'),container=new Element();container.append(canvas);
const stranger={...original[1],id:'stranger-task',planetKey:'stranger',planetSequence:7};
const graph=createConversationGraph({canvas,container,nodes:[stranger]});graph.renderOnce(.05);
let state=graph.getDiagnostics().nodeStates[0];
assert.ok(Math.abs(state.scale-.9)<1e-9,'idle Stranger scale');
graph.update({nodes:[{...stranger,working:true,state:'processing'}]});
for(let index=0;index<60;index++)graph.renderOnce(.05);
state=graph.getDiagnostics().nodeStates[0];assert.ok(Math.abs(state.scale-1.35)<.001,'working Stranger scale');
graph.update({nodes:[{...stranger,working:false,shattered:true,state:'due',completionToken:'turn:1'}]});
for(let index=0;index<60;index++)graph.renderOnce(.05);
state=graph.getDiagnostics().nodeStates[0];assert.ok(Math.abs(state.scale-1.125)<.001,'fragment Stranger scale');
graph.dispose();
""")
