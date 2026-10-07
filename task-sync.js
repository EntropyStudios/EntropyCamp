(function initializeTaskSync() {
  "use strict";

  const managerThreadName = document.querySelector("#managerThreadName");
  const windowStartInput = document.querySelector("#windowStartInput");
  const windowDescription = document.querySelector("#windowDescription");
  const analyzeButton = document.querySelector("#analyzeButton");
  const refreshButton = document.querySelector("#refreshButton");
  const runList = document.querySelector("#runList");
  const emptyState = document.querySelector("#emptyState");
  const reviewContent = document.querySelector("#reviewContent");
  const reviewForm = document.querySelector("#reviewForm");
  const runWindow = document.querySelector("#runWindow");
  const runMeta = document.querySelector("#runMeta");
  const runStatus = document.querySelector("#runStatus");
  const runError = document.querySelector("#runError");
  const waitingBox = document.querySelector("#waitingBox");
  const waitingText = document.querySelector("#waitingText");
  const analysisSummary = document.querySelector("#analysisSummary");
  const linearUpdates = document.querySelector("#linearUpdates");
  const newLinearTasks = document.querySelector("#newLinearTasks");
  const feishuTasks = document.querySelector("#feishuTasks");
  const ignoredSection = document.querySelector("#ignoredSection");
  const ignoredItems = document.querySelector("#ignoredItems");
  const submitDecisionButton = document.querySelector("#submitDecisionButton");
  const executionResult = document.querySelector("#executionResult");
  const executionResultText = document.querySelector("#executionResultText");
  const toast = document.querySelector("#toast");
  const sourceSearch = document.querySelector("#sourceSearch");
  const sourceThreadList = document.querySelector("#sourceThreadList");
  const sourceSelectionSummary = document.querySelector("#sourceSelectionSummary");
  const toggleSourcesButton = document.querySelector("#toggleSourcesButton");

  let state = null;
  let managerThreads = [];
  let sourceThreads = [];
  let selectedSourceRefs = new Set();
  let sourcesInitialized = false;
  let activeRunId = "";
  let loading = false;
  let pollTimer = 0;
  let toastTimer = 0;
  let selectionSaveTimer = 0;

  const statusLabels = {
    analyzing: "分析中",
    review: "待审核",
    executing: "执行中",
    completed: "已提交",
    failed: "失败",
  };

  function escapeHtml(value = "") {
    return String(value)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function showToast(message) {
    window.clearTimeout(toastTimer);
    toast.textContent = message;
    toast.classList.add("is-visible");
    toastTimer = window.setTimeout(() => toast.classList.remove("is-visible"), 2600);
  }

  function formatDateTime(timestamp) {
    if (!Number.isFinite(Number(timestamp))) return "未知时间";
    return new Intl.DateTimeFormat("zh-CN", {
      timeZone: "Asia/Shanghai",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    }).format(new Date(Number(timestamp)));
  }

  function toLocalInputValue(timestamp) {
    const date = new Date(Number(timestamp));
    const parts = new Intl.DateTimeFormat("sv-SE", {
      timeZone: "Asia/Shanghai",
      year: "numeric", month: "2-digit", day: "2-digit",
      hour: "2-digit", minute: "2-digit", hour12: false,
    }).formatToParts(date).reduce((result, part) => ({ ...result, [part.type]: part.value }), {});
    return `${parts.year}-${parts.month}-${parts.day}T${parts.hour}:${parts.minute}`;
  }

  function firstWindowStart() {
    const now = new Date();
    return new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  }

  async function request(path, body) {
    const response = await fetch(path, {
      method: body ? "POST" : "GET",
      cache: "no-store",
      headers: { "Content-Type": "application/json", "X-Lumen-Request": "1" },
      ...(body ? { body: JSON.stringify(body) } : {}),
    });
    const result = await response.json();
    if (!response.ok || result.available === false) throw new Error(result.error || "请求失败");
    return result;
  }

  function managerThread() {
    return managerThreads.find((thread) => thread.id === state?.managerThreadId)
      || managerThreads[0]
      || null;
  }

  function sourceRef(thread) {
    return thread.hostId && thread.hostId !== "local" ? `${thread.hostId}::${thread.id}` : thread.id;
  }

  function renderManagerThread() {
    const manager = managerThread();
    managerThreadName.textContent = manager
      ? manager.name || manager.preview || "未命名对话"
      : "没有找到本机 Codex 对话";
  }

  function visibleSourceThreads() {
    const query = sourceSearch.value.trim().toLocaleLowerCase();
    if (!query) return sourceThreads;
    return sourceThreads.filter((thread) => `${thread.name || ""} ${thread.preview || ""} ${thread.sourceLabel || ""}`.toLocaleLowerCase().includes(query));
  }

  function renderSourceThreads() {
    const visible = visibleSourceThreads();
    sourceThreadList.innerHTML = visible.length ? visible.map((thread) => {
      const ref = sourceRef(thread);
      return `
        <label class="source-thread-option ${selectedSourceRefs.has(ref) ? "is-selected" : ""}">
          <input type="checkbox" value="${escapeHtml(ref)}" ${selectedSourceRefs.has(ref) ? "checked" : ""} />
          <span>
            <strong>${escapeHtml(thread.name || thread.preview || "未命名对话")}</strong>
            <small>${escapeHtml(thread.sourceLabel || "本机")} · ${escapeHtml(thread.cwd || "未标注目录")}</small>
          </span>
        </label>`;
    }).join("") : `<div class="source-empty">没有匹配的对话</div>`;
    sourceSelectionSummary.textContent = `已勾选 ${selectedSourceRefs.size} / ${sourceThreads.length} 个对话`;
    toggleSourcesButton.textContent = visible.length && visible.every((thread) => selectedSourceRefs.has(sourceRef(thread))) ? "清空当前" : "全选当前";
  }

  function renderWindow() {
    const start = state?.lastTriggeredAt || firstWindowStart();
    if (!windowStartInput.matches(":focus")) windowStartInput.value = toLocalInputValue(start);
    windowDescription.textContent = state?.lastTriggeredAt
      ? `默认从上次点击 ${formatDateTime(state.lastTriggeredAt)} 开始。`
      : "首次默认从今天 00:00 开始，可临时修改。";
  }

  function currentRun() {
    return (state?.runs || []).find((run) => run.id === activeRunId) || null;
  }

  function renderRuns() {
    const runs = state?.runs || [];
    if (!runs.length) {
      runList.innerHTML = `<div class="empty-state"><span>暂无同步记录</span></div>`;
      return;
    }
    runList.innerHTML = runs.map((run) => `
      <button class="run-item ${run.id === activeRunId ? "is-active" : ""}" type="button" data-run-id="${escapeHtml(run.id)}" data-status="${escapeHtml(run.status)}">
        <strong>${escapeHtml(statusLabels[run.status] || run.status)}</strong>
        <span>${escapeHtml(formatDateTime(run.windowStart))} - ${escapeHtml(formatDateTime(run.windowEnd))}</span>
        <small>${Number(run.sourceThreadCount || 0)} 个对话 · ${Number(run.sourceTurnCount || 0)} 个回合</small>
      </button>
    `).join("");
  }

  function editableField(label, name, value, wide = false, textarea = false) {
    const control = textarea
      ? `<textarea data-field="${name}" rows="3">${escapeHtml(value || "")}</textarea>`
      : `<input data-field="${name}" value="${escapeHtml(value || "")}" />`;
    return `<label class="${wide ? "wide" : ""}"><span>${label}</span>${control}</label>`;
  }

  function renderRows(target, rows, kind) {
    target.className = "result-list";
    if (!rows.length) {
      target.innerHTML = `<div class="result-item"><span>本次没有建议</span></div>`;
      return;
    }
    target.innerHTML = rows.map((row) => {
      const checked = row.selected !== false ? "checked" : "";
      let fields = "";
      if (kind === "linearUpdates") {
        fields = `
          <div class="field-grid">
            ${editableField("Issue", "issueId", row.issueId)}
            ${editableField("标题", "title", row.title)}
            ${editableField("更新理由", "reason", row.reason, true, true)}
          </div>`;
      } else if (kind === "newLinearTasks") {
        fields = `
          <div class="field-grid">
            ${editableField("标题", "title", row.title, true)}
            ${editableField("父任务", "parentIssueId", row.parentIssueId || "")}
            ${editableField("截止日期", "dueDate", row.dueDate || "")}
            ${editableField("标签（逗号分隔）", "labels", (row.labels || []).join(", "), true)}
            ${editableField("创建理由", "reason", row.reason, true, true)}
            ${editableField("任务描述与验收", "description", row.description, true, true)}
          </div>`;
      } else {
        fields = `
          <div class="field-grid">
            ${editableField("工作内容", "title", row.title, true)}
            ${editableField("工作前期需求", "prerequisite", row.prerequisite || "")}
            ${editableField("汇报方式", "reportType", row.reportType || "")}
            ${editableField("截止日期", "dueDate", row.dueDate || "")}
            ${editableField("工作状态", "status", row.status || "")}
            ${editableField("建议理由", "reason", row.reason, true, true)}
            ${editableField("验收标准", "acceptance", row.acceptance || "", true, true)}
          </div>`;
      }
      return `
        <article class="result-item" data-kind="${kind}" data-item-id="${escapeHtml(row.id)}">
          <div class="result-item-head">
            <input type="checkbox" data-field="selected" ${checked} aria-label="选择此建议" />
            <div class="result-item-body">
              ${fields}
              <div class="source-refs">来源：${escapeHtml((row.sourceThreadIds || []).join("、") || "未标注")}</div>
            </div>
          </div>
        </article>`;
    }).join("");
  }

  function renderAnalysis(run) {
    const analysis = run.analysis || {};
    analysisSummary.value = analysis.summary || "";
    renderRows(linearUpdates, analysis.linearUpdates || [], "linearUpdates");
    renderRows(newLinearTasks, analysis.newLinearTasks || [], "newLinearTasks");
    renderRows(feishuTasks, analysis.feishuTasks || [], "feishuTasks");
    document.querySelector("#linearUpdateCount").textContent = (analysis.linearUpdates || []).length;
    document.querySelector("#newLinearCount").textContent = (analysis.newLinearTasks || []).length;
    document.querySelector("#feishuCount").textContent = (analysis.feishuTasks || []).length;
    const ignored = analysis.ignored || [];
    ignoredSection.hidden = !ignored.length;
    ignoredItems.innerHTML = ignored.map((item) => `
      <div class="ignored-item"><strong>${escapeHtml(item.topic || "未命名")}</strong>：${escapeHtml(item.reason || "")}</div>
    `).join("");
  }

  function renderReview() {
    const run = currentRun();
    emptyState.hidden = Boolean(run);
    reviewContent.hidden = !run;
    if (!run) return;
    runWindow.textContent = `${formatDateTime(run.windowStart)} - ${formatDateTime(run.windowEnd)}`;
    runMeta.textContent = `${run.sourceThreadCount || 0} 个对话，${run.sourceTurnCount || 0} 个回合 · ${run.managerThreadName || "统管对话"}`;
    runStatus.textContent = statusLabels[run.status] || run.status;
    runStatus.dataset.status = run.status || "";
    runError.hidden = !run.error;
    runError.textContent = run.error || "";
    const waiting = run.status === "analyzing" || run.status === "executing";
    waitingBox.hidden = !waiting;
    waitingText.textContent = run.status === "analyzing"
      ? "Codex 正在分析新增对话，完成后这里会自动出现审核项。"
      : "确认结果已发给统管对话，正在等待实际执行结果。";
    reviewForm.hidden = !run.analysis || waiting;
    executionResult.hidden = !run.executionResult;
    executionResultText.textContent = run.executionResult || "";
    if (run.analysis && !waiting) {
      renderAnalysis(run);
      submitDecisionButton.textContent = run.status === "completed" ? "提交修订结果" : "提交确认结果";
    }
  }

  function render() {
    renderManagerThread();
    renderSourceThreads();
    renderWindow();
    renderRuns();
    renderReview();
    const busy = (state?.runs || []).some((run) => ["analyzing", "executing"].includes(run.status));
    analyzeButton.disabled = loading || busy || !managerThread() || selectedSourceRefs.size === 0;
    schedulePoll(busy);
  }

  async function loadState({ quiet = false } = {}) {
    try {
      const result = await request("/api/task-sync");
      state = result.state;
      managerThreads = result.managerThreads || [];
      sourceThreads = (result.sourceThreads || result.managerThreads || []).sort((left, right) =>
        Number(right.updatedAt || 0) - Number(left.updatedAt || 0)
      );
      if (!sourcesInitialized) {
        const available = new Set(sourceThreads.map(sourceRef));
        selectedSourceRefs = Array.isArray(state.selectedSourceRefs)
          ? new Set(state.selectedSourceRefs.filter((ref) => available.has(ref)))
          : new Set(available);
        sourcesInitialized = true;
      }
      if (!activeRunId && state.runs?.length) activeRunId = state.runs[0].id;
      render();
    } catch (error) {
      if (!quiet) showToast(error.message || "读取失败");
    }
  }

  function schedulePoll(enabled) {
    window.clearTimeout(pollTimer);
    if (enabled) pollTimer = window.setTimeout(() => loadState({ quiet: true }), 2500);
  }

  function scheduleSourceSelectionSave() {
    window.clearTimeout(selectionSaveTimer);
    selectionSaveTimer = window.setTimeout(async () => {
      try {
        const result = await request("/api/task-sync/settings", {
          sourceThreadRefs: [...selectedSourceRefs],
        });
        state = result.state;
      } catch (error) {
        showToast(error.message || "对话选择保存失败");
      }
    }, 450);
  }

  async function startAnalysis() {
    const manager = managerThread();
    if (!manager) return showToast("没有找到可用的本机统管对话");
    if (!selectedSourceRefs.size) return showToast("请至少勾选一条需要统计的对话");
    const since = new Date(windowStartInput.value).getTime();
    if (!Number.isFinite(since)) return showToast("请选择有效的同步起点");
    loading = true;
    analyzeButton.disabled = true;
    analyzeButton.classList.add("is-loading");
    analyzeButton.querySelector("span").textContent = "正在启动…";
    try {
      const result = await request("/api/task-sync/analyze", {
        managerThreadId: manager.id,
        sourceThreadRefs: [...selectedSourceRefs],
        since,
      });
      activeRunId = result.run.id;
      showToast("已将增量对话发送给统管对话分析");
      await loadState({ quiet: true });
    } catch (error) {
      showToast(error.message || "分析启动失败");
    } finally {
      loading = false;
      analyzeButton.classList.remove("is-loading");
      analyzeButton.querySelector("span").textContent = "分析新增对话";
      render();
    }
  }

  function serializeRows(target, originalRows, kind) {
    const originalById = new Map(originalRows.map((row) => [row.id, row]));
    return [...target.querySelectorAll("[data-item-id]")].map((element) => {
      const row = { ...(originalById.get(element.dataset.itemId) || {}) };
      element.querySelectorAll("[data-field]").forEach((input) => {
        const field = input.dataset.field;
        row[field] = input.type === "checkbox" ? input.checked : input.value.trim();
      });
      if (kind === "newLinearTasks") {
        row.labels = String(row.labels || "").split(/[，,]/).map((item) => item.trim()).filter(Boolean);
        row.dueDate = row.dueDate || null;
        row.parentIssueId = row.parentIssueId || null;
      }
      if (kind === "feishuTasks") row.dueDate = row.dueDate || null;
      return row;
    });
  }

  function serializeAnalysis(run) {
    const original = run.analysis || {};
    return {
      summary: analysisSummary.value.trim(),
      linearUpdates: serializeRows(linearUpdates, original.linearUpdates || [], "linearUpdates"),
      newLinearTasks: serializeRows(newLinearTasks, original.newLinearTasks || [], "newLinearTasks"),
      feishuTasks: serializeRows(feishuTasks, original.feishuTasks || [], "feishuTasks"),
      ignored: original.ignored || [],
    };
  }

  async function submitDecision(event) {
    event.preventDefault();
    const run = currentRun();
    if (!run) return;
    submitDecisionButton.disabled = true;
    try {
      await request("/api/task-sync/submit", {
        runId: run.id,
        analysis: serializeAnalysis(run),
      });
      showToast("确认结果已发送给统管对话");
      await loadState({ quiet: true });
    } catch (error) {
      showToast(error.message || "提交失败");
    } finally {
      submitDecisionButton.disabled = false;
    }
  }

  runList.addEventListener("click", (event) => {
    const button = event.target.closest("[data-run-id]");
    if (!button) return;
    activeRunId = button.dataset.runId;
    render();
  });
  sourceSearch.addEventListener("input", renderSourceThreads);
  sourceThreadList.addEventListener("change", (event) => {
    if (!event.target.matches('input[type="checkbox"]')) return;
    if (event.target.checked) selectedSourceRefs.add(event.target.value);
    else selectedSourceRefs.delete(event.target.value);
    scheduleSourceSelectionSave();
    render();
  });
  toggleSourcesButton.addEventListener("click", () => {
    const visible = visibleSourceThreads();
    const shouldSelect = visible.some((thread) => !selectedSourceRefs.has(sourceRef(thread)));
    visible.forEach((thread) => {
      const ref = sourceRef(thread);
      if (shouldSelect) selectedSourceRefs.add(ref);
      else selectedSourceRefs.delete(ref);
    });
    scheduleSourceSelectionSave();
    render();
  });
  analyzeButton.addEventListener("click", startAnalysis);
  refreshButton.addEventListener("click", () => loadState());
  reviewForm.addEventListener("submit", submitDecision);
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) loadState({ quiet: true });
  });

  loadState();
})();
