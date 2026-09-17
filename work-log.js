const STORAGE_KEY = "lumen-reminder-cards-v1";
const WORK_SESSION_KEY = "lumen-reminder-work-session-v1";
const WORK_HISTORY_KEY = "lumen-reminder-work-history-v1";
const historyEntryId = new URLSearchParams(window.location.search).get("history") || "";
const historyCore = window.WorkHistoryCore;

const reportSummary = document.querySelector("#reportSummary");
const sessionMeta = document.querySelector("#sessionMeta");
const threadList = document.querySelector("#threadList");
const reportStatus = document.querySelector("#reportStatus");
const reportPreview = document.querySelector("#reportPreview");
const includeProcessMessages = document.querySelector("#includeProcessMessages");
const generateReportButton = document.querySelector("#generateReportButton");
const toggleSelectionButton = document.querySelector("#toggleSelectionButton");
const copyMarkdownButton = document.querySelector("#copyMarkdownButton");
const downloadMarkdownButton = document.querySelector("#downloadMarkdownButton");
const downloadJsonButton = document.querySelector("#downloadJsonButton");
const reportBackLink = document.querySelector("#reportBackLink");

const historicalContext = loadHistoricalContext();
let cards = historicalContext?.cards || loadCards();
let workSession = historicalContext?.workSession || loadWorkSession();
let currentMarkdown = "";
let currentJson = null;

function updateExportButtons() {
  const hasReport = Boolean(currentMarkdown);
  copyMarkdownButton.disabled = !hasReport;
  downloadMarkdownButton.disabled = !hasReport;
  downloadJsonButton.disabled = !currentJson;
}

function clearGeneratedReport(message = "设置已变更，重新生成后再复制或下载") {
  currentMarkdown = "";
  currentJson = null;
  reportPreview.value = "";
  reportStatus.textContent = message;
  updateExportButtons();
}

function loadCards() {
  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) || "[]");
    return Array.isArray(saved)
      ? saved
          .filter((card) => card && card.codexThreadId)
          .map((card) => ({
            ...card,
            codexHost: typeof card.codexHost === "string" && /^ssh-[A-Za-z0-9][A-Za-z0-9._-]{0,63}$/.test(card.codexHost)
              ? card.codexHost
              : "local",
          }))
      : [];
  } catch {
    return [];
  }
}

function loadWorkSession() {
  try {
    const saved = JSON.parse(localStorage.getItem(WORK_SESSION_KEY) || "{}");
    return saved && typeof saved === "object" ? saved : {};
  } catch {
    return {};
  }
}

function loadHistoricalContext() {
  if (!historyEntryId || !historyCore) return null;
  try {
    const store = historyCore.normalizeStore(localStorage.getItem(WORK_HISTORY_KEY));
    const entry = store.entries.find((candidate) => candidate.id === historyEntryId);
    if (!entry || !entry.conversations.length) return null;
    const countsByCardId = {};
    const cards = entry.conversations.map((conversation, index) => {
      const id = `history-${index}`;
      countsByCardId[id] = conversation.count;
      return {
        id,
        title: conversation.title,
        codexThreadId: conversation.threadId,
        codexHost: conversation.hostId || "local",
        codexThreadName: conversation.threadName,
        createdAt: index,
      };
    });
    return {
      entry,
      cards,
      workSession: {
        active: false,
        startedAt: entry.startedAt,
        endedAt: entry.endedAt,
        countsByCardId,
      },
    };
  } catch {
    return null;
  }
}

