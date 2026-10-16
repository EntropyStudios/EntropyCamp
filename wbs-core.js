(function(root){
  'use strict';
  const terminal=i=>['completed','canceled','duplicate'].includes(i.statusType)||['Done','Canceled','Duplicate'].includes(i.status);
  const done=i=>i.statusType==='completed'||i.status==='Done';
  const status=i=>done(i)?'已完成':(['canceled','duplicate'].includes(i.statusType)||['Canceled','Duplicate'].includes(i.status))?'已取消':i.statusType==='backlog'||i.status==='Backlog'?'待排期':i.statusType==='triage'?'待分拣':/review|评审|验收/i.test(i.status)?'待验收':i.statusType==='started'||i.status==='In Progress'?'进行中':i.assignee?'已接取·待开始':'待接取';
  function graph(issues){
    const map=new Map(issues.map(i=>[i.id,i]));
    const children=new Map();
    issues.forEach(i=>{if(i.parentId){if(!children.has(i.parentId))children.set(i.parentId,[]);children.get(i.parentId).push(i);}});
    function rootOf(id){const seen=new Set();let i=map.get(id);while(i?.parentId&&map.has(i.parentId)){if(seen.has(i.id))return null;seen.add(i.id);i=map.get(i.parentId);}return i||null;}
    function descendants(id){let out=[],seen=new Set([id]),q=[id];while(q.length){for(const i of children.get(q.shift())||[]){if(seen.has(i.id))continue;seen.add(i.id);out.push(i);q.push(i.id);}}return out;}
    return {map,children,rootOf,descendants};
  }
  // Parent/child never creates finish-to-start dependencies. Only native blockedBy does.
  function cpm(issues,allIssues){
    const map=new Map(issues.map(i=>[i.id,i])), all=new Map(allIssues.map(i=>[i.id,i]));
    const incoming=new Map(issues.map(i=>[i.id,new Set()])), outgoing=new Map(issues.map(i=>[i.id,[]]));
    const external=[], missing=[], uncertain=[];
    for(const i of issues){
      if(!terminal(i)&&(!Number.isFinite(i.duration)||i.duration<=0))missing.push(i.id);
      for(const dep of i.blockedBy||[]){
        if(map.has(dep)){incoming.get(i.id).add(dep);outgoing.get(dep).push(i.id);}
        else if(!all.has(dep)||!terminal(all.get(dep)))external.push({from:dep,to:i.id});
      }
      for(const dep of i.specDependencies||[])if(!(i.blockedBy||[]).includes(dep))uncertain.push({from:dep,to:i.id});
    }
    const degree=new Map([...incoming].map(([id,s])=>[id,s.size]));
    const queue=issues.filter(i=>!degree.get(i.id)).map(i=>i.id),order=[],level=new Map(),es=new Map(),ef=new Map();
    while(queue.length){const id=queue.shift();order.push(id);const deps=[...incoming.get(id)];level.set(id,Math.max(0,...deps.map(d=>(level.get(d)||0)+1)));es.set(id,Math.max(0,...deps.map(d=>ef.get(d)||0)));ef.set(id,es.get(id)+(terminal(map.get(id))?0:map.get(id).duration||0));for(const next of outgoing.get(id)){degree.set(next,degree.get(next)-1);if(!degree.get(next))queue.push(next);}}
    const cycle=order.length!==issues.length,valid=!cycle&&!missing.length&&!external.length&&!uncertain.length;
    const total=Math.max(0,...ef.values()),ls=new Map(),lf=new Map();
    for(const id of [...order].reverse()){const succ=outgoing.get(id);lf.set(id,succ.length?Math.min(...succ.map(s=>ls.get(s))):total);ls.set(id,lf.get(id)-(terminal(map.get(id))?0:map.get(id).duration||0));}
    return {valid,cycle,missing,external,uncertain,total:valid?total:null,
      nodes:issues.map(i=>({...i,level:level.get(i.id)||0,es:valid?es.get(i.id):null,ef:valid?ef.get(i.id):null,critical:valid&&!terminal(i)&&Math.abs(ls.get(i.id)-es.get(i.id))<1e-8})),
      edges:issues.flatMap(i=>[...incoming.get(i.id)].map(from=>({from,to:i.id}))) };
  }
  function ownerStyle(name){
    const known={'李昊洋':['#72b9ed','昊洋'],'文子轩':['#c4a0ed','子轩'],'张泽临':['#e9ba75','泽临'],'蒋梓欣':['#83c9ac','梓欣']};
    if(!name)return {color:'#9ca3af',initials:'?',name:'待接取',unassigned:true};
    if(known[name])return {color:known[name][0],initials:known[name][1],name,unassigned:false};
    let h=0;for(const ch of name)h=(h*31+ch.charCodeAt(0))>>>0;
    return {color:['#a9b8dd','#d5a8b4','#b5c384','#8ec8ca'][h%4],initials:name.slice(-2),name,unassigned:false};
  }
  // Hierarchy edges express ownership only, never execution dependencies.
  function hierarchyLayout(tree){
    const nodes=[],edges=[];let maxDepth=0;
    function size(n){return Math.max(n.kind==='issue'?192:120,(n.children||[]).reduce((s,c)=>s+size(c)+20,-20));}
    function place(n,depth,top,parent){const span=size(n),height=n.kind==='issue'?176:100;
      const node={...n,children:undefined,x:24+depth*330,y:top+(span-height)/2,width:280,height};
      nodes.push(node);maxDepth=Math.max(maxDepth,depth);if(parent)edges.push({from:parent,to:n.id});
      let y=top;for(const child of n.children||[]){place(child,depth+1,y,n.id);y+=size(child)+20;}
    }
    place(tree,0,24,null);return {nodes,edges,width:(maxDepth+1)*330+24,height:size(tree)+48};
  }
  function radialLayout(tree){
    const nodes=[],edges=[],counts=new Map();
    const count=n=>{const v=(n.children||[]).reduce((sum,c)=>sum+count(c),0)||1;counts.set(n.id,v);return v;};count(tree);
    function place(n,depth,start,end,parent){
      const angle=(start+end)/2,r=depth===0?0:depth===1?500:500+(depth-1)*430;
      nodes.push({...n,children:undefined,x:r*Math.cos(angle),y:r*Math.sin(angle),width:280,height:n.kind==='issue'?176:100,depth});
      if(parent)edges.push({from:parent,to:n.id});
      const kids=n.children||[],total=kids.reduce((s,c)=>s+counts.get(c.id),0);let a=start;
      for(const c of kids){const b=a+(end-start)*counts.get(c.id)/total;place(c,depth+1,a,b,n.id);a=b;}
    }
    place(tree,0,-Math.PI,Math.PI,null);
    // Resolve overlapping rectangles while keeping the project centered.
    for(let step=0;step<100;step++){
      let moved=false;
      for(let a=0;a<nodes.length;a++)for(let b=a+1;b<nodes.length;b++){
        const p=nodes[a],q=nodes[b],dx=q.x-p.x,dy=q.y-p.y;
        const ox=(p.width+q.width)/2+32-Math.abs(dx),oy=(p.height+q.height)/2+32-Math.abs(dy);
        if(ox>0&&oy>0){moved=true;const move=(node,s)=>{if(!node.depth)return;if(ox<oy)node.x+=s*(ox/2+1);else node.y+=s*(oy/2+1);};const sign=ox<oy?(dx>=0?1:-1):(dy>=0?1:-1);move(p,-sign);move(q,sign);}
      }
      if(!moved)break;
    }
    return {nodes,edges};
  }
  const api={terminal,done,status,graph,cpm,ownerStyle,hierarchyLayout,radialLayout};
  if(typeof module==='object'&&module.exports)module.exports=api;else root.WbsCore=api;
})(typeof globalThis==='object'?globalThis:this);
