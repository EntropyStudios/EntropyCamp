const fs=require('node:fs'),assert=require('node:assert/strict');
const C=require('./wbs-core.js'),source=fs.readFileSync(__dirname+'/wbs.js','utf8');
function extract(name,next,context){const code=source.slice(source.indexOf('  function '+name+'('),source.indexOf('  function '+next+'('));return new Function(...Object.keys(context),code+';return '+name)(...Object.values(context));}
const issue=(id,more={})=>({id,title:id,status:'In Progress',statusType:'started',duration:2,blockedBy:[],...more});
const a=issue('MOTION-1'),b=issue('MOTION-2',{blockedBy:[a.id]});
const plan=C.cpm([a,b],[a,b]);
for(const hidden of [a.id,b.id]){
 const render=extract('renderNetwork','renderGantt',{visible:i=>i.id!==hidden,card:i=>`<article data-test="${i.id}"></article>`,zoom:1});
 const html=render(plan);
 assert.ok(!html.includes('marker-end="url(#arrow)"'),'No edge may point at a filtered-out node');
 assert.ok(html.includes('隐藏'),'Explain that filtering hides dependency edges');
 assert.ok(!html.includes(`data-test="${hidden}"`));
}
const renderAll=extract('renderNetwork','renderGantt',{visible:()=>true,card:i=>`<article>${i.id}</article>`,zoom:1});
assert.ok(renderAll(plan).includes('marker-end="url(#arrow)"'));
for(const scope of ['',a.id]){
 const render=extract('renderLinks','render',{C,prefs:{scope},shownRoots:()=>[a,b],data:{links:{}},records:[],performanceError:'',esc:String,field:()=>'',date:String});
 const html=render();assert.ok(html.includes(a.id));assert.equal(html.includes(b.id),!scope);
}
console.log('WBS view filters: visible edges and scoped reconciliation passed');