function escapeHtml(value = "") {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function formatDateTime(timestamp) {
  if (!Number.isFinite(timestamp)) return "未知时间";
  return new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(new Date(timestamp));
}

function codexThreadRef(cardOrThread) {
  const threadId = cardOrThread?.codexThreadId || cardOrThread?.threadId || cardOrThread?.id || "";
  const hostId = cardOrThread?.codexHost || cardOrThread?.hostId || "local";
  return hostId !== "local" ? `${hostId}::${threadId}` : threadId;
}

function workCountForCard(card) {
  const count = workSession.countsByCardId?.[card.id];
  return Number.isFinite(count) ? count : 0;
}

function totalWorkCount() {
  return cards.reduce((total, card) => total + workCountForCard(card), 0);
}

function selectedCards() {
  const selectedIds = new Set(
    [...document.querySelectorAll("[data-report-card]:checked")].map((input) => input.value)
  );
  return cards.filter((card) => selectedIds.has(card.id));
}

function reportCardInputs() {
  return [...document.querySelectorAll("[data-report-card]")];
}

function syncToggleSelectionLabel() {
  const inputs = reportCardInputs();
  toggleSelectionButton.disabled = inputs.length === 0;
  toggleSelectionButton.textContent = inputs.length && inputs.every((input) => input.checked) ? "清空" : "全选";
}

function exportUntil() {
  if (workSession.active) return null;
  return Number.isFinite(workSession.endedAt) ? workSession.endedAt : null;
}

function renderSummary() {
  const stateText = historicalContext ? "历史班次" : workSession.active ? "上班中" : workSession.startedAt ? "已下班" : "未上班";
  reportSummary.innerHTML = `
    <span>${stateText}</span>
    <strong>${totalWorkCount()}</strong>
    <small>次完成</small>
  `;
  if (!workSession.startedAt) {
    sessionMeta.textContent = "还没有上班记录。先回到提醒页点击上班，再从这里导出。";
    generateReportButton.disabled = true;
    return;
  }
  const until = exportUntil();
  sessionMeta.textContent = until
    ? `${historicalContext ? "历史班次" : "班次"}：${formatDateTime(workSession.startedAt)} - ${formatDateTime(until)}`
    : `班次：${formatDateTime(workSession.startedAt)} - 当前`;
  generateReportButton.disabled = cards.length === 0;
}

function renderThreadList() {
  if (!cards.length) {
    threadList.innerHTML = `<div class="empty-state compact-empty">还没有关联 Codex 对话的卡片</div>`;
    toggleSelectionButton.disabled = true;
    return;
  }

  const cardsWithCount = cards.filter((card) => workCountForCard(card) > 0);
  const defaultSelected = new Set((historicalContext ? cards : cardsWithCount.length ? cardsWithCount : cards).map((card) => card.id));
  cards.sort((a, b) => workCountForCard(b) - workCountForCard(a) || a.createdAt - b.createdAt);
  threadList.innerHTML = cards
    .map((card) => {
      const count = workCountForCard(card);
      const checked = defaultSelected.has(card.id) ? "checked" : "";
      return `
        <label class="thread-option">
          <input data-report-card type="checkbox" value="${escapeHtml(card.id)}" ${checked} />
          <span>
            <strong>${escapeHtml(card.title || card.codexThreadName || "Codex 对话")}</strong>
            <small>${escapeHtml(card.codexThreadName || "Codex 对话")} · 本班 ${count} 次</small>
          </span>
        </label>
      `;
    })
    .join("");
  syncToggleSelectionLabel();
}

function renderPage() {
  renderSummary();
  renderThreadList();
}

function itemLabel(item) {
  if (item.role === "user") return "我";
  if (item.phase === "final_answer") return "Codex 最终回复";
  return "Codex 过程";
}

function buildMarkdown(report, selected) {
  const selectedByThread = new Map(selected.map((card) => [codexThreadRef(card), card]));
  const until = exportUntil();
  const lines = [
    "# 工作日报素材",
    "",
    `班次：${formatDateTime(workSession.startedAt)} - ${until ? formatDateTime(until) : "当前"}`,
    `本班完成：${totalWorkCount()} 次`,
    `导出时间：${formatDateTime(Date.now())}`,
    "",
  ];

  report.threads.forEach((thread) => {
    const card = selectedByThread.get(codexThreadRef(thread));
    lines.push(`## ${card?.title || thread.name || "Codex 对话"}`);
    lines.push("");
    lines.push(`Codex 对话：${card?.codexThreadName || thread.name || "未命名对话"}`);
    lines.push(`本班完成：${card ? workCountForCard(card) : 0} 次`);
    lines.push("");
    if (thread.error) {
      lines.push(`读取失败：${thread.error}`);
      lines.push("");
      return;
    }
    if (!thread.turns?.length) {
      lines.push("这段时间没有读取到新增对话内容。");
      lines.push("");
      return;
    }
    thread.turns.forEach((turn) => {
      const turnTime = turn.completedAt || turn.startedAt;
      lines.push(`### ${formatDateTime(turnTime ? turnTime * 1000 : null)}`);
      lines.push("");
      turn.items.forEach((item) => {
        lines.push(`**${itemLabel(item)}：**`);
        lines.push("");
        lines.push(item.text.trim());
        lines.push("");
      });
    });
  });

  return lines.join("\n").replace(/\n{4,}/g, "\n\n\n").trim() + "\n";
}

async function generateReport() {
  const selected = selectedCards();
  if (!workSession.startedAt) {
    reportStatus.textContent = "还没有上班记录";
    return;
  }
  if (!selected.length) {
    reportStatus.textContent = "先选择至少一个 Codex 对话";
    return;
  }

  generateReportButton.disabled = true;
  currentJson = null;
  currentMarkdown = "";
  reportPreview.value = "";
  updateExportButtons();
  reportStatus.textContent = "正在读取 Codex 对话…";
  const query = new URLSearchParams();
  [...new Set(selected.map(codexThreadRef))].forEach((id) => query.append("id", id));
  query.set("since", String(workSession.startedAt));
  const until = exportUntil();
  if (until) query.set("until", String(until));
  query.set("includeProcess", includeProcessMessages.checked ? "1" : "0");

  try {
    const response = await fetch(`/api/codex/work-log?${query}`, { cache: "no-store" });
    const report = await response.json();
    if (!response.ok || !report.available) throw new Error(report.error || "读取失败");
    currentJson = {
      exportedAt: Date.now(),
      workSession,
      selectedCards: selected.map((card) => ({
        id: card.id,
        title: card.title,
        codexThreadId: card.codexThreadId,
        codexThreadName: card.codexThreadName,
        workCount: workCountForCard(card),
      })),
      report,
    };
    currentMarkdown = buildMarkdown(report, selected);
    reportPreview.value = currentMarkdown;
    const turnCount = report.threads.reduce((count, thread) => count + (thread.turns?.length || 0), 0);
    reportStatus.textContent = `已生成：${report.threads.length} 个对话，${turnCount} 个回合`;
    updateExportButtons();
  } catch (error) {
    currentJson = null;
    currentMarkdown = "";
    reportPreview.value = "";
    reportStatus.textContent = error.message || "读取失败";
    updateExportButtons();
  } finally {
    generateReportButton.disabled = !workSession.startedAt || cards.length === 0;
  }
}

async function copyMarkdown() {
  if (!currentMarkdown) await generateReport();
  if (!currentMarkdown) return;
  try {
    await navigator.clipboard.writeText(currentMarkdown);
    reportStatus.textContent = "Markdown 已复制";
  } catch {
    reportPreview.focus();
    reportPreview.select();
    document.execCommand("copy");
    reportStatus.textContent = "Markdown 已选中并尝试复制";
  }
}

function downloadBlob(filename, content, type) {
  const link = document.createElement("a");
  link.href = URL.createObjectURL(new Blob([content], { type }));
  link.download = filename;
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(link.href), 1000);
}

