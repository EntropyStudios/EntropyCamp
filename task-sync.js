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
  const parentTaskRequests = document.querySelector("#parentTaskRequests");
  const acceptanceRequests = document.querySelector("#acceptanceRequests");
  const feishuTasks = document.querySelector("#feishuTasks");
  const ignoredSection = document.querySelector("#ignoredSection");
  const ignoredItems = document.querySelector("#ignoredItems");
  const questionsSection = document.querySelector("#questionsSection");
  const questionItems = document.querySelector("#questionItems");
  const submitDecisionButton = document.querySelector("#submitDecisionButton");
  const executionResult = document.querySelector("#executionResult");
  const executionResultText = document.querySelector("#executionResultText");
  const toast = document.querySelector("#toast");
  const sourceSearch = document.querySelector("#sourceSearch");
  const sourceThreadList = document.querySelector("#sourceThreadList");
  const sourceSelectionSummary = document.querySelector("#sourceSelectionSummary");
  const toggleSourcesButton = document.querySelector("#toggleSourcesButton");
  const copyAnalysisRequest = document.querySelector("#copyAnalysisRequest");
  const copyExecutionRequest = document.querySelector("#copyExecutionRequest");
  const requestPanel = document.querySelector("#requestPanel");
  const requestText = document.querySelector("#requestText");

  let state = null;
  let managerThreads = [];
  let sourceThreads = [];
  let selectedSourceRefs = new Set();
  let sourcesInitialized = false;
  let activeRunId = sessionStorage.getItem("task-sync-active-run") || "";
  let loading = false;
  let pollTimer = 0;
  let toastTimer = 0;
  let selectionSaveTimer = 0;
  let draftDirty = false;
  let draftRunId = "";
  let draftRevision = 0;

  const statusLabels = {
    awaiting_analysis: "等待粘贴分析请求",
    awaiting_execution: "等待粘贴执行请求",
    analyzing: "分析中",
    review: "待审核",
    executing: "执行中",
    completed: "已回写结果",
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
      || (state?.managerThreadId ? {id: state.managerThreadId, name: state.managerThreadName} : null)
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

  function parentSummary(row) {
    const identifier = String(row.parentIssueId || "").trim();
    const title = row.parentTitle || "父任务标题待核对";
    const text = identifier ? `${identifier}｜${title}` : "未确认父TASK，不能创建子Issue";
    return `<div class="parent-task-summary"><strong>对应父TASK</strong><span>${escapeHtml(text)}</span></div>`;
  }

  function updateKindField(value) {
    return `<label><span>建议类别</span><select data-field="updateKind">
      <option value="progress" ${!value || value === "progress" ? "selected" : ""}>子Issue过程更新</option>
      <option value="scope_change" ${value === "scope_change" ? "selected" : ""}>合同变更（需单独确认）</option>
      ${value === "acceptance" ? '<option value="acceptance" selected>旧验收建议：请重新分析分类</option>' : ""}
    </select></label>`;
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
            ${editableField("父TASK", "parentIssueId", row.parentIssueId || "")}
            ${editableField("父TASK标题", "parentTitle", row.parentTitle || "")}
            ${updateKindField(row.updateKind)}
            ${editableField("归属依据（父合同覆盖哪项要求）", "scopeEvidence", row.scopeEvidence || "", true, true)}
            ${editableField("更新理由", "reason", row.reason, true, true)}
          </div>`;
      } else if (kind === "newLinearTasks") {
        fields = `
          <div class="field-grid">
            ${editableField("标题", "title", row.title, true)}
            ${editableField("父任务", "parentIssueId", row.parentIssueId || "")}
            ${editableField("父TASK标题", "parentTitle", row.parentTitle || "")}
            ${editableField("Project", "project", row.project || "")}
            ${editableField("Module", "module", row.module || "")}
            ${editableField("任务类型", "taskType", row.taskType || "")}
            ${editableField("对应飞书记录ID（没有则留空）", "feishuRecordId", row.feishuRecordId || "")}
            ${editableField("归属依据（父合同覆盖哪项要求）", "scopeEvidence", row.scopeEvidence || "", true, true)}
            ${editableField("截止日期", "dueDate", row.dueDate || "")}
            ${editableField("标签（逗号分隔）", "labels", (row.labels || []).join(", "), true)}
            ${editableField("创建理由", "reason", row.reason, true, true)}
            ${editableField("子Issue正文（四部分模板）", "description", row.description, true, true)}
          </div>`;
      } else if (kind === "parentTaskRequests") {
        fields = `<div class="field-grid">
          ${editableField("父任务草稿标题", "title", row.title, true)}
          ${editableField("候选Project", "project", row.project || "")}
          ${editableField("候选Module", "module", row.module || "")}
          ${editableField("对应飞书记录ID", "feishuRecordId", row.feishuRecordId || "")}
          ${editableField("为何需要先确认父任务", "reason", row.reason, true, true)}
          ${editableField("要解决的问题及价值", "purpose", row.purpose || "", true, true)}
          ${editableField("希望得到的结果", "expectedResult", row.expectedResult || "", true, true)}
          ${editableField("如何验证", "validation", row.validation || "", true, true)}
          ${editableField("与现有任务的关系", "existingTaskRelation", row.existingTaskRelation || "", true, true)}
          ${editableField("预计投入", "estimatedEffort", row.estimatedEffort || "")}
          ${editableField("所需支持", "supportNeeded", row.supportNeeded || "")}
          ${editableField("是否愿意接取", "willingToTake", row.willingToTake || "")}
          ${editableField("补充说明（兼容历史草稿）", "description", row.description, true, true)}
        </div><button type="button" class="secondary-button" data-copy-parent>复制父任务确认请求</button>`;
      } else if (kind === "acceptanceRequests") {
        fields = `<div class="field-grid">
          ${editableField("父TASK编号", "issueId", row.issueId)}
          ${editableField("父TASK标题", "parentTitle", row.parentTitle || "")}
          ${editableField("父TASK归属编号", "parentIssueId", row.parentIssueId || row.issueId || "")}
          ${editableField("建议标题", "title", row.title)}
          ${editableField("对应推进子Issue（逗号分隔）", "childIssueIds", (row.childIssueIds || []).join(", "), true)}
          ${editableField("整体结果与验收依据", "scopeEvidence", row.scopeEvidence || "", true, true)}
          ${editableField("申请理由、证据及未完成边界", "reason", row.reason, true, true)}
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
            ${kind === "parentTaskRequests" ? "" : `<input type="checkbox" data-field="selected" ${checked} aria-label="选择此建议" />`}
            <div class="result-item-body">
              ${["linearUpdates", "newLinearTasks", "acceptanceRequests"].includes(kind) ? parentSummary(row) : ""}
              ${fields}
              <div class="source-refs">来源：${escapeHtml((row.sourceThreadIds || []).join("、") || "未标注")}</div>
            </div>
          </div>
        </article>`;
    }).join("");
  }

  function renderAnalysis(run) {
    if (draftDirty && draftRunId === run.id) return;
    draftRunId = run.id;
    draftRevision = Number(run.revision || 0);
    const analysis = run.analysis || {};
    analysisSummary.value = analysis.summary || "";
    const questions = analysis.questions || [];
    questionsSection.hidden = !questions.length;
    document.querySelector("#questionCount").textContent = questions.length;
    questionItems.innerHTML = questions.map((q) => `
      <article class="result-item" data-question-id="${escapeHtml(q.id)}">
        <h4>${escapeHtml(q.question)}</h4>
        <p>${escapeHtml(q.context || "")}</p>
        <div class="question-options">${(q.options || []).map((option) => `<button type="button" class="secondary-button" data-answer-option="${escapeHtml(option)}">${escapeHtml(option)}</button>`).join("")}</div>
        <label class="summary-field"><span>你的回答</span><textarea data-question-answer rows="2">${escapeHtml(q.answer || "")}</textarea></label>
        <label><span>处理方式</span><select data-question-status>
          <option value="pending" ${q.status === "pending" ? "selected" : ""}>暂未确认</option>
          <option value="answered" ${q.status === "answered" ? "selected" : ""}>已回答</option>
          <option value="ignored" ${q.status === "ignored" ? "selected" : ""}>忽略此问题</option>
        </select></label>
      </article>`).join("");
    renderRows(linearUpdates, analysis.linearUpdates || [], "linearUpdates");
    renderRows(newLinearTasks, analysis.newLinearTasks || [], "newLinearTasks");
    renderRows(parentTaskRequests, analysis.parentTaskRequests || [], "parentTaskRequests");
    renderRows(acceptanceRequests, analysis.acceptanceRequests || [], "acceptanceRequests");
    document.querySelector("#acceptanceCount").textContent = (analysis.acceptanceRequests || []).length;
    document.querySelector("#parentTaskCount").textContent = (analysis.parentTaskRequests || []).length;
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
    waitingText.textContent = run.progressMessage || (run.status === "analyzing"
      ? "Codex 正在分析新增对话，完成后这里会自动出现审核项。"
      : "请复制请求到统管对话，处理进度和结果会通过接口回写。");
    waitingBox.hidden = !waiting && !["awaiting_analysis", "awaiting_execution"].includes(run.status);
    copyExecutionRequest.hidden = run.status !== "awaiting_execution";
    reviewForm.hidden = !run.analysis || waiting;
    executionResult.hidden = !run.executionResult;
    const operations = run.executionOperations || [];
    const operationLines = operations.map((item) => {
      const status = {success: "成功", failed: "失败", skipped: "跳过", unknown: "状态待核对"}[item.status] || item.status;
      return `[${status}] ${item.itemId} ${item.issueId || ""}\n${item.url || ""}\n${item.message || ""}\n评论ID：${(item.commentIds || []).join("、") || "无"}`;
    });
    executionResultText.textContent = [run.executionResult || "", ...operationLines].filter(Boolean).join("\n\n");
    if (run.analysis && !waiting) {
      renderAnalysis(run);
      submitDecisionButton.querySelector("span").textContent = run.status === "completed" ? "保存修订并复制请求" : "保存确认并复制请求";
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
    schedulePoll((state?.runs || []).some((run) => ["awaiting_analysis", "awaiting_execution", "analyzing", "executing", "failed"].includes(run.status)));
  }

  async function loadState({ quiet = false } = {}) {
    try {
      const result = await request("/api/task-sync?stateOnly=1");
      state = result.state;
      if (!state.runs?.some((run) => run.id === activeRunId)) activeRunId = state.runs?.[0]?.id || "";
      sessionStorage.setItem("task-sync-active-run", activeRunId);
      const editing = reviewForm.contains(document.activeElement);
      if (!editing) render();
    } catch (error) {
      if (!quiet) showToast(error.message || "读取失败");
    }
  }

  async function loadSources() {
    try {
      const result = await request("/api/codex/threads");
      sourceThreads = (result.threads || []).sort((a, b) => Number(b.updatedAt || 0) - Number(a.updatedAt || 0));
      managerThreads = sourceThreads.filter((thread) => thread.hostId === "local");
      if (!sourcesInitialized) {
        selectedSourceRefs = new Set(Array.isArray(state?.selectedSourceRefs) ? state.selectedSourceRefs : sourceThreads.map(sourceRef));
        sourcesInitialized = true;
      }
      render();
    } catch (error) {
      sourceSelectionSummary.textContent = "来源列表加载失败，已保存结果仍可审核；点击刷新重试";
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
    analyzeButton.querySelector("span").textContent = "正在收集…";
    try {
      const result = await request("/api/task-sync/analyze", {
        managerThreadId: manager.id,
        sourceThreadRefs: [...selectedSourceRefs],
        since,
      });
      activeRunId = result.run.id;
      sessionStorage.setItem("task-sync-active-run", activeRunId);
      await loadState({ quiet: true });
      await copyRequest("analysis");
    } catch (error) {
      showToast(error.message || "分析启动失败");
    } finally {
      loading = false;
      analyzeButton.classList.remove("is-loading");
      analyzeButton.querySelector("span").textContent = "生成分析请求";
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
      if (kind === "acceptanceRequests") {
        row.childIssueIds = String(row.childIssueIds || "").split(/[，,、\s]+/).map((item) => item.trim()).filter(Boolean);
      }
      return row;
    });
  }

  function serializeAnalysis(run) {
    const original = run.analysis || {};
    return {
      summary: analysisSummary.value.trim(),
      linearUpdates: serializeRows(linearUpdates, original.linearUpdates || [], "linearUpdates"),
      newLinearTasks: serializeRows(newLinearTasks, original.newLinearTasks || [], "newLinearTasks"),
      parentTaskRequests: serializeRows(parentTaskRequests, original.parentTaskRequests || [], "parentTaskRequests"),
      acceptanceRequests: serializeRows(acceptanceRequests, original.acceptanceRequests || [], "acceptanceRequests"),
      feishuTasks: serializeRows(feishuTasks, original.feishuTasks || [], "feishuTasks"),
      ignored: original.ignored || [],
      questions: (original.questions || []).map((q) => {
        const element = [...questionItems.querySelectorAll("[data-question-id]")].find((item) => item.dataset.questionId === q.id);
        return element ? {...q, answer: element.querySelector("[data-question-answer]").value.trim(), status: element.querySelector("[data-question-status]").value} : q;
      }),
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
        expectedRevision: draftRevision,
      });
      draftDirty = false;
      await loadState({ quiet: true });
      await copyRequest("execution");
    } catch (error) {
      showToast(error.message || "提交失败");
    } finally {
      submitDecisionButton.disabled = false;
    }
  }

  async function copyRequest(phase) {
    const run = currentRun();
    if (!run) return;
    try {
      const result = await request(`/api/task-sync/request?id=${encodeURIComponent(run.id)}&phase=${phase}`);
      requestText.value = result.prompt;
      requestPanel.hidden = false;
      try {
        await navigator.clipboard.writeText(result.prompt);
        showToast("请求已复制，请粘贴到架构师-sevenova对话");
      } catch {
        requestText.focus();
        requestText.select();
        showToast("请求已生成，请手动复制下方文本");
      }
    } catch (error) { showToast(error.message); }
  }

  copyAnalysisRequest.addEventListener("click", () => copyRequest("analysis"));
  copyExecutionRequest.addEventListener("click", () => copyRequest("execution"));

  runList.addEventListener("click", (event) => {
    const button = event.target.closest("[data-run-id]");
    if (!button) return;
    activeRunId = button.dataset.runId;
    sessionStorage.setItem("task-sync-active-run", activeRunId);
    draftDirty = false;
    requestPanel.hidden = true;
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
  refreshButton.addEventListener("click", async () => { await loadState(); loadSources(); });
  reviewForm.addEventListener("submit", submitDecision);
  reviewForm.addEventListener("input", (event) => {
    draftDirty = true;
    if (!["parentIssueId", "parentTitle"].includes(event.target.dataset.field)) return;
    const item = event.target.closest("[data-item-id]");
    const summary = item?.querySelector(".parent-task-summary");
    if (!summary) return;
    const parent = {
      parentIssueId: item.querySelector('[data-field="parentIssueId"]')?.value,
      parentTitle: item.querySelector('[data-field="parentTitle"]')?.value,
    };
    summary.outerHTML = parentSummary(parent);
  });
  reviewForm.addEventListener("change", () => { draftDirty = true; });
  parentTaskRequests.addEventListener("click", async (event) => {
    const button = event.target.closest("[data-copy-parent]");
    if (!button) return;
    const element = button.closest("[data-item-id]");
    const value = (name) => element.querySelector(`[data-field="${name}"]`)?.value.trim() || "";
    const prompt = `请先和我确认父TASK，不创建子Issue、不写入外部系统。
批次：${currentRun()?.id || ""}
建议ID：${element.dataset.itemId}
标题：${value("title")}
候选Project：${value("project")}
候选Module：${value("module")}
飞书记录：${value("feishuRecordId")}
理由：${value("reason")}
待确认内容：
问题及价值：${value("purpose")}
希望结果：${value("expectedResult")}
验证方式：${value("validation")}
与现有任务关系：${value("existingTaskRelation")}
预计投入：${value("estimatedEffort")}
所需支持：${value("supportNeeded")}
是否愿意接取：${value("willingToTake")}
${value("description")}
父任务经我明确确认并发布后，再重新读取父Issue合同，二次分析这个批次的子Issue建议。`;
    requestPanel.hidden = false;
    requestText.value = prompt;
    try {
      await navigator.clipboard.writeText(prompt);
      showToast("已复制，先到统管对话确认父任务");
    } catch {
      showToast("请从请求框手动复制");
    }
  });
  questionItems.addEventListener("input", (event) => {
    if (!event.target.matches("[data-question-answer]")) return;
    event.target.closest("[data-question-id]").querySelector("[data-question-status]").value = event.target.value.trim() ? "answered" : "pending";
  });
  questionItems.addEventListener("click", (event) => {
    const button = event.target.closest("[data-answer-option]");
    if (!button) return;
    const element = button.closest("[data-question-id]");
    element.querySelector("[data-question-answer]").value = button.dataset.answerOption;
    element.querySelector("[data-question-status]").value = "answered";
    draftDirty = true;
  });
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) loadState({ quiet: true });
  });

  loadState().then(loadSources);
})();
