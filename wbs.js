(() => {
  'use strict';
  const $=s=>document.querySelector(s), C=WbsCore, key='entropy-wbs-preferences-v1';
  let data={projects:[],issues:[],modules:[],links:{}}, records=[],performanceError='',candidate=null, previewRevision=null, selectedIssue=null, zoom=1;
  let prefs={project:'',view:'tree',scope:'',owner:'',status:'',search:'',hideDone:true};
  try{prefs={...prefs,...JSON.parse(localStorage.getItem(key)||'{}')};}catch{}
  let expanded=new Set(Array.isArray(prefs.expanded)?prefs.expanded:[]);
  let radialNodes=[],radialEdges=[];
  prefs.nodePositions ||= {};
  zoom=Math.max(.5,Math.min(1.5,Number(prefs.zoom)||.65));
  const esc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const date=x=>x?new Date(x).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai'}):'未同步';
  const field=(r,n)=>r.fields_by_name?.[n];
  const listText=x=>Array.isArray(x)?x.map(v=>v?.name||v?.text||'').join('、'):String(x??'');
  const projectName=id=>data.projects.find(p=>p.id===id)?.name||'未归属项目';
  const api=async(path,body)=>{
    const response=await fetch(path,{method:body?'POST':'GET',headers:{'Content-Type':'application/json','X-Lumen-Request':'1'},body:body?JSON.stringify(body):undefined,cache:'no-store',signal:AbortSignal.timeout(180000)});
    const result=await response.json();if(!response.ok)throw Error(result.error||'请求失败');return result;
  };
  function notice(text){$('#notice').textContent=text;$('#notice').hidden=!text;}
  function save(){prefs.zoom=zoom;prefs.expanded=[...expanded];localStorage.setItem(key,JSON.stringify(prefs));const url=new URL(location.href);url.searchParams.set('project',prefs.project);url.searchParams.set('view',prefs.view);if(selectedIssue)url.searchParams.set('issue',selectedIssue);else url.searchParams.delete('issue');history.replaceState(null,'',url);}
  function current(){return data.issues.filter(i=>i.projectId===prefs.project||(prefs.project==='__none'&&!i.projectId));}
  function visible(i,includeEnded=false){return (includeEnded===true||!prefs.hideDone||!C.terminal(i))&&(!prefs.owner||(prefs.owner==='__none'?!i.assignee:i.assignee===prefs.owner))&&(!prefs.status||C.status(i)===prefs.status)&&(!prefs.search||(i.id+' '+i.title+' '+i.assignee).toLowerCase().includes(prefs.search.toLowerCase()));}
  function roots(){return current().filter(i=>!i.parentId);}
  function shownRoots(){const g=C.graph(data.issues);return roots().filter(i=>visible(i)||g.descendants(i.id).some(visible)&&!!(prefs.search||prefs.owner||prefs.status));}
  function options(){
    const groups=[['进行中的项目',data.projects.filter(p=>!['completed','canceled'].includes(p.state))],['历史项目',data.projects.filter(p=>['completed','canceled'].includes(p.state))]];
    $('#project').innerHTML=groups.map(([label,ps])=>`<optgroup label="${esc(label)}">${ps.map(p=>`<option value="${esc(p.id)}">${esc(p.name)}</option>`).join('')}</optgroup>`).join('')+'<option value="__none">未归属项目</option>';
    if(!data.projects.some(p=>p.id===prefs.project)&&prefs.project!=='__none')prefs.project=data.projects.find(p=>p.name==='V3抓取规划算法开发与验证')?.id||data.projects[0]?.id||'__none';
    $('#project').value=prefs.project;
    $('#owner').innerHTML='<option value="">全部人员</option><option value="__none">未接取</option>'+[...new Set(current().map(i=>i.assignee).filter(Boolean))].sort().map(n=>`<option>${esc(n)}</option>`).join('');
    if(![...$('#owner').options].some(o=>o.value===prefs.owner))prefs.owner='';
    $('#scope').innerHTML='<option value="">父TASK总览</option>'+roots().map(i=>`<option value="${i.id}">${i.id} · ${esc(i.title)}</option>`).join('');
    if(!roots().some(i=>i.id===prefs.scope))prefs.scope='';
    for(const id of ['view','scope','owner','status','search'])$('#'+id).value=prefs[id];
    $('#hideDone').checked=prefs.hideDone;
    const activeFilters=['scope','owner','status','search'].filter(id=>prefs[id]).length;
    $('.filter-disclosure>summary').innerHTML=`筛选任务 ${activeFilters?`<b class="active-filter-count">${activeFilters} 项生效</b>`:''}<span>范围 · 负责人 · 状态 · 搜索${prefs.hideDone?' · 已隐藏结束任务':''}</span>`;
  }
  function ownerBadge(name){const o=C.ownerStyle(name);return `<span class="owner-badge ${o.unassigned?'unassigned':''}" style="--owner:${o.color}"><span class="owner-avatar" aria-hidden="true">${esc(o.initials)}</span>${esc(o.name)}</span>`;}
  function ownerLegend(){const tasks=shownRoots().filter(i=>!prefs.scope||i.id===prefs.scope);return `<div class="owner-legend"><div class="state-overview">${['进行中','待验收','待接取'].map(s=>`<span data-state="${s}"><b>${tasks.filter(i=>C.status(i)===s).length}</b>${s}</span>`).join('')}</div><div class="owner-key">${[...new Set(current().map(i=>i.assignee).filter(Boolean))].sort().map(ownerBadge).join('')}${ownerBadge('')}</div></div>`;}
  function card(i,style='',tree=false){
    const g=C.graph(data.issues),children=g.descendants(i.id),n=children.filter(C.done).length;
    const root=g.rootOf(i.id),linked=data.links[root?.id]?.recordIds||[];
    return `<article class="wbs-card${i.critical?' critical':''}" data-status="${esc(C.status(i))}" ${style}><div class="card-head"><a href="${esc(i.url)}" target="_blank" rel="noopener">${i.id}</a><span class="task-deadline">${i.dueDate?esc(i.dueDate):""}</span></div><div class="task-signals"><span class="task-owner-signal ${i.assignee?"":"is-unassigned"}" style="--task-owner:${C.ownerStyle(i.assignee).color}">${esc(i.assignee||"待接取")}</span><span class="task-state-signal">${C.status(i)==="进行中"?"▶ ":C.status(i)==="待验收"?"◆ ":C.status(i)==="已完成"?"✓ ":""}${esc(C.status(i))}</span></div><button class="issue-title" data-open="${i.id}">${esc(i.title)}</button><footer><button ${tree&&children.length?'data-expand':'data-open'}="${i.id}">${tree&&children.length?(expanded.has(i.id)?'收起':'展开')+' · ':''}${children.length?children.length+'个子Issue · '+n+'个完成':'查看要求'}</button><span>${linked.length?'已关联飞书 '+linked.length:'未关联飞书'}</span></footer></article>`;
  }
  function health(){
    const g=C.graph(data.issues),warnings=[];
    for(const i of current()){
      if(i.parentId&&!g.map.has(i.parentId))warnings.push(`${i.id} 父级 ${i.parentId} 不在镜像，保留为待核对，不提升为父TASK`);
      else if(i.parentId&&g.map.get(i.parentId).projectId!==i.projectId)warnings.push(`${i.id} 与父级 ${i.parentId} 跨项目，请核对Linear`);
      if(!g.rootOf(i.id))warnings.push(`${i.id} 存在父子循环`);
      if(i.module==='未分类')warnings.push(`${i.id} 未找到该Project对应的WBS模块标签`);
    }
    $('#health').innerHTML=warnings.length?`<details><summary>归属检查：${warnings.length}项待核对</summary><ul>${warnings.map(w=>`<li>${esc(w)}</li>`).join('')}</ul></details>`:'';
  }
  function renderWbs(){
    let rows=shownRoots();if(prefs.scope)rows=rows.filter(i=>i.id===prefs.scope);
    const groups=new Map();
    const pname=projectName(prefs.project);
    data.modules.filter(m=>m.group==='WBS · '+pname).forEach(m=>groups.set(m.name,[]));
    rows.forEach(i=>{if(!groups.has(i.module))groups.set(i.module,[]);groups.get(i.module).push(i);});
    return [...groups].map(([name,is])=>`<section class="module"><div class="module-heading"><h2>${esc(name)}</h2><span>${is.length}个父TASK</span></div><div class="cards">${is.map(i=>card(i)).join('')||'<p class="summary-block">当前筛选下没有任务</p>'}</div></section>`).join('')||'<div class="empty">没有符合条件的父TASK</div>';
  }
  function renderHierarchy(){
    const g=C.graph(data.issues),rows=shownRoots().filter(i=>!prefs.scope||i.id===prefs.scope),groups=new Map();
    function issueNode(i,seen=new Set()){
      if(seen.has(i.id))return null;
      const next=new Set([...seen,i.id]);
      return {id:i.id,kind:'issue',issue:i,children:expanded.has(i.id)?(g.children.get(i.id)||[]).filter(c=>visible(c,true)).map(c=>issueNode(c,next)).filter(Boolean):[]};
    }
    rows.forEach(i=>{if(!groups.has(i.module))groups.set(i.module,[]);groups.get(i.module).push(issueNode(i));});
    if(!rows.length)return '<div class="empty">没有符合条件的任务</div>';
    const layout=C.radialLayout({id:'project',kind:'project',title:projectName(prefs.project),children:[...groups].map(([name,children])=>({id:'module-'+name,kind:'module',title:name,children}))});
    radialNodes=layout.nodes.map(n=>{const saved=prefs.nodePositions[prefs.project]?.[n.id];return {...n,x:5000+(saved?.x??n.x)-n.width/2,y:5000+(saved?.y??n.y)-n.height/2};});radialEdges=layout.edges;
    return `<div class="graph-tools"><button data-zoom="out">−</button><button data-zoom="in">＋</button><button data-fit>查看全图</button><button data-center>回到中心</button><button data-reset-layout>重新排布</button><button data-collapse>收起子Issue</button><span>${Math.round(zoom*100)}% · 拖动节点调整位置，拖动背景平移；连线表示任务归属</span></div><div class="scroll tree-scroll radial-scroll" tabindex="0" aria-label="WBS网状图"><div style="width:${10000*zoom}px;height:${10000*zoom}px"><div class="hierarchy" style="width:10000px;height:10000px;transform:scale(${zoom});transform-origin:top left"><svg width="10000" height="10000"></svg>${radialNodes.map(n=>`<div class="radial-node" data-node-id="${esc(n.id)}" style="left:${n.x}px;top:${n.y}px;width:${n.width}px;height:${n.height}px">`+(n.kind==='issue'?card(n.issue,`style="width:${n.width}px;height:${n.height}px"`,true):`<div class="hierarchy-group ${n.kind}" style="width:${n.width}px;height:${n.height}px"><small>${n.kind==='project'?'PROJECT / 项目':'MODULE / 模块'}</small><strong>${esc(n.title)}</strong></div>`)+`</div>`).join('')}</div></div></div>`;
  }
  function drawRadialEdges(){const svg=$('.radial-scroll svg');if(!svg)return;const byId=new Map(radialNodes.map(n=>[n.id,n]));svg.innerHTML=radialEdges.map(e=>{const a=byId.get(e.from),b=byId.get(e.to);return `<line x1="${a.x+a.width/2}" y1="${a.y+a.height/2}" x2="${b.x+b.width/2}" y2="${b.y+b.height/2}" stroke="#718295" stroke-width="2"/>`;}).join('');}
  function centerRadial(){const area=$('.radial-scroll');if(!area)return;area.scrollLeft=5000*zoom-area.clientWidth/2;area.scrollTop=5000*zoom-area.clientHeight/2;}
  function plan(){
    const g=C.graph(data.issues);let rows=[];
    if(prefs.scope){rows=g.descendants(prefs.scope).filter(i=>!(g.children.get(i.id)||[]).length);}
    else {
      // Summary view projects actual dependencies onto root TASKs. Never add parent completion as another duration.
      rows=shownRoots().map(i=>{
        const members=[i,...g.descendants(i.id)],deps=new Set();
        members.forEach(m=>(m.blockedBy||[]).forEach(d=>{const r=g.rootOf(d);if(r&&r.id!==i.id)deps.add(r.id);else if(!r)deps.add(d);}));
        const specs=new Set();members.forEach(m=>(m.specDependencies||[]).forEach(d=>{const r=g.rootOf(d);if(r&&r.id!==i.id)specs.add(r.id);else if(!r)specs.add(d);}));
        const leaf=members.filter(m=>m.id!==i.id&&!(g.children.get(m.id)||[]).length);
        const inner=leaf.length?C.cpm(leaf,data.issues):null;
        return {...i,duration:inner?(inner.valid?inner.total:null):i.duration,blockedBy:[...deps],specDependencies:[...specs]};
      });
    }
    // In a scoped plan, filters affect visibility only, not calculation of upstream prerequisites.
    const result=C.cpm(rows,data.issues);
    return result;
  }
  function planWarnings(p){return `<div class="summary-block">${prefs.scope?'只计算该TASK下叶子推进Issue；父TASK不重复计时。':'父TASK总览：工期从内部叶子依赖汇总；展开单个TASK可查看具体推进。'} 只使用Linear真实阻塞关系；不会按机器人动作顺序造依赖。</div>`+(!p.valid?`<div class="warning">排期尚不完整，暂不显示关键路径或预计完工日期。${p.cycle?'<br>依赖存在循环，需核对Linear。':''}${p.missing.length?'<br>缺少明确剩余工期：'+p.missing.join('、'):''}${p.external.length?'<br>未完成或未知的外部前置：'+p.external.map(e=>esc(e.from+' → '+e.to)).join('、'):''}${p.uncertain.length?'<br>描述前置与原生阻塞未对齐：'+p.uncertain.map(e=>esc(e.from+' → '+e.to)).join('、'):''}</div>`:`<div class="summary-block">最长依赖链剩余 ${p.total} 工作日（未计算人员资源冲突及节假日）。</div>`);}
  function renderNetwork(p){
    const connected=new Set(p.edges.flatMap(e=>[e.from,e.to]));
    const visibleNodes=p.nodes.filter(i=>visible(i)&&connected.has(i.id));
    const visibleIds=new Set(visibleNodes.map(i=>i.id));
    const visibleEdges=p.edges.filter(e=>visibleIds.has(e.from)&&visibleIds.has(e.to));
    const hiddenEdges=p.edges.length-visibleEdges.length;
    const independent=p.nodes.filter(i=>!connected.has(i.id)&&visible(i));
    const independentHtml=independent.length?`<section class="module"><div class="module-heading"><h2>独立推进</h2><span>暂无真实前置关系，保持并行</span></div><div class="cards">${independent.map(i=>card(i)).join('')}</div></section>`:'';
    if(!connected.size)return independentHtml||'<div class="empty">当前范围没有推进任务</div>';
    const groups=new Map(),positions=new Map();p.nodes.filter(i=>connected.has(i.id)).forEach(i=>{if(!groups.has(i.level))groups.set(i.level,[]);groups.get(i.level).push(i);});
    const width=Math.max(800,...[...groups.keys()].map(n=>(n+1)*330+30)),height=Math.max(430,...[...groups.values()].map(ns=>ns.length*210+40));
    for(const [level,ns] of groups)ns.forEach((i,n)=>positions.set(i.id,{x:20+level*330,y:20+n*210}));
    const lines=visibleEdges.map(e=>{let a=positions.get(e.from),b=positions.get(e.to);return `<path d="M${a.x+270},${a.y+75} C${a.x+305},${a.y+75} ${b.x-35},${b.y+75} ${b.x},${b.y+75}" fill="none" stroke="#8095aa" stroke-width="2" marker-end="url(#arrow)"/>`;}).join('');
    const filterNote=hiddenEdges?`<div class="summary-block">当前筛选隐藏了 ${hiddenEdges} 条涉及不可见任务的依赖线；排期仍按完整依赖计算，筛选不会解除前置关系。</div>`:'';
    return `${filterNote}<div class="graph-tools"><button data-zoom="out">缩小</button><button data-zoom="in">放大</button><span>${Math.round(zoom*100)}% · 按依赖从左向右；同列任务可并行</span></div><div class="scroll" style="height:min(70vh,800px)"><div style="width:${width*zoom}px;height:${height*zoom}px"><div class="network" style="width:${width}px;height:${height}px;transform:scale(${zoom});transform-origin:top left"><svg width="${width}" height="${height}"><defs><marker id="arrow" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto"><path d="M0,0 L0,6 L7,3 z" fill="#8095aa"/></marker></defs>${lines}</svg>${visibleNodes.map(i=>{let xy=positions.get(i.id);return card(i,`style="left:${xy.x}px;top:${xy.y}px"`);}).join('')}</div></div></div>${independentHtml}`;
  }
  function renderGantt(p){
    if(!p.valid)return '<div class="empty">先在Linear描述中明确“WBS 剩余工期：N 个工作日”，并核对前置，再刷新。</div>';
    const max=Math.max(1,p.total);
    return `<div class="scroll"><table class="gantt"><thead><tr><th>任务 / 负责人</th><th>剩余工期 · 第0～${max}工作日（相对时间）</th><th>截止节点</th></tr></thead><tbody>${p.nodes.filter(visible).map(i=>`<tr><td><button data-open="${i.id}">${i.id} · ${esc(i.title)}</button><br><small>${esc(i.assignee||'待接取')} · ${esc(C.status(i))}</small></td><td><div class="track"><div class="bar ${i.critical?'critical':''}" style="left:${100*i.es/max}%;width:${100*(i.ef-i.es)/max}%" title="${i.es} → ${i.ef} 工作日"></div></div><small>${i.es} → ${i.ef} 工作日${i.critical?' · 关键链':''}</small></td><td>${esc(i.dueDate||'未定')}</td></tr>`).join('')}</tbody></table></div>`;
  }
  function renderLinks(){
    const tasks=shownRoots().filter(i=>!prefs.scope||i.id===prefs.scope),used=new Set(Object.values(data.links).flatMap(v=>v.recordIds));
    return `<div class="summary-block">关联只在本机保存，依据目的、范围和验收人工确认；不自动改Linear/飞书状态。${performanceError?esc(performanceError):'飞书已读取 '+records.length+' 条记录。'}<br>状态不同仅提示复核，“完成等待验证”不等于Linear Done。</div><table class="records-table"><thead><tr><th>父TASK</th><th>对应飞书记录 / 对账</th><th>操作</th></tr></thead><tbody>${tasks.map(i=>{
      const link=data.links[i.id],rs=(link?.recordIds||[]).map(id=>records.find(r=>r.record_id===id)||{record_id:id});
      return `<tr><td><a href="${i.url}" target="_blank" rel="noopener">${i.id}</a> ${esc(i.title)}<p>${esc(C.status(i))} · ${esc(i.assignee||'待接取')}</p></td><td>${rs.length?rs.map(r=>`<a href="performance.html?record=${encodeURIComponent(r.record_id)}">${esc(field(r,'工作内容')||r.record_id)}</a><p>飞书：${esc(field(r,'工作状态')||'本次未读到，待核对')} ｜ Linear：${esc(C.status(i))}<br>截止：${esc(field(r,'截止日期')?date(field(r,'截止日期')):'未定')} / ${esc(i.dueDate||'未定')}</p>`).join(''):'<span class="link-state">尚未确认对应关系</span>'}<p>${esc(link?.note||'')}</p></td><td><button data-open="${i.id}">查看范围 / 关联</button></td></tr>`;
    }).join('')}</tbody></table><details><summary>未关联的飞书记录（${records.filter(r=>!used.has(r.record_id)&&field(r,'工作内容')).length}）</summary>${records.filter(r=>!used.has(r.record_id)&&field(r,'工作内容')).map(r=>`<p><a href="performance.html?record=${encodeURIComponent(r.record_id)}">${esc(field(r,'工作内容'))}</a> · ${esc(field(r,'工作状态'))}</p>`).join('')}</details>`;
  }
  function render(){
    const oldArea=$('.radial-scroll'),position=oldArea?{x:oldArea.scrollLeft/zoom,y:oldArea.scrollTop/zoom,project:oldArea.dataset.project}:null;
    options();health();save();
    $('#syncInfo').textContent=`Linear镜像：${date(data.importedAt)} · v${data.revision} ｜ 飞书${performanceError==='正在读取飞书任务'?'读取中':performanceError?'读取待核对':'只读'}（两个系统独立刷新）`;
    $('#counts').textContent=`${current().length}个Issue · ${roots().length}个父TASK · ${roots().filter(i=>!i.assignee&&!C.terminal(i)).length}个未接取`;
    if(prefs.view==='wbs')$('#content').innerHTML=ownerLegend()+renderWbs();
    else if(prefs.view==='tree')$('#content').innerHTML=ownerLegend()+renderHierarchy();
    else if(prefs.view==='links')$('#content').innerHTML=renderLinks();
    else {const p=plan();$('#content').innerHTML=ownerLegend()+planWarnings(p)+(prefs.view==='gantt'?renderGantt(p):renderNetwork(p));}
    if(prefs.view==='tree'){const area=$('.radial-scroll');if(area){area.dataset.project=prefs.project;drawRadialEdges();if(position?.project===prefs.project){area.scrollLeft=position.x*zoom;area.scrollTop=position.y*zoom;}else centerRadial();}}
  }
  async function loadPerformance(){
    const found=new Map();try{
      let stale=false;
      for(const department of ['运控','力控']){
        let complete=false;
        for(let page=1;page<=1000;page++){
          const response=await api('/api/performance/records?department='+encodeURIComponent(department)+'&archived=exclude&page_size=100&page='+page);
          const d=response.data;for(const row of d.items||[])found.set(row.record_id,row);
          stale ||= Boolean(d.stale);
          if(!d.has_more){complete=true;break;}
        }
        if(!complete)throw Error(department+'分页超出限制');
      }
      records=[...found.values()];performanceError=stale?'飞书接口返回缓存，需核对同步时间':'';
    }catch(e){performanceError='飞书读取未完整成功：'+e.message;}
  }
  function openIssue(id){
    const i=data.issues.find(x=>x.id===id);if(!i)return;selectedIssue=id;save();
    const g=C.graph(data.issues),root=g.rootOf(id),children=g.descendants(id),link=data.links[root?.id],linked=link?.recordIds||[];
    $('#detailTitle').textContent=id+' · '+i.title;$('#detail').hidden=false;
    $('#detailBody').innerHTML=`<p><span class="pill">${esc(C.status(i))}</span>　${esc(i.assignee||'待接取')}　<a href="${i.url}" target="_blank" rel="noopener">打开Linear</a></p><p class="summary-block">${esc(projectName(i.projectId))} / ${esc(i.module)}${i.parentId?'<br>实际父级：<button data-open="'+i.parentId+'">'+i.parentId+'</button>':''}<br>里程碑：${esc(i.milestone?.name||'未设置')} · 截止：${esc(i.dueDate||'未定')}</p><h3>真实前置依赖</h3><p>${(i.blockedBy||[]).map(d=>`<a href="https://linear.app/sevenova/issue/${d}" target="_blank" rel="noopener">${d}</a>`).join('、')||'无'}${(i.specDependencies||[]).filter(d=>!i.blockedBy.includes(d)).length?'<br>描述中另有未对齐前置，请核对':''}</p><h3>任务要求与验收（Linear原文）</h3><pre>${esc(i.description||'未填写')}</pre><h3>${children.length}个推进子Issue · ${children.filter(C.done).length}个完成</h3><div class="children">${(g.children.get(id)||[]).map(c=>`<button data-open="${c.id}">${c.id} · ${esc(c.title)}<br><span class="badge">${esc(C.status(c))}</span>　${esc(c.assignee||'未指派')}</button>`).join('')||'<p>尚无子Issue；不能据此自动评价父任务。</p>'}</div>${!i.parentId?`<p><button data-scope="${id}">查看本TASK的内部依赖</button></p>`:''}<h3>对应飞书任务</h3>${linked.map(rid=>{const r=records.find(r=>r.record_id===rid);return `<div class="record"><a href="performance.html?record=${encodeURIComponent(rid)}">${esc(r?field(r,'工作内容'):rid)}</a><p>飞书：${esc(r?field(r,'工作状态'):'本次未读到')} · 负责人：${esc(r?listText(field(r,'姓名 (人员 )')):'待核对')}</p><p>验收：${esc(r?field(r,'验收标准'):'待核对')}</p></div>`;}).join('')}${i.parentId?'<p>公司节点以父TASK关联为准，子Issue不重复建飞书任务。</p>':`<form class="link-form" id="linkForm"><label>选择已有飞书任务（可多选）<select id="recordSelect" multiple size="7">${records.filter(r=>field(r,'工作内容')).map(r=>`<option value="${esc(r.record_id)}" ${linked.includes(r.record_id)?'selected':''}>${esc(field(r,'工作内容'))} · ${esc(field(r,'工作状态'))}</option>`).join('')}</select></label><label>未在列表的记录ID（逗号分隔）<input id="extraRecords" value="${esc(linked.filter(id=>!records.some(r=>r.record_id===id)).join(','))}"></label><label>对应依据 / 已知差异<textarea id="linkNote" placeholder="说明目的、范围和验收如何对应；存在差异请明确标注">${esc(link?.note||'')}</textarea></label><button>确认保存本机关联</button></form>`}`;
    $('#linkForm')?.addEventListener('submit',async e=>{e.preventDefault();const recordIds=[...$('#recordSelect').selectedOptions].map(o=>o.value).concat($('#extraRecords').value.split(/[，,\s]+/).filter(Boolean));try{data=await api('/api/wbs/link',{issueId:id,recordIds,note:$('#linkNote').value,expectedRevision:data.revision});render();openIssue(id);notice('已保存本机关联；没有修改Linear或飞书。');}catch(e){notice(e.message);}});
  }
  for(const id of ['project','view','scope','owner','status','search','hideDone'])$('#'+id).addEventListener(id==='search'?'input':'change',()=>{prefs[id]=id==='hideDone'?$('#'+id).checked:$('#'+id).value;if(id==='project'){prefs.scope='';prefs.owner='';selectedIssue=null;$('#detail').hidden=true;}if(id==='status'&&['已完成','已取消'].includes(prefs.status))prefs.hideDone=false;render();});
  document.addEventListener('click',e=>{const open=e.target.closest('[data-open]');if(open)openIssue(open.dataset.open);const scope=e.target.closest('[data-scope]');if(scope){prefs.scope=scope.dataset.scope;prefs.view='cpm';selectedIssue=null;$('#detail').hidden=true;render();}const expand=e.target.closest('[data-expand]');if(expand){const id=expand.dataset.expand;expanded.has(id)?expanded.delete(id):expanded.add(id);render();}if(e.target.closest('[data-collapse]')){expanded.clear();render();}const z=e.target.closest('[data-zoom]');if(z){zoom=Math.max(.15,Math.min(1.5,zoom+(z.dataset.zoom==='in'?.1:-.1)));render();}});
  let drag=null;
  document.addEventListener('click',e=>{if(e.target.closest('[data-reset-layout]')){delete prefs.nodePositions[prefs.project];render();centerRadial();}if(e.target.closest('[data-center]'))centerRadial();if(e.target.closest('[data-fit]')){const area=$('.radial-scroll');if(!area||!radialNodes.length)return;const minX=Math.min(...radialNodes.map(n=>n.x)),minY=Math.min(...radialNodes.map(n=>n.y)),maxX=Math.max(...radialNodes.map(n=>n.x+n.width)),maxY=Math.max(...radialNodes.map(n=>n.y+n.height));zoom=Math.max(.15,Math.min(1,(area.clientWidth-60)/(maxX-minX),(area.clientHeight-60)/(maxY-minY)));render();const next=$('.radial-scroll');next.scrollLeft=(minX+maxX)/2*zoom-next.clientWidth/2;next.scrollTop=(minY+maxY)/2*zoom-next.clientHeight/2;}});
  document.addEventListener('pointerdown',e=>{const area=e.target.closest('.tree-scroll');if(!area||e.target.closest('button,a,input,select')||e.button!==0)return;const node=e.target.closest('[data-node-id]'),item=node&&radialNodes.find(n=>n.id===node.dataset.nodeId);drag={area,node,item,x:e.clientX,y:e.clientY,left:area.scrollLeft,top:area.scrollTop,ox:item?.x,oy:item?.y};area.setPointerCapture(e.pointerId);area.classList.add('dragging');});
  document.addEventListener('pointermove',e=>{if(!drag)return;if(drag.item){drag.item.x=Math.max(30,Math.min(9600,drag.ox+(e.clientX-drag.x)/zoom));drag.item.y=Math.max(30,Math.min(9600,drag.oy+(e.clientY-drag.y)/zoom));drag.node.style.left=drag.item.x+'px';drag.node.style.top=drag.item.y+'px';drawRadialEdges();}else{drag.area.scrollLeft=drag.left+drag.x-e.clientX;drag.area.scrollTop=drag.top+drag.y-e.clientY;}});
  function endDrag(){if(drag){if(drag.item){prefs.nodePositions[prefs.project]||={};prefs.nodePositions[prefs.project][drag.item.id]={x:drag.item.x+drag.item.width/2-5000,y:drag.item.y+drag.item.height/2-5000};save();}drag.area.classList.remove('dragging');drag=null;}}
  document.addEventListener('pointerup',endDrag);document.addEventListener('pointercancel',endDrag);
  $('#closeDetail').onclick=()=>{$('#detail').hidden=true;selectedIssue=null;save();};
  async function loadAuth(){try{const s=await api('/api/wbs/oauth/status');$('#authStatus').textContent=s.authenticated?'已登录：'+s.user.name+' · '+s.user.workspace+'（只读，自动续期）':s.registered?'应用已登记，登录后即可读取Linear任务。':'首次使用：先登记OAuth应用，再登录Linear。已有任务快照仍可查看。';$('#authSummary').textContent=s.authenticated?'Linear已连接 · 数据更新':'连接Linear';$('#login').hidden=s.authenticated;$('#logout').hidden=!s.authenticated;$('#clientId').value=s.clientId||'';return s;}catch(e){notice(e.message);}}
  $('#connection').onclick=async()=>{const s=await loadAuth();if(!s)return;$('#configured').textContent='回调地址必须与Linear应用登记完全一致。';$('#settings').showModal();};
  $('#login').onclick=async()=>{if(location.origin!=='http://127.0.0.1:8765'){location.href='http://127.0.0.1:8765/wbs.html?connect=1';return;}const s=await loadAuth();if(!s?.registered){$('#connection').click();return;}try{const r=await api('/api/wbs/oauth/start',{});location.assign(r.url);}catch(e){notice(e.message);}};
  $('#logout').onclick=async()=>{try{await api('/api/wbs/oauth/logout',{});await loadAuth();notice('已退出本机Linear登录，任务快照保留。');}catch(e){notice(e.message);}};
  $('#cancelSettings').onclick=()=>$('#settings').close();
  $('#reloadLocal').onclick=async()=>{try{data=await api('/api/wbs');render();await loadPerformance();render();notice('本机Linear镜像和飞书查询已重新载入；Linear镜像日期见上方。');}catch(e){notice(e.message);}};
  $('#settingsForm').onsubmit=async e=>{e.preventDefault();try{await api('/api/wbs/oauth/configure',{clientId:$('#clientId').value.trim()});$('#settings').close();await loadAuth();notice('应用已登记，现在可以登录Linear。');}catch(e){notice(e.message);}};
  $('#refresh').onclick=async()=>{
    const btn=$('#refresh');btn.disabled=true;notice('正在读取Linear任务，完成后自动保存…');
    try{
      const r=await api('/api/wbs/refresh',{});
      const latest=await api('/api/wbs/import',{...r.candidate,expectedRevision:r.preview.expectedRevision});
      data=latest;candidate=null;render();
      if(selectedIssue)openIssue(selectedIssue);
      notice(`Linear任务已更新并保存 · ${date(data.importedAt)}；当前项目和飞书关联已保留。`);
    }catch(e){notice('Linear刷新未完成，当前仍显示上次保存的数据：'+e.message);$('#connectionPanel').open=true;}
    finally{btn.disabled=false;}
  };
  $('#cancelImport').onclick=()=>{$('#preview').close();candidate=null;};
  $('#applyImport').onclick=async()=>{if(!candidate)return;try{data=await api('/api/wbs/import',{...candidate,expectedRevision:previewRevision});candidate=null;$('#preview').close();render();notice('本机镜像已更新，Linear和飞书未被修改。');}catch(e){notice(e.message);}};
  $('#copySync').onclick=()=>{const prompt=`请更新EntropyCamp部门WBS的Linear只读镜像。先GET http://127.0.0.1:8765/api/wbs 读取revision和现有数据，再读取本地仓库 /mnt/mydisk/My_project/Entropy/EntropyCamp/docs/WBS_API.md。使用Linear工具完整分页读取MOTION团队项目、模块标签和全部Issue（包括父子关系、完整description、status/statusType、负责人、projectId、milestone、原生blockedBy）。不修改Linear、飞书或WorkGraph，不按标题相似自动关联。POST /api/wbs/preview预览完整快照，再POST /api/wbs/import，complete=true和expectedRevision使用读取的版本；所有POST使用Content-Type: application/json及X-Lumen-Request: 1。保留本地已确认飞书关联。飞书按/api/performance/records完整分页读取，仅报告差异，不自动改状态。更新后在当前对话简要汇报。`;$('#requestText').value=prompt;$('#request').showModal();};
  $('#closeRequest').onclick=()=>$('#request').close();$('#copyRequest').onclick=async()=>{try{await navigator.clipboard.writeText($('#requestText').value);notice('更新请求已复制');}catch{notice('请从文本框手动复制');}};
  document.addEventListener('keydown',e=>{if(e.key==='Escape'){$('#detail').hidden=true;selectedIssue=null;save();}});
  (async()=>{const params=new URLSearchParams(location.search);if(params.has('project'))prefs.project=params.get('project');if(params.has('view'))prefs.view=params.get('view');if(params.has('login')){notice(params.get('login'));const u=new URL(location.href);u.searchParams.delete('login');history.replaceState(null,'',u);}loadAuth();if(params.has('connect'))$('#connectionPanel').open=true;try{data=await api('/api/wbs');performanceError='正在读取飞书任务';render();const id=params.get('issue');if(id)openIssue(id);await loadPerformance();render();if(selectedIssue&&!$('#linkForm')?.contains(document.activeElement))openIssue(selectedIssue);}catch(e){notice(e.message);}})();
})();
