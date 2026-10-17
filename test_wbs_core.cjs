const assert=require('node:assert/strict');
const C=require('./wbs-core.js');
const item=(id,more={})=>({id,title:id,status:'Todo',statusType:'unstarted',duration:1,blockedBy:[],...more});
let rows=[item('P'),item('A',{parentId:'P',duration:2}),item('B',{parentId:'P',duration:3,blockedBy:['A']})];
let g=C.graph(rows);assert.equal(g.rootOf('B').id,'P');assert.equal(g.descendants('P').length,2);
let p=C.cpm(rows.slice(1),rows);assert.equal(p.total,5);assert.equal(p.nodes.find(i=>i.id==='B').level,1);assert.ok(p.valid);
// Parentage is never a dependency edge or extra duration.
p=C.cpm(rows,rows);assert.equal(p.edges.length,1);assert.equal(p.total,5);
p=C.cpm([item('A',{duration:null})],[]);assert.equal(p.total,null);assert.equal(p.nodes[0].critical,false);
p=C.cpm([item('A',{blockedBy:['OTHER']})],[]);assert.equal(p.valid,false);assert.equal(p.external.length,1);
p=C.cpm([item('A',{specDependencies:['OTHER']})],[]);assert.equal(p.valid,false);
p=C.cpm([item('A',{blockedBy:['B']}),item('B',{blockedBy:['A']})],[]);assert.equal(p.cycle,true);assert.equal(p.total,null);
assert.equal(C.status(item('A')),'待接取');assert.equal(C.status(item('A',{assignee:'张泽临'})),'已接取·待开始');
assert.equal(C.status(item('A',{status:'Canceled',statusType:'canceled'})),'已取消');assert.equal(C.done(item('A',{statusType:'canceled'})),false);
rows=[item('A',{parentId:'B'}),item('B',{parentId:'A'})];assert.equal(C.graph(rows).rootOf('A'),null);
console.log('WBS hierarchy, status, native dependencies and incomplete CPM checks passed');
const layout=C.hierarchyLayout({id:'p',kind:'project',children:[{id:'m',kind:'module',children:[{id:'a',kind:'issue',children:[{id:'c',kind:'issue'}]},{id:'b',kind:'issue'}]}]});
assert.deepEqual(layout.edges,[{from:'p',to:'m'},{from:'m',to:'a'},{from:'a',to:'c'},{from:'m',to:'b'}]);
const a=layout.nodes.find(n=>n.id==='a'),b=layout.nodes.find(n=>n.id==='b');assert.ok(a.y+a.height<b.y);assert.ok(layout.nodes.find(n=>n.id==='c').x>a.x);
assert.notEqual(C.ownerStyle('李昊洋').color,C.ownerStyle('张泽临').color);assert.equal(C.ownerStyle('').unassigned,true);assert.equal(C.ownerStyle('文子轩').unassigned,false);assert.deepEqual(C.ownerStyle('新同事'),C.ownerStyle('新同事'));
console.log('WBS hierarchy layout and stable owner identifiers passed');
const radial=C.radialLayout({id:'root',kind:'project',children:[{id:'m1',kind:'module',children:[{id:'t1',kind:'issue'}]},{id:'m2',kind:'module',children:[{id:'t2',kind:'issue'}]},{id:'m3',kind:'module',children:[{id:'t3',kind:'issue'}]}]});
assert.equal(radial.edges.length,6);assert.ok(radial.nodes.some(n=>n.x<0));assert.ok(radial.nodes.some(n=>n.x>0));assert.ok(radial.nodes.some(n=>n.y<0));assert.ok(radial.nodes.some(n=>n.y>0));
for(let i=0;i<radial.nodes.length;i++)for(let j=i+1;j<radial.nodes.length;j++){const a=radial.nodes[i],b=radial.nodes[j];assert.ok(Math.abs(a.x-b.x)>=(a.width+b.width)/2 || Math.abs(a.y-b.y)>=(a.height+b.height)/2);}
console.log('Radial WBS nodes spread around project without rectangle overlaps');
