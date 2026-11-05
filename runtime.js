"use strict";
(() => {
  const $ = (id) => document.getElementById(id);
  const escape = (value) => String(value ?? "").replace(/[&<>"']/g, (c) => ({"&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#39;"}[c]));
  const bytes = (n) => n >= 1024 ** 3 ? `${(n / 1024 ** 3).toFixed(1)} GB` : `${(n / 1024 ** 2).toFixed(0)} MB`;
  const age = (n) => n >= 86400 ? `${Math.floor(n / 86400)}天 ${Math.floor(n % 86400 / 3600)}时` : n >= 3600 ? `${Math.floor(n / 3600)}时 ${Math.floor(n % 3600 / 60)}分` : `${Math.floor(n / 60)}分`;
  const percent = (n) => n == null ? "采样中" : `${n.toFixed(1)}%`;
  let snapshot = null, tab = "process", automatic = true, loading = false, selectedCommand = "";
  let settings = {};
  try { settings = JSON.parse(localStorage.getItem("entropycamp-runtime-view") || "{}"); } catch { /* Use defaults. */ }
  $("search").value = settings.search || "";
  if ([...$("filter").options].some((o) => o.value === settings.filter)) $("filter").value = settings.filter;
  if ([...$("sort").options].some((o) => o.value === settings.sort)) $("sort").value = settings.sort;
  function remember() {
    try { localStorage.setItem("entropycamp-runtime-view", JSON.stringify({search: $("search").value, filter: $("filter").value, sort: $("sort").value})); } catch { /* Private mode. */ }
  }
  function render() {
    if (!snapshot) return;
    const query = $("search").value.toLowerCase().trim();
    const match = (p) => [p.name, p.command, p.cwd, p.pid, ...p.ports].join(" ").toLowerCase().includes(query);
    const filter = $("filter").value;
    let rows = snapshot.processes.filter((p) => match(p) && (filter === "all" || filter === "development" && p.development || filter === "long" && p.development && p.ageSeconds >= 21600 || filter === "focus" && (p.development || p.ports.length)));
    const key = {cpu:"cpuPercent", memory:"memoryBytes", age:"ageSeconds", pid:"pid"}[$("sort").value];
    rows.sort((a,b) => key === "pid" ? a.pid-b.pid : (b[key] ?? -1)-(a[key] ?? -1) || a.pid-b.pid);
    $("processRows").innerHTML = rows.map((p) => `<tr><td><div class="runtime-name">${escape(p.name)} ${p.hints.includes("运行超过 6 小时") ? '<span class="runtime-badge long">超过 6 小时</span>' : p.development ? '<span class="runtime-badge">开发 / 测试</span>' : ""}</div><div class="runtime-command" title="${escape(p.cwd)}">${escape(p.command)}</div></td><td>${p.pid}</td><td class="${p.cpuPercent > 80 ? "runtime-hot" : ""}">${percent(p.cpuPercent)}</td><td>${bytes(p.memoryBytes)}</td><td>${age(p.ageSeconds)}</td><td>${p.ports.length ? p.ports.join(", ") : "—"}</td><td><button class="runtime-more" data-pid="${p.pid}" aria-label="查看 ${escape(p.name)} ${p.pid} 详情">详情</button></td></tr>`).join("");
    const ports = snapshot.listeners.filter((port) => [port.port, port.address, port.protocol, port.scope, ...port.pids.map((pid) => {
      const process = snapshot.processes.find((p) => p.pid === pid);
      return `${pid} ${process?.name || ""} ${process?.command || ""}`;
    })].join(" ").toLowerCase().includes(query));
    $("portRows").innerHTML = ports.map((p) => `<tr><td><strong>${p.port}</strong></td><td>${escape(p.protocol)}</td><td><code>${escape(p.address)}</code></td><td><span class="runtime-badge${p.scope === "所有网卡" ? " long" : ""}">${escape(p.scope)}</span></td><td>${p.pids.length ? p.pids.map((pid) => {
      const process = snapshot.processes.find((item) => item.pid === pid);
      return process ? `<button class="runtime-port" data-pid="${pid}">${escape(process.name)} · ${pid}</button>` : `<span>PID ${pid}（详情不可见）</span>`;
    }).join(" · ") : '<span class="runtime-command">系统 / 其他用户，归属不可见</span>'}</td></tr>`).join("");
    $("processTable").hidden = tab !== "process";
    $("portTable").hidden = tab !== "port";
    $("filter").hidden = tab !== "process";
    $("sort").hidden = tab !== "process";
    $("processTab").setAttribute("aria-pressed", String(tab === "process"));
    $("portTab").setAttribute("aria-pressed", String(tab === "port"));
    const count = tab === "process" ? rows.length : ports.length;
    $("resultCount").textContent = tab === "process" ? `${count} 个进程 · 当前用户共 ${snapshot.processes.length} 个` : `${count} 个监听端点 · TCP / UDP`;
    $("empty").hidden = count !== 0;
  }
  async function refresh() {
    if (loading) return;
    loading = true;
    $("refresh").disabled = true;
    try {
      const response = await fetch("/api/runtime", {cache:"no-store", signal:AbortSignal.timeout(12000)});
      if (!response.ok) throw new Error(`读取失败（HTTP ${response.status}）`);
      const data = await response.json();
      if (!data.available) throw new Error(data.error || "本机状态暂不可用");
      snapshot = data;
      $("machineName").textContent = data.hostname;
      $("cpu").textContent = percent(data.cpuPercent);
      $("cpuBar").style.width = `${Math.min(100, Math.max(0, data.cpuPercent || 0))}%`;
      $("cpuNote").textContent = `${data.logicalCpus} 个逻辑核心 · 整机使用率`;
      $("memory").textContent = bytes(data.memoryUsed);
      $("memoryBar").style.width = `${data.memoryUsed / data.memoryTotal * 100}%`;
      $("memoryNote").textContent = `共 ${bytes(data.memoryTotal)} · 交换 ${bytes(data.swapUsed)} / ${bytes(data.swapTotal)}`;
      $("devCount").textContent = data.processes.filter((p) => p.development).length;
      $("portCount").textContent = new Set(data.listeners.map((p) => p.port)).size;
      $("uptime").textContent = `电脑已运行 ${age(data.uptimeSeconds)}`;
      $("scope").textContent = data.scope;
      $("updatedAt").textContent = `${new Date(data.sampledAt).toLocaleTimeString("zh-CN", {hour12:false})} 更新 · ${automatic ? "每 5 秒" : "手动刷新"} · 只读`;
      $("notice").hidden = !data.warnings.length;
      $("notice").textContent = data.warnings.join(" ");
      render();
    } catch (error) {
      $("notice").hidden = false;
      $("notice").textContent = `${error.message}。${snapshot ? "当前保留上次采样，请留意更新时间。" : "请确认 EntropyCamp 服务正在运行。"}`;
    } finally {
      loading = false;
      $("refresh").disabled = false;
    }
  }
  function showProcess(pid) {
    const process = snapshot?.processes.find((p) => p.pid === pid);
    if (!process) return;
    selectedCommand = process.command;
    $("detailTitle").textContent = `${process.name} · ${pid}`;
    const stateNames = {R:"运行中", S:"休眠 / 等待事件", D:"等待 I/O", T:"已暂停", Z:"僵尸进程", I:"空闲"};
    const details = [["CPU",percent(process.cpuPercent)],["内存",bytes(process.memoryBytes)],["已运行",age(process.ageSeconds)],["父进程 PID",process.ppid],["进程状态",stateNames[process.state] || process.state],["监听端口",process.ports.join(", ") || "无"]];
    $("detail").innerHTML = `<div class="runtime-detail-grid">${details.map(([k,v]) => `<div><span>${escape(k)}</span><strong>${escape(v)}</strong></div>`).join("")}</div><h3>启动时间</h3><p>${escape(new Date(process.startedAt).toLocaleString("zh-CN",{hour12:false}))}</p><h3>启动命令（常见密钥参数已隐藏）</h3><pre>${escape(process.command)}</pre><h3>工作目录</h3><pre>${escape(process.cwd || "不可读取")}</pre><p>${escape(process.hints.join(" · "))}</p><p>这是最近一次采样，进程可能已经退出。内存为 RSS（含共享页），不能直接相加作为实际总占用。</p>`;
    $("copyStatus").textContent = "";
    $("processDialog").showModal();
  }
  $("processRows").addEventListener("click", (event) => {const button = event.target.closest("[data-pid]"); if (button) showProcess(Number(button.dataset.pid));});
  $("portRows").addEventListener("click", (event) => {const button = event.target.closest("[data-pid]"); if (button) showProcess(Number(button.dataset.pid));});
  $("processTab").onclick = () => {tab="process"; render();};
  $("portTab").onclick = () => {tab="port"; render();};
  for (const id of ["search", "filter", "sort"]) $(id).addEventListener(id === "search" ? "input" : "change", () => {remember(); render();});
  $("refresh").onclick = refresh;
  $("autoRefresh").onclick = () => {automatic = !automatic; $("autoRefresh").textContent = `自动刷新 · ${automatic ? "开" : "关"}`; $("autoRefresh").setAttribute("aria-pressed", String(automatic)); if (automatic) refresh(); else $("updatedAt").textContent = $("updatedAt").textContent.replace("每 5 秒", "手动刷新");};
  $("closeDialog").onclick = $("doneDialog").onclick = () => $("processDialog").close();
  $("processDialog").addEventListener("click", (event) => {if(event.target === $("processDialog")) {const rect=event.target.getBoundingClientRect(); if(event.clientX<rect.left || event.clientX>rect.right || event.clientY<rect.top || event.clientY>rect.bottom) event.target.close();}});
  $("copyCommand").onclick = async () => {try {await navigator.clipboard.writeText(selectedCommand); $("copyStatus").textContent="已复制（敏感参数保持隐藏）";} catch {$("copyStatus").textContent="无法访问剪贴板，请选中命令手动复制。";}};
  document.addEventListener("visibilitychange", () => {if(!document.hidden && automatic) refresh();});
  setInterval(() => {if(automatic && !document.hidden) refresh();}, 5000);
  refresh();
})();