async function downloadMarkdown() {
  if (!currentMarkdown) await generateReport();
  if (!currentMarkdown) return;
  downloadBlob("codex-work-log.md", currentMarkdown, "text/markdown;charset=utf-8");
}

async function downloadJson() {
  if (!currentJson) await generateReport();
  if (!currentJson) return;
  downloadBlob("codex-work-log.json", JSON.stringify(currentJson, null, 2), "application/json;charset=utf-8");
}

function toggleSelection() {
  const inputs = reportCardInputs();
  const shouldSelect = inputs.some((input) => !input.checked);
  inputs.forEach((input) => {
    input.checked = shouldSelect;
  });
  syncToggleSelectionLabel();
  clearGeneratedReport();
}

generateReportButton.addEventListener("click", generateReport);
copyMarkdownButton.addEventListener("click", copyMarkdown);
downloadMarkdownButton.addEventListener("click", downloadMarkdown);
downloadJsonButton.addEventListener("click", downloadJson);
toggleSelectionButton.addEventListener("click", toggleSelection);
includeProcessMessages.addEventListener("change", () => clearGeneratedReport());
threadList.addEventListener("change", (event) => {
  if (!event.target.matches("[data-report-card]")) return;
  syncToggleSelectionLabel();
  clearGeneratedReport();
});

window.addEventListener("storage", (event) => {
  if (historicalContext) return;
  if (event.key !== STORAGE_KEY && event.key !== WORK_SESSION_KEY) return;
  cards = loadCards();
  workSession = loadWorkSession();
  currentMarkdown = "";
  currentJson = null;
  reportPreview.value = "";
  renderPage();
  reportStatus.textContent = "数据已更新，重新生成后再复制或下载";
  updateExportButtons();
});

updateExportButtons();
if (historicalContext) {
  reportBackLink.href = `history.html?day=${encodeURIComponent(historicalContext.entry.dayKey)}`;
  reportBackLink.textContent = "返回历史";
}
renderPage();
if (workSession.startedAt && (historicalContext || cards.some((card) => workCountForCard(card) > 0))) {
  generateReport();
}
