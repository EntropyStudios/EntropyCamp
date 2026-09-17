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
 shouldReduceMotion:()=>false,snapshotCardRects:()=>new Map(),ensureActiveWorkBaselines(){},renderWorkSession(){},
 queueWidgetSnapshotSync(){},animateCardLayout(){},updateGraphConnections(){},showGraphNodeInspector(){},
 requestAnimationFrame:cb=>{const id=++next;frames.set(id,cb);return id;},cancelAnimationFrame:id=>frames.delete(id),
 console:{warn(){}},
 loadGraphModule:async()=>({createConversationGraph(){
   attempts++;controllers++;
   return {camera:{angle:0},update(){updates++;},dispose(){disposed++;},getSelectedNode:()=>null,setActive(){}};
 }}),
};
vm.createContext(context);
vm.runInContext('let conversationGraphController=null,conversationGraphMountVersion=0,conversationGraphMountPromise=null,conversationGraphPending=null,conversationGraphRenderFrame=0,conversationGraphDisposed=false;\n'+
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
let rendererCount=0,disposeCount=0,lossCount=0,sizeCalls=0,observers=0,failTexture=false;
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
 observe(){if(!this.observed){this.observed=true;observers++;}}
 disconnect(){if(this.observed){this.observed=false;observers--;}}
};
function step(now){const callbacks=[...frames.values()];frames.clear();callbacks.forEach(fn=>fn(now));}
class Renderer {
 constructor({canvas}){rendererCount++;this.canvas=canvas;this.ratio=1;this.geometries=new Set();this.textures=new Set();
  this.info={memory:{geometries:0,textures:0},programs:[]};this.context={lost:false,isContextLost(){return this.lost;}};}
 setPixelRatio(ratio){this.ratio=ratio;}
 getPixelRatio(){return this.ratio;}
 setClearColor(){}
 setSize(w,h){sizeCalls++;this.canvas.width=w*this.ratio;this.canvas.height=h*this.ratio;}
 getContext(){return this.context;}
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
globalThis.__three={...actualThree,WebGLRenderer:Renderer};
const source=fs.readFileSync('graph-3d.js','utf8').replace('import * as THREE from "./assets/vendor/three.module.js";', 'const THREE=globalThis.__three;');
const {createConversationGraph}=await import('data:text/javascript;base64,'+Buffer.from(source).toString('base64'));
const original=[{id:'model',kind:'model',label:'Model',threadCount:2},
 {id:'t0',kind:'thread',label:'Task 0',state:'processing',modelId:'model',effort:'low',statusLabel:'Working',phaseLabel:'Reasoning'},
 {id:'t1',kind:'thread',label:'Task 1',state:'processing',modelId:'model',effort:'max',statusLabel:'Working',phaseLabel:'Tool'}];
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
canvas.handlers.get('wheel')({deltaY:100,preventDefault(){}});
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
assert.equal(canvas.handlers.size,0);assert.equal(canvas.width,1);assert.equal(canvas.height,1);
assert.equal(container.children.length,1);
""")

    def test_structure_and_state_churn_disposes_old_scene_resources(self):
        self.run_graph(r"""
const canvas=new Element('canvas'),container=new Element();container.append(canvas);
const graph=createConversationGraph({canvas,container,nodes:original});graph.renderOnce();
const before=graph.getDiagnostics();
for(let i=0;i<60;i++){
 graph.update({nodes:[original[0],{...original[1],state:'attention',modelId:null},
  {id:'new-'+i,kind:'thread',label:'Countdown',state:'countdown',statusLabel:'Waiting'}]});
 graph.renderOnce();
 graph.update({nodes:original});graph.renderOnce();
 assert.equal(graph.getDiagnostics().geometries,before.geometries);
 assert.equal(graph.getDiagnostics().textures,before.textures);
}
assert.equal(rendererCount,1);assert.equal(lossCount,0);
graph.selectNode('t0');graph.update({nodes:[original[0]]});
assert.equal(graph.getSelectedNode(),null);
graph.setActive(false);assert.equal(frames.size,0);
graph.setActive(true);graph.setActive(true);assert.equal(frames.size,1);
graph.dispose();assert.equal(lossCount,1);assert.equal(observers,0);
""")

    def test_failed_initialization_releases_context_and_partial_resources(self):
        self.run_graph(r"""
const canvas=new Element('canvas'),container=new Element();container.append(canvas);
failTexture=true;
assert.throws(()=>createConversationGraph({canvas,container,nodes:original}));
assert.equal(rendererCount,1);assert.equal(disposeCount,1);assert.equal(lossCount,1);
assert.equal(frames.size,0);assert.equal(observers,0);assert.equal(canvas.handlers.size,0);
assert.equal(container.children.length,1);assert.equal(canvas.width,1);
""")
