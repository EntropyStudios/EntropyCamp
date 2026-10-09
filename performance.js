(() => {
  "use strict";
  const $ = (selector) => document.querySelector(selector);
  const form = $("#filters"), list = $("#taskList");
  const FILTER_KEY = "entropycamp-performance-filters-v1";
  const ids = {title:"fldH19Afzi",department:"fldRik8iRo",people:"fldzmvfjEO",status:"fldTSdvgfF",due:"fld9RMSxRx"};
  let meta = [], total = 0, requestId = 0, ready = false;
  let applied = null, pollTimer, detailRequestId = 0;
  const esc = (v) => String(v ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  function text(value) {
    if (value === null || value === undefined || value === "") return "—";
    if (Array.isArray(value)) return value.length ? value.map(v => typeof v === "object" ? v.text ?? v.name ?? v.en_name ?? v.record_id ?? v.id ?? "" : v).join(value.every(v => v && typeof v === "object" && "text" in v) ? "" : "、") : "—";
    if (typeof value === "object") return value.text ?? value.name ?? JSON.stringify(value);
    return String(value);
  }
  function date(value, withTime = false) {
    const numeric = Number(value);
    const n = Number.isFinite(numeric) ? numeric : Date.parse(value);
    if (!value || !Number.isFinite(n)) return "未设置";
    return new Intl.DateTimeFormat("zh-CN", {timeZone:"Asia/Shanghai",year:"numeric",month:"2-digit",day:"2-digit", ...(withTime ? {hour:"2-digit",minute:"2-digit",hour12:false} : {})}).format(new Date(n < 1e11 ? n * 1000 : n));
  }
  function field(record, id, name) { return record.fields?.[id] ?? record.fields_by_name?.[name]; }
  function today(offset = 0) { return new Date(Date.now() + 8*3600000 + offset*86400000).toISOString().slice(0,10); }
  async function api(path, body) {
    const response = await fetch(`/api/performance/${path}`, {cache:"no-store",method:body ? "POST" : "GET",headers:{"Content-Type":"application/json","X-Lumen-Request":"1"},...(body ? {body:JSON.stringify(body)} : {}),signal:AbortSignal.timeout(30000)});
    let result;
    try { result = await response.json(); } catch { throw new Error("本机任务接口尚未就绪，请重启 EntropyCamp 服务后重试"); }
    if (!response.ok) { const e = new Error(result.error || "任务请求失败"); e.status = response.status; throw e; }
    return result;
  }
  function notice(message) { $("#errorNotice").hidden = !message; $("#errorNotice").textContent = message || ""; }
  function values() { return Object.fromEntries([...new FormData(form)].filter(([,v]) => v !== "")); }
  function remember() { try { localStorage.setItem(FILTER_KEY, JSON.stringify(applied)); } catch {} }
  function renderRecords(items) {
    const existing = new Map([...list.children].map(node => [node.dataset.record, node]));
    let position = list.firstElementChild;
    items.forEach(record => {
      const status = text(field(record, ids.status, "工作状态"));
      const due = field(record, ids.due, "截止日期");
      const completed = /完成|结束|验收通过/.test(status);
      const overdue = due && Number(due) < new Date(`${today()}T00:00:00+08:00`).getTime() && !completed;
      const content = `<div class="task-card-head"><span class="badge ${completed ? "finished" : overdue ? "overdue" : ""}">${esc(status === "—" ? "未设状态" : status)}</span><span>${esc(text(field(record, ids.department, "部门")))}</span></div><h3>${esc(text(field(record, ids.title, "工作内容")))}</h3><div class="task-card-foot"><span>${esc(text(field(record, ids.people, "姓名 (人员 )")))}</span><time>${overdue ? "已逾期 · " : "截止 "}${esc(date(due))}</time></div>`;
      let node = existing.get(record.record_id);
      if (!node) {
        node = document.createElement("button");
        node.type = "button";
        node.className = "task-card";
        node.dataset.record = record.record_id;
      }
      // Keep the same card element, focus and hover state across background polls.
      if (node._renderedContent !== content) {
        node.innerHTML = content;
        node._renderedContent = content;
      }
      existing.delete(record.record_id);
      if (node !== position) list.insertBefore(node, position);
      position = node.nextElementSibling;
    });
    existing.forEach(node => node.remove());
    $("#emptyState").hidden = items.length > 0;
  }
  async function load(fresh = false) {
    if (!applied) applied = values();
    const id = ++requestId;
    list.setAttribute("aria-busy", "true");
    $("#syncStatus").textContent = "正在读取任务…";
    $("#refreshButton").disabled = true;
    notice("");
    try {
      const items = new Map();
      let batch = 1, data, stale = false;
      do {
        const query = new URLSearchParams({...applied,page:String(batch),page_size:"200", ...(fresh && batch === 1 ? {fresh:"true"} : {})});
        const result = await api(`records?${query}`);
        if (id !== requestId) return;
        data = result.data;
        stale ||= !!data.stale;
        for (const record of data.items || []) items.set(record.record_id, record);
        $("#syncStatus").textContent = `正在读取任务… ${items.size} / ${data.total}`;
        batch++;
      } while (data.has_more && data.items?.length);
      total = data.total;
      renderRecords([...items.values()]);
      $("#totalCount").textContent = total;
      $("#syncStatus").textContent = `${stale ? "数据暂未更新 · " : "最近同步 "}${date(data.synced_at, true)}`;
      $("#syncStatus").classList.toggle("stale", stale);
      $("#filterSummary").textContent = `${applied.department || "全部部门"} · ${applied.due_from ? applied.due_from + " 起" : "不限起点"} · 全部结果`;
      $("#pageLabel").textContent = `已展示 ${items.size} 条 · 全部结果在此页连续展示`;
    } catch(e) {
      if (id !== requestId) return;
      notice(e.message + (e.status === 401 ? "，点击右上角“连接设置”完成配置。" : "；已显示的任务保留，稍后可重试。"));
      $("#syncStatus").textContent = "连接未就绪";
    } finally {
      if (id === requestId) { list.setAttribute("aria-busy","false"); $("#refreshButton").disabled = false; }
      clearTimeout(pollTimer);
      if (ready) pollTimer = setTimeout(() => { if (!document.hidden) load(); }, 30000);
    }
  }
  function option(value,label) { return `<option value="${esc(value)}">${esc(label)}</option>`; }
  async function metadata() {
    const [m,p] = await Promise.all([api("meta"),api("people")]);
    meta = Array.isArray(m.data) ? m.data : m.data.fields || m.data.items || [];
    const status = meta.find(f => (f.field_id || f.id) === ids.status);
    const options = status?.property?.options || status?.options || [];
    const oldStatus = form.elements.status.value || applied?.status || "";
    form.elements.status.innerHTML = option("","全部状态") + options.map(o => option(o.name || o,o.name || o)).join("");
    form.elements.status.value = oldStatus;
    const people = Array.isArray(p.data) ? p.data : p.data.items || p.data.people || [];
    const oldPerson = form.elements.person_id.value || applied?.person_id || "";
    form.elements.person_id.innerHTML = option("","全部人员") + people.map(person => option(person.id || person.open_id,person.name || person.id || person.open_id)).join("");
    form.elements.person_id.value = oldPerson;
    for (const f of meta) {
      const id = f.field_id || f.id, name = f.field_name || f.name;
      if (id && name && ![...form.elements.sort_by.options].some(o => o.value === id)) form.elements.sort_by.add(new Option(name,id));
    }
  }
  async function openDetail(recordId) {
    const detailId = ++detailRequestId;
    const dialog = $("#detailDialog");
    $("#detailContent").textContent = "正在读取最新详情…";
    dialog.showModal();
    try {
      const {data} = await api(`records/${encodeURIComponent(recordId)}`);
      if (!dialog.open || detailId !== detailRequestId) return;
      const fields = meta.length ? meta : Object.keys(data.fields_by_name || {}).map(name => ({field_name:name}));
      const content = fields.map(f => {
        const name = f.field_name || f.name || f.field_id;
        const v = field(data,f.field_id || f.id,name);
        let rendered = esc(text(v));
        if ([5,1001,1002].includes(Number(f.type)) || /日期|创建时间|更改时间/.test(name)) rendered = esc(date(v, /时间/.test(name)));
        if (Number(f.type) === 17 && Array.isArray(v)) rendered = v.map(a => esc(a.name || a.file_token || "附件")).join("<br>");
        return `<div class="detail-field ${/内容|标准|备注|需求/.test(name) ? "wide" : ""}"><dt>${esc(name)}</dt><dd>${rendered}</dd></div>`;
      }).join("");
      $("#detailContent").innerHTML = `<h3 class="detail-title">${esc(text(field(data,ids.title,"工作内容")))}</h3><p class="detail-record">${esc(data.record_id)} · 实时只读详情</p><dl class="detail-grid">${content}</dl>`;
    } catch(e) { if (detailId === detailRequestId) $("#detailContent").textContent = e.message; }
  }
  async function settings() {
    const config = await api("settings");
    $("#baseUrl").value = config.baseUrl;
    $("#apiToken").value = "";
    $("#connectionStatus").textContent = config.configured ? "已保存密钥；留空即可沿用。" : "尚未配置只读密钥。";
    $("#settingsDialog").showModal();
  }
  $("#settingsButton").addEventListener("click", () => settings().catch(e => notice(e.message)));
  $("#settingsForm").addEventListener("submit", async event => {
    event.preventDefault(); $("#saveConnection").disabled = true;
    try {
      await api("settings",{baseUrl:$("#baseUrl").value.trim(),token:$("#apiToken").value.trim()});
      $("#apiToken").value = "";
      await metadata(); ready = true;
      $("#connectionStatus").textContent = "连接成功，已读取真实字段与人员。";
      $("#settingsDialog").close(); await load();
    } catch(e) { $("#connectionStatus").textContent = e.message; }
    finally { $("#saveConnection").disabled = false; }
  });
  document.querySelectorAll("[data-close]").forEach(button => button.addEventListener("click",() => $(`#${button.dataset.close}`).close()));
  form.addEventListener("submit", event => { event.preventDefault(); const next=values(); if (next.due_from && next.due_to && next.due_from > next.due_to) return notice("开始日期不能晚于结束日期"); applied=next; remember(); load(); });
  $("#resetButton").addEventListener("click",() => {form.reset();applied=values();remember();load();});
  $("#refreshButton").addEventListener("click",() => load(true));
  list.addEventListener("click",event => {const b=event.target.closest("[data-record]");if(b)openDetail(b.dataset.record);});
  document.querySelectorAll("[data-days]").forEach(b => b.addEventListener("click",() => {form.elements.due_from.value=today();form.elements.due_to.value=Number(b.dataset.days) ? today(Number(b.dataset.days)) : "";form.requestSubmit();}));
  $("#clearDates").addEventListener("click",() => {form.elements.due_from.value="";form.elements.due_to.value="";form.requestSubmit();});
  document.addEventListener("visibilitychange",() => {clearTimeout(pollTimer);if(!document.hidden && ready)load();});
  async function init() {
    try { applied=JSON.parse(localStorage.getItem(FILTER_KEY) || "null"); } catch {}
    if (applied) delete applied.page_size;
    if (applied?.department === "运控组") applied.department = "运控";
    if (applied) {
      for (const [key,value] of Object.entries(applied)) if(form.elements[key] && !["status","person_id"].includes(key)) form.elements[key].value=value;
    } else applied=values();
    applied ||= values();
    try {const config=await api("settings");if(config.configured){await metadata();ready=true;await load();}else {notice("首次使用请在连接设置中填写只读密钥。");}}
    catch(e){notice(e.message);}
  }
  init();
})();
