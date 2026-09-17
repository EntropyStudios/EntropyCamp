(function initializeWorkHistoryPage() {
  "use strict";

  const core = window.WorkHistoryCore;
  if (!core) throw new Error("WorkHistoryCore is required");

  const STORAGE_KEY = "lumen-reminder-work-history-v1";
  const CARDS_STORAGE_KEY = "lumen-reminder-cards-v1";
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
  const dayTitleFormatter = new Intl.DateTimeFormat("zh-CN", {
    timeZone: core.DISPLAY_TIME_ZONE,
    month: "long",
    day: "numeric",
  });
  const weekdayFormatter = new Intl.DateTimeFormat("zh-CN", {
    timeZone: core.DISPLAY_TIME_ZONE,
    weekday: "long",
  });
  const monthFormatter = new Intl.DateTimeFormat("zh-CN", {
    timeZone: "UTC",
    year: "numeric",
    month: "long",
  });
  const timeFormatter = new Intl.DateTimeFormat("zh-CN", {
    timeZone: core.DISPLAY_TIME_ZONE,
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });

  const calendarGrid = document.querySelector("#historyCalendarGrid");
  const monthLabel = document.querySelector("#historyMonthLabel");
  const recordCount = document.querySelector("#historyRecordCount");
  const monthDuration = document.querySelector("#monthDuration");
  const monthCompletions = document.querySelector("#monthCompletions");
  const monthShifts = document.querySelector("#monthShifts");
  const monthDays = document.querySelector("#monthDays");
  const selectedDayTitle = document.querySelector("#selectedDayTitle");
  const selectedDayWeekday = document.querySelector("#selectedDayWeekday");
  const selectedDayMood = document.querySelector("#selectedDayMood");
  const daySummary = document.querySelector("#historyDaySummary");
  const shiftList = document.querySelector("#historyShiftList");
  const dayEmpty = document.querySelector("#historyDayEmpty");
  const toast = document.querySelector("#historyToast");
  const conversationDialog = document.querySelector("#historyConversationDialog");
  const conversationForm = document.querySelector("#historyConversationForm");
  const conversationRange = document.querySelector("#historyConversationRange");
  const conversationSearch = document.querySelector("#historyConversationSearch");
  const conversationPicker = document.querySelector("#historyConversationPicker");
  const conversationStatus = document.querySelector("#historyConversationStatus");
  const conversationSelectionToggle = document.querySelector("#toggleHistoryConversationSelection");
  const saveHistoryConversations = document.querySelector("#saveHistoryConversations");

  let store = loadStore();
  let entries = isDemoMode() ? demoEntries() : store.entries;
  let reminderCards = isDemoMode() ? [] : loadReminderCards();
  const requestedDay = new URLSearchParams(window.location.search).get("day") || "";
  const validRequestedDay = /^\d{4}-\d{2}-\d{2}$/.test(requestedDay) ? requestedDay : "";
  let visibleMonth = validRequestedDay ? validRequestedDay.slice(0, 7) : core.monthKey(Date.now());
  let selectedDay = validRequestedDay || latestDayInMonth(visibleMonth) || core.dayKey(Date.now());
  let toastTimer = 0;
  let editingEntryId = "";
  let conversationDialogTrigger = null;
  let selectedConversationIds = new Set();

  function isDemoMode() {
    return new URLSearchParams(window.location.search).get("demo") === "1";
  }

  function loadStore(rawValue) {
    try {
      const raw = rawValue === undefined ? localStorage.getItem(STORAGE_KEY) : rawValue;
      return core.normalizeStore(raw);
    } catch {
      return { version: core.STORE_VERSION, updatedAt: 0, entries: [], unavailable: true };
    }
  }

  function loadReminderCards(rawValue) {
    try {
      const raw = rawValue === undefined ? localStorage.getItem(CARDS_STORAGE_KEY) : rawValue;
      const parsed = JSON.parse(raw || "[]");
      return Array.isArray(parsed)
        ? parsed.filter((card) => card && typeof card.id === "string" && typeof card.codexThreadId === "string" && card.codexThreadId)
        : [];
    } catch {
      return [];
    }
  }

  function showToast(message) {
    window.clearTimeout(toastTimer);
    toast.textContent = message;
    toast.classList.add("is-visible");
    toastTimer = window.setTimeout(() => toast.classList.remove("is-visible"), 2300);
  }

  function saveEntries(nextEntries) {
    if (isDemoMode()) {
      showToast("演示数据不会写入历史");
      return false;
    }
    const payload = {
      version: core.STORE_VERSION,
      updatedAt: Date.now(),
      entries: nextEntries,
    };
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(payload));
      store = core.normalizeStore(payload);
      entries = store.entries;
      return true;
    } catch {
      showToast("保存失败，请检查浏览器本地存储空间");
      return false;
    }
  }

  function timestampForDay(day, hour, minute) {
    return Date.parse(`${day}T${String(hour).padStart(2, "0")}:${String(minute).padStart(2, "0")}:00+08:00`);
  }

  function demoEntries() {
    const month = core.monthKey(Date.now());
    const moods = core.MOODS.map((mood) => mood.id);
    const notes = [
      "把日报读取改成了尾部增量扫描，等待时间明显缩短。",
      "今天的节奏比较稳，明天继续把移动端交互收干净。",
      "钟面细节终于对齐了，留了一些想法准备下次继续。",
      "任务很多，但优先级比较清楚，完成度比预期高。",
    ];
    const records = [];
    [1, 3, 4, 6, 7, 10, 12, 13, 15, 18, 19, 21, 24, 25, 26].forEach((dayNumber, index) => {
      const day = `${month}-${String(dayNumber).padStart(2, "0")}`;
      const startedAt = timestampForDay(day, 8 + (index % 2), 35 + (index % 4) * 5);
      const endedAt = startedAt + (6.4 + (index % 5) * 0.42) * 60 * 60 * 1000;
      records.push(core.createEntry({
        id: `demo-${day}-1`,
        session: { startedAt, countsByCardId: { a: 3 + index % 6, b: index % 3 } },
        endedAt,
        completionCount: 3 + index % 8,
        completions: [
          { cardId: "a", title: "办公工具优化", count: 2 + index % 5 },
          { cardId: "b", title: "钟面细节调整", count: 1 + index % 3 },
        ],
        conversations: [
          { threadId: `demo-office-${index}`, title: "办公工具优化", threadName: "Codex · 办公前端", count: 2 + index % 5 },
          { threadId: `demo-clock-${index}`, title: "钟面细节调整", threadName: "Codex · 世界名钟", count: 1 + index % 3 },
        ],
        mood: moods[index % moods.length],
        note: notes[index % notes.length],
      }));
      if (index === 7 || index === 12) {
        const secondStart = timestampForDay(day, 19, 10);
        records.push(core.createEntry({
          id: `demo-${day}-2`,
          session: { startedAt: secondStart, countsByCardId: { c: 2 } },
          endedAt: secondStart + 78 * 60 * 1000,
          completionCount: 2,
          completions: [{ cardId: "c", title: "晚间收尾", count: 2 }],
          conversations: [{ threadId: `demo-evening-${index}`, title: "晚间收尾", threadName: "Codex · 当日修整", count: 2 }],
          mood: "focused",
          note: "晚间把白天留下的两个小问题收完了。",
        }));
      }
    });
    return records;
  }

  function latestDayInMonth(month) {
    const monthEntries = core.entriesForMonth(entries, month);
    return monthEntries.length ? monthEntries[monthEntries.length - 1].dayKey : "";
  }

  function formatDuration(value, compact = false) {
    const totalMinutes = Math.max(0, Math.round(value / 60000));
    const hours = Math.floor(totalMinutes / 60);
    const minutes = totalMinutes % 60;
    if (compact) return hours ? `${hours}h${minutes ? `${minutes}m` : ""}` : `${minutes}m`;
    if (!hours) return `${minutes}分钟`;
    return minutes ? `${hours}小时 ${minutes}分` : `${hours}小时`;
  }

  function formatCellDuration(value) {
    const totalMinutes = Math.max(0, Math.round(value / 60000));
    const hours = Math.floor(totalMinutes / 60);
    const minutes = totalMinutes % 60;
    return hours ? `${hours}:${String(minutes).padStart(2, "0")}` : `${minutes}m`;
  }

  function monthDate(month) {
    return new Date(Date.UTC(Number(month.slice(0, 4)), Number(month.slice(5, 7)) - 1, 1));
  }

  function dayDate(day) {
    return new Date(`${day}T12:00:00+08:00`);
  }

  function createElement(tag, className, text) {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (text !== undefined) element.textContent = text;
    return element;
  }

  function formatShiftRange(entry) {
    const day = dayTitleFormatter.format(new Date(entry.startedAt));
    const start = timeFormatter.format(new Date(entry.startedAt));
    const endDay = core.dayKey(entry.endedAt) === entry.dayKey
      ? ""
      : `${dayTitleFormatter.format(new Date(entry.endedAt))} `;
    const end = timeFormatter.format(new Date(entry.endedAt));
    return `${day} ${start} — ${endDay}${end}`;
  }

  function conversationRef(conversation) {
    const threadId = conversation?.threadId || "";
    const hostId = conversation?.hostId || "local";
    return hostId !== "local" ? `${hostId}::${threadId}` : threadId;
  }

  function threadOptionsForEntry(entry) {
    return core.groupConversationChoices(reminderCards, entry.countsByCardId, entry.conversations).map((conversation) => ({
      id: conversationRef(conversation),
      threadId: conversation.threadId,
      hostId: conversation.hostId || "local",
      title: conversation.title,
      name: conversation.threadName,
      count: conversation.count,
    }));
  }

  function visibleThreadOptions(entry) {
    const query = conversationSearch.value.trim().toLocaleLowerCase("zh-CN");
    return threadOptionsForEntry(entry).filter((thread) => {
      if (!query) return true;
      return `${thread.title}\n${thread.name}`.toLocaleLowerCase("zh-CN").includes(query);
    });
  }

  function updateConversationPickerStatus(entry, visibleCount) {
    const selectedCount = selectedConversationIds.size;
    const suffix = visibleCount === threadOptionsForEntry(entry).length ? "" : ` · 当前显示 ${visibleCount} 个`;
    if (isDemoMode()) {
      conversationStatus.textContent = `演示模式 · 已选择 ${selectedCount} 个${suffix}，不会写入真实历史`;
    } else {
      conversationStatus.textContent = `已选择 ${selectedCount} 个关联对话${suffix}`;
    }
    saveHistoryConversations.textContent = selectedCount ? `保存 ${selectedCount} 个对话` : "清空已保存对话";
    saveHistoryConversations.disabled = isDemoMode();
  }

  function renderConversationPicker() {
    const entry = entries.find((item) => item.id === editingEntryId);
    if (!entry) return;
    const visible = visibleThreadOptions(entry);
    const fragment = document.createDocumentFragment();
    visible.forEach((thread) => {
      const label = createElement("label", "history-conversation-option");
      const input = document.createElement("input");
      input.type = "checkbox";
      input.value = thread.id;
      input.checked = selectedConversationIds.has(thread.id);
      const marker = createElement("span", "history-conversation-check");
      marker.append(createElement("span"));
      const copy = createElement("span", "history-conversation-option-copy");
      const title = createElement("strong", "", thread.title);
      const detail = createElement("small", "", `${thread.name} · 本班 ${thread.count} 次`);
      copy.append(title, detail);
      if (thread.count > 0) copy.append(createElement("em", "", "本班有完成记录"));
      label.append(input, marker, copy);
      fragment.append(label);
    });
    if (!visible.length) {
      fragment.append(createElement(
        "div",
        "history-conversation-picker-empty",
        conversationSearch.value.trim()
          ? "没有找到匹配的已关联对话"
          : "当前提醒卡片还没有关联 Codex 对话",
      ));
    }
    conversationPicker.replaceChildren(fragment);
    const everyVisibleSelected = visible.length > 0 && visible.every((thread) => selectedConversationIds.has(thread.id));
    conversationSelectionToggle.textContent = everyVisibleSelected ? "取消当前结果" : "全选当前结果";
    conversationSelectionToggle.disabled = !visible.length;
    updateConversationPickerStatus(entry, visible.length);
  }

  function closeConversationDialog() {
    if (conversationDialog.open) conversationDialog.close();
    editingEntryId = "";
    conversationDialogTrigger?.focus();
    conversationDialogTrigger = null;
  }

  function openConversationDialog(entryId, trigger) {
    const entry = entries.find((item) => item.id === entryId);
    if (!entry) return;
    editingEntryId = entry.id;
    conversationDialogTrigger = trigger || null;
    selectedConversationIds = new Set(entry.conversations.map(conversationRef));
    conversationSearch.value = "";
    const rangeStrong = conversationRange.querySelector("strong");
    rangeStrong.textContent = formatShiftRange(entry);
    conversationRange.querySelector("small").textContent = `勾选一个对话后，会读取它在这 ${formatDuration(entry.durationMs)} 班次窗口内的全部消息；正文不会复制到历史数据中。`;
    renderConversationPicker();
    if (typeof conversationDialog.showModal === "function") conversationDialog.showModal();
    else conversationDialog.setAttribute("open", "");
    window.setTimeout(() => conversationSearch.focus(), 0);
  }

  function renderOverview() {
    const monthEntries = core.entriesForMonth(entries, visibleMonth);
    const summary = core.summarize(monthEntries);
    recordCount.textContent = `${entries.length} 次班次`;
    monthDuration.textContent = formatDuration(summary.durationMs);
    monthCompletions.textContent = `${summary.completionCount} 次`;
    monthShifts.textContent = `${summary.shiftCount} 次`;
    monthDays.textContent = `${new Set(monthEntries.map((entry) => entry.dayKey)).size} 天`;
  }

  function buildDayCell(day) {
    const dayEntries = core.entriesForDay(entries, day.dayKey);
    const summary = core.summarize(dayEntries);
    const mood = core.moodById(summary.latestMood);
    const button = createElement("button", "history-day-cell");
    button.type = "button";
    button.dataset.dayKey = day.dayKey;
    button.setAttribute("role", "gridcell");
    button.setAttribute("aria-selected", String(day.dayKey === selectedDay));
    button.setAttribute("aria-label", dayEntries.length
      ? `${day.dayKey}，工作 ${formatDuration(summary.durationMs)}，完成 ${summary.completionCount} 次对话`
      : `${day.dayKey}，没有工作记录`);
    button.classList.toggle("is-outside", !day.inMonth);
    button.classList.toggle("is-today", day.isToday);
    button.classList.toggle("is-selected", day.dayKey === selectedDay);
    if (mood) button.style.setProperty("--day-accent", mood.color);
    button.append(createElement("span", "history-day-number", String(day.day)));
    if (dayEntries.length) {
      const duration = createElement("span", "history-day-duration", formatDuration(summary.durationMs, true));
      duration.dataset.mobileDuration = formatCellDuration(summary.durationMs);
      button.append(
        duration,
        createElement("span", "history-day-count", `${summary.completionCount} 次完成`),
        createElement("span", "history-day-indicator"),
      );
    }
    return button;
  }

  function animateCalendar(direction) {
    if (reduceMotion.matches || typeof calendarGrid.animate !== "function") return;
    calendarGrid.animate(
      [
        { opacity: 0, transform: `translateX(${direction * 16}px)` },
        { opacity: 1, transform: "translateX(0)" },
      ],
      { duration: 330, easing: "cubic-bezier(0.22, 1, 0.36, 1)" },
    );
    [...calendarGrid.children].forEach((cell, index) => {
      cell.animate(
        [{ opacity: 0, transform: "translateY(5px)" }, { opacity: 1, transform: "translateY(0)" }],
        { duration: 230, delay: Math.min(index * 7, 110), easing: "ease-out", fill: "backwards" },
      );
    });
  }

  function renderCalendar({ direction = 0, animate = false } = {}) {
    monthLabel.textContent = monthFormatter.format(monthDate(visibleMonth));
    const fragment = document.createDocumentFragment();
    core.monthGrid(visibleMonth).forEach((day) => fragment.append(buildDayCell(day)));
    calendarGrid.replaceChildren(fragment);
    if (animate) animateCalendar(direction || 1);
  }

  function summaryMetric(label, value) {
    const item = createElement("div");
    item.append(createElement("span", "", label), createElement("strong", "", value));
    return item;
  }

  function buildShift(entry, index) {
    const mood = core.moodById(entry.mood);
    const article = createElement("article", "history-shift");
    if (mood) article.style.setProperty("--shift-accent", mood.color);
    const head = createElement("div", "history-shift-head");
    head.append(
      createElement("strong", "", `${timeFormatter.format(new Date(entry.startedAt))} - ${timeFormatter.format(new Date(entry.endedAt))}`),
      createElement("span", "", mood?.label || `第 ${index + 1} 段`),
    );
    const meta = createElement("div", "history-shift-meta");
    meta.append(
      createElement("span", "", formatDuration(entry.durationMs)),
      createElement("span", "", `${entry.completionCount} 次完成`),
    );
    article.append(head, meta);
    if (entry.note) article.append(createElement("p", "history-shift-note", entry.note));
    if (entry.completions.length) {
      const completions = createElement("div", "history-completions");
      entry.completions.forEach((row) => {
        const line = createElement("div", "history-completion-row");
        line.append(createElement("span", "", row.title), createElement("strong", "", `${row.count} 次`));
        completions.append(line);
      });
      article.append(completions);
    }
    {
      const saved = createElement("div", "history-conversations");
      const savedHead = createElement("div", "history-conversations-head");
      savedHead.append(createElement(
        "span",
        "",
        entry.conversations.length ? `已保存 ${entry.conversations.length} 个对话引用` : "尚未补选这个班次的对话",
      ));
      const savedActions = createElement("div", "history-conversations-actions");
      const edit = createElement(
        "button",
        "history-edit-conversations",
        entry.conversations.length ? "修改对话" : "补选对话",
      );
      edit.type = "button";
      edit.dataset.editConversations = entry.id;
      savedActions.append(edit);
      if (entry.conversations.length) {
      const open = createElement("a", "history-open-conversations", "查看对话记录");
      open.href = `work-log.html?history=${encodeURIComponent(entry.id)}`;
      open.setAttribute("aria-label", `查看 ${timeFormatter.format(new Date(entry.startedAt))} 班次的对话记录`);
        savedActions.append(open);
      }
      savedHead.append(savedActions);
      saved.append(savedHead);
      entry.conversations.forEach((conversation) => {
        const row = createElement("div", "history-conversation-row");
        const copy = createElement("span");
        copy.append(
          createElement("strong", "", conversation.title),
          createElement("small", "", conversation.threadName),
        );
        row.append(copy, createElement("b", "", conversation.count ? `${conversation.count} 次` : "已补录"));
        saved.append(row);
      });
      article.append(saved);
    }
    return article;
  }

  function renderDayDetail({ animate = true } = {}) {
    const dayEntries = core.entriesForDay(entries, selectedDay);
    const summary = core.summarize(dayEntries);
    const mood = core.moodById(summary.latestMood);
    const selectedDate = dayDate(selectedDay);
    selectedDayTitle.textContent = dayTitleFormatter.format(selectedDate);
    selectedDayWeekday.textContent = weekdayFormatter.format(selectedDate);
    selectedDayMood.hidden = !mood;
    if (mood) {
      selectedDayMood.textContent = mood.label;
      selectedDayMood.style.setProperty("--mood-color", mood.color);
    }
    daySummary.replaceChildren(
      summaryMetric("工作时长", formatDuration(summary.durationMs)),
      summaryMetric("完成对话", `${summary.completionCount} 次`),
      summaryMetric("班次", `${summary.shiftCount} 次`),
    );
    const fragment = document.createDocumentFragment();
    dayEntries.forEach((entry, index) => fragment.append(buildShift(entry, index)));
    shiftList.replaceChildren(fragment);
    shiftList.hidden = !dayEntries.length;
    daySummary.hidden = !dayEntries.length;
    dayEmpty.hidden = Boolean(dayEntries.length);
    if (animate && !reduceMotion.matches && typeof document.querySelector("#historyDayDetail").animate === "function") {
      document.querySelector("#historyDayDetail").animate(
        [{ opacity: 0.45, transform: "translateY(7px)" }, { opacity: 1, transform: "translateY(0)" }],
        { duration: 280, easing: "cubic-bezier(0.22, 1, 0.36, 1)" },
      );
    }
  }

  function renderAll(options = {}) {
    renderOverview();
    renderCalendar(options);
    renderDayDetail({ animate: options.animate !== false });
  }

  function changeMonth(delta) {
    visibleMonth = core.shiftMonth(visibleMonth, delta);
    selectedDay = latestDayInMonth(visibleMonth) || `${visibleMonth}-01`;
    renderAll({ direction: Math.sign(delta), animate: true });
  }

  calendarGrid.addEventListener("click", (event) => {
    const button = event.target.closest("[data-day-key]");
    if (!button) return;
    const nextDay = button.dataset.dayKey;
    const nextMonth = nextDay.slice(0, 7);
    if (nextMonth !== visibleMonth) {
      const direction = nextMonth > visibleMonth ? 1 : -1;
      visibleMonth = nextMonth;
      selectedDay = nextDay;
      renderAll({ direction, animate: true });
      return;
    }
    selectedDay = nextDay;
    renderCalendar();
    renderDayDetail();
  });

  shiftList.addEventListener("click", (event) => {
    const button = event.target.closest("[data-edit-conversations]");
    if (!button) return;
    openConversationDialog(button.dataset.editConversations, button);
  });

  conversationPicker.addEventListener("change", (event) => {
    const input = event.target.closest('input[type="checkbox"]');
    if (!input) return;
    if (input.checked) selectedConversationIds.add(input.value);
    else selectedConversationIds.delete(input.value);
    renderConversationPicker();
  });

  conversationSearch.addEventListener("input", renderConversationPicker);

  conversationSelectionToggle.addEventListener("click", () => {
    const entry = entries.find((item) => item.id === editingEntryId);
    if (!entry) return;
    const visible = visibleThreadOptions(entry);
    const allSelected = visible.length > 0 && visible.every((thread) => selectedConversationIds.has(thread.id));
    visible.forEach((thread) => {
      if (allSelected) selectedConversationIds.delete(thread.id);
      else selectedConversationIds.add(thread.id);
    });
    renderConversationPicker();
  });

  conversationForm.addEventListener("submit", (event) => {
    event.preventDefault();
    const entry = entries.find((item) => item.id === editingEntryId);
    if (!entry || isDemoMode()) return;
    const oldById = new Map(entry.conversations.map((conversation) => [conversation.threadId, conversation]));
    const threadById = new Map(threadOptionsForEntry(entry).map((thread) => [thread.id, thread]));
    const conversations = [...selectedConversationIds].map((threadId) => {
      const old = oldById.get(threadId);
      const thread = threadById.get(threadId);
      return {
        threadId: thread?.threadId || (threadId.includes("::") ? threadId.split("::").slice(1).join("::") : threadId),
        ...(thread?.hostId && thread.hostId !== "local" ? { hostId: thread.hostId } : {}),
        title: thread?.title || old?.title || "Codex 对话",
        threadName: thread?.name || old?.threadName || "Codex 对话",
        count: thread?.count ?? old?.count ?? 0,
      };
    });
    const updatedEntry = core.normalizeEntry({ ...entry, conversations });
    const nextEntries = entries.map((item) => item.id === entry.id ? updatedEntry : item);
    if (!saveEntries(nextEntries)) return;
    closeConversationDialog();
    renderAll({ animate: true });
    showToast(conversations.length ? `已为这个班次保存 ${conversations.length} 个对话` : "已清空这个班次保存的对话");
  });

  document.querySelector("#closeHistoryConversationDialog").addEventListener("click", closeConversationDialog);
  document.querySelector("#cancelHistoryConversationDialog").addEventListener("click", closeConversationDialog);
  conversationDialog.addEventListener("click", (event) => {
    if (event.target === conversationDialog) closeConversationDialog();
  });

  document.querySelector("#previousMonth").addEventListener("click", () => changeMonth(-1));
  document.querySelector("#nextMonth").addEventListener("click", () => changeMonth(1));
  document.querySelector("#historyTodayButton").addEventListener("click", () => {
    const todayMonth = core.monthKey(Date.now());
    const direction = todayMonth >= visibleMonth ? 1 : -1;
    visibleMonth = todayMonth;
    selectedDay = core.dayKey(Date.now());
    renderAll({ direction, animate: true });
  });

  window.addEventListener("storage", (event) => {
    if (isDemoMode()) return;
    if (event.key === CARDS_STORAGE_KEY) {
      reminderCards = loadReminderCards(event.newValue);
      if (conversationDialog.open) renderConversationPicker();
      return;
    }
    if (event.key !== STORAGE_KEY) return;
    store = loadStore(event.newValue);
    if (store.incompatible) {
      showToast("另一页面保存了更新版本的历史数据");
      return;
    }
    entries = store.entries;
    renderAll({ animate: true });
  });

  if (store.invalid) window.setTimeout(() => showToast("历史数据已损坏，已安全忽略"), 0);
  if (store.unavailable) window.setTimeout(() => showToast("浏览器已禁用本地存储"), 0);
  if (store.incompatible) window.setTimeout(() => showToast("历史数据来自更新版本，当前页面无法读取"), 0);
  renderAll({ animate: false });
})();
