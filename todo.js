(async function initializeTodoPage() {
  "use strict";
  await window.EntropyState.ready;
  const businessState = window.EntropyState;
  const core = window.TodoCore;
  if (!core) throw new Error("TodoCore is required");

  const STORAGE_KEY = "lumen-todos-v1";
  const DISPLAY_TIME_ZONE = "Asia/Shanghai";
  const list = document.querySelector("#todoList");
  const empty = document.querySelector("#todoEmpty");
  const emptyTitle = document.querySelector("#todoEmptyTitle");
  const pageCount = document.querySelector("#todoPageCount");
  const dialog = document.querySelector("#todoDialog");
  const form = document.querySelector("#todoForm");
  const dialogTitle = document.querySelector("#todoDialogTitle");
  const idInput = document.querySelector("#todoId");
  const titleInput = document.querySelector("#todoTitle");
  const sectionInput = document.querySelector("#todoSection");
  const priorityInput = document.querySelector("#todoPriority");
  const dueInput = document.querySelector("#todoDueAt");
  const noteInput = document.querySelector("#todoNote");
  const deleteButton = document.querySelector("#deleteTodoButton");
  const toast = document.querySelector("#todoToast");

  let store = loadStore();
  let items = store.items;
  let view = new URLSearchParams(location.search).get("view") || "today";
  if (!["today", "inbox", "later", "completed"].includes(view)) view = "today";
  let editingBase;
  let returnFocus = null;
  let deleteArmed = false;
  let toastTimer = 0;

  const timeFormatter = new Intl.DateTimeFormat("zh-CN", {
    timeZone: DISPLAY_TIME_ZONE,
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });

  function loadStore(rawValue) {
    return core.normalizeStore(rawValue === undefined ? businessState.getItem(STORAGE_KEY) : rawValue);
  }

  async function persist(nextItems, base = businessState.getItem(STORAGE_KEY)) {
    if (store.incompatible) {
      showToast("待办数据来自更新版本，当前页面不会覆盖它");
      return false;
    }
    const payload = { version: core.STORE_VERSION, updatedAt: Date.now(), items: nextItems };
    if (!await businessState.setItem(STORAGE_KEY, JSON.stringify(payload), base)) return false;
    store = loadStore();
    items = store.items;
    return true;
  }

  function showToast(message) {
    clearTimeout(toastTimer);
    toast.textContent = message;
    toast.classList.add("is-visible");
    toastTimer = setTimeout(() => toast.classList.remove("is-visible"), 2200);
  }

  function icon(name) {
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("aria-hidden", "true");
    const use = document.createElementNS("http://www.w3.org/2000/svg", "use");
    use.setAttribute("href", `#icon-${name}`);
    svg.append(use);
    return svg;
  }

  function button(iconName, label, action, item) {
    const element = document.createElement("button");
    element.type = "button";
    element.className = "todo-row-action";
    element.dataset.todoAction = action;
    element.dataset.todoId = item.id;
    element.setAttribute("aria-label", label);
    element.title = label;
    element.append(icon(iconName));
    return element;
  }

  function dueLabel(timestamp) {
    if (!Number.isFinite(timestamp)) return "";
    const prefix = timestamp < Date.now() ? "已逾期 " : "";
    return `${prefix}${timeFormatter.format(new Date(timestamp))}`;
  }

  function renderTabs() {
    const counts = {
      today: core.sortItems(items, "today").length,
      inbox: core.sortItems(items, "inbox").length,
      later: core.sortItems(items, "later").length,
      completed: core.sortItems(items, "completed").length,
    };
    document.querySelectorAll("[data-todo-view]").forEach((tab) => {
      const active = tab.dataset.todoView === view;
      tab.classList.toggle("is-active", active);
      tab.setAttribute("aria-pressed", String(active));
      tab.querySelector("span").textContent = String(counts[tab.dataset.todoView]);
    });
    const total = counts.today + counts.inbox + counts.later;
    pageCount.textContent = `${total} 项未完成`;
  }

  function rowElement(item, visible) {
    const row = document.createElement("article");
    row.className = `todo-row${item.completedAt ? " is-completed" : ""}`;
    row.dataset.todoId = item.id;

    const check = document.createElement("button");
    check.type = "button";
    check.className = "todo-check";
    check.dataset.todoAction = "toggle";
    check.dataset.todoId = item.id;
    check.setAttribute("aria-label", item.completedAt ? `恢复 ${item.title}` : `完成 ${item.title}`);
    check.append(icon("check"));

    const copy = document.createElement("div");
    copy.className = "todo-row-copy";
    const title = document.createElement("strong");
    title.className = "todo-row-title";
    title.textContent = item.title;
    copy.append(title);
    if (item.note) {
      const note = document.createElement("span");
      note.className = "todo-row-note";
      note.textContent = item.note;
      copy.append(note);
    }

    const meta = document.createElement("div");
    meta.className = "todo-row-meta";
    const priority = document.createElement("i");
    priority.className = `todo-priority is-${item.priority}`;
    priority.title = item.priority === "high" ? "高优先级" : item.priority === "low" ? "低优先级" : "普通优先级";
    meta.append(priority);
    const due = dueLabel(item.dueAt);
    if (due) {
      const time = document.createElement("time");
      time.dateTime = new Date(item.dueAt).toISOString();
      time.textContent = due;
      meta.append(time);
    }
    if (item.completedAt) {
      const completed = document.createElement("span");
      completed.textContent = `完成于 ${timeFormatter.format(new Date(item.completedAt))}`;
      meta.append(completed);
    }

    const actions = document.createElement("div");
    actions.className = "todo-row-actions";
    if (!item.completedAt) {
      const peers = visible.filter((candidate) => candidate.priority === item.priority);
      const peerIndex = peers.findIndex((candidate) => candidate.id === item.id);
      const up = button("up", "上移", "up", item);
      const down = button("down", "下移", "down", item);
      up.disabled = peerIndex === 0;
      down.disabled = peerIndex === peers.length - 1;
      actions.append(up, down);
    }
    actions.append(button("pencil", "编辑", "edit", item));
    row.append(check, copy, meta, actions);
    return row;
  }

  function render({ animate = true } = {}) {
    const before = new Map(
      [...list.querySelectorAll("[data-todo-id]")].map((row) => [row.dataset.todoId, row.getBoundingClientRect()]),
    );
    const visible = core.sortItems(items, view);
    list.replaceChildren(...visible.map((item) => rowElement(item, visible)));
    list.hidden = !visible.length;
    empty.hidden = Boolean(visible.length);
    emptyTitle.textContent = view === "completed" ? "还没有已完成的待办" : view === "today" ? "今天没有待办" : view === "inbox" ? "收集箱是空的" : "稍后没有待办";
    renderTabs();
    if (!animate || matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    requestAnimationFrame(() => {
      list.querySelectorAll("[data-todo-id]").forEach((row) => {
        const previous = before.get(row.dataset.todoId);
        if (!previous) return;
        const current = row.getBoundingClientRect();
        const y = previous.top - current.top;
        if (Math.abs(y) < 1) return;
        row.animate([{ transform: `translateY(${y}px)` }, { transform: "translateY(0)" }], {
          duration: 340,
          easing: "cubic-bezier(0.22, 1, 0.36, 1)",
        });
      });
    });
  }

  function localInputValue(timestamp) {
    if (!Number.isFinite(timestamp)) return "";
    const date = new Date(timestamp - new Date(timestamp).getTimezoneOffset() * 60_000);
    return date.toISOString().slice(0, 16);
  }

  function resetDeleteArm() {
    deleteArmed = false;
    deleteButton.textContent = "删除";
    deleteButton.classList.remove("is-armed");
  }

  function openDialog(item = null, trigger = null) {
    editingBase = businessState.getItem(STORAGE_KEY);
    returnFocus = trigger || document.activeElement;
    form.reset();
    resetDeleteArm();
    idInput.value = item?.id || "";
    titleInput.value = item?.title || "";
    sectionInput.value = item?.section || (view === "completed" ? "today" : view);
    priorityInput.value = item?.priority || "normal";
    dueInput.value = localInputValue(item?.dueAt);
    noteInput.value = item?.note || "";
    dialogTitle.textContent = item ? "编辑待办" : "新建待办";
    deleteButton.hidden = !item;
    dialog.showModal();
    setTimeout(() => titleInput.focus(), 20);
  }

  function closeDialog() {
    if (dialog.open) dialog.close();
  }

  async function saveTodo(event) {
    event.preventDefault();
    if (!form.reportValidity()) return;
    const now = Date.now();
    const existing = items.find((item) => item.id === idInput.value);
    const dueAt = dueInput.value ? new Date(dueInput.value).getTime() : null;
    const item = {
      id: existing?.id || crypto.randomUUID?.() || `todo-${now}-${Math.random().toString(16).slice(2)}`,
      title: titleInput.value.trim(),
      note: noteInput.value.trim(),
      section: sectionInput.value,
      priority: priorityInput.value,
      dueAt: Number.isFinite(dueAt) ? dueAt : null,
      completedAt: existing?.completedAt || null,
      order: existing?.section === sectionInput.value ? existing.order : core.nextOrder(items, sectionInput.value),
      createdAt: existing?.createdAt || now,
      updatedAt: now,
    };
    const next = existing ? items.map((candidate) => candidate.id === item.id ? item : candidate) : [...items, item];
    if (!await persist(next, editingBase)) return;
    closeDialog();
    render();
  }

  async function toggleTodo(item) {
    const now = Date.now();
    const next = items.map((candidate) => candidate.id === item.id
      ? { ...candidate, completedAt: candidate.completedAt ? null : now, updatedAt: now }
      : candidate);
    if (await persist(next)) render();
  }

  async function deleteTodo() {
    const item = items.find((candidate) => candidate.id === idInput.value);
    if (!item) return;
    if (!deleteArmed) {
      deleteArmed = true;
      deleteButton.textContent = "再次点击确认";
      deleteButton.classList.add("is-armed");
      return;
    }
    if (!await persist(items.filter((candidate) => candidate.id !== item.id), editingBase)) return;
    closeDialog();
    render();
    showToast("待办已删除");
  }

  async function moveTodo(item, direction) {
    const next = core.moveItem(items, item.id, direction).map((candidate) => candidate.id === item.id
      ? { ...candidate, updatedAt: Date.now() }
      : candidate);
    if (await persist(next)) render();
  }

  document.querySelector("#newTodoButton").addEventListener("click", (event) => openDialog(null, event.currentTarget));
  document.querySelector("#emptyNewTodoButton").addEventListener("click", (event) => openDialog(null, event.currentTarget));
  document.querySelector("#closeTodoDialog").addEventListener("click", closeDialog);
  document.querySelector("#cancelTodoDialog").addEventListener("click", closeDialog);
  deleteButton.addEventListener("click", deleteTodo);
  form.addEventListener("submit", saveTodo);
  dialog.addEventListener("click", (event) => { if (event.target === dialog) closeDialog(); });
  dialog.addEventListener("close", () => { returnFocus?.focus?.(); returnFocus = null; });

  document.querySelector(".todo-tabs").addEventListener("click", (event) => {
    const tab = event.target.closest("[data-todo-view]");
    if (!tab) return;
    view = tab.dataset.todoView;
    history.replaceState(null, "", `?view=${view}`);
    render();
  });

  list.addEventListener("click", async (event) => {
    const action = event.target.closest("[data-todo-action]");
    if (!action) return;
    const item = items.find((candidate) => candidate.id === action.dataset.todoId);
    if (!item) return;
    if (action.dataset.todoAction === "toggle") await toggleTodo(item);
    if (action.dataset.todoAction === "edit") openDialog(item, action);
    if (action.dataset.todoAction === "up") await moveTodo(item, -1);
    if (action.dataset.todoAction === "down") await moveTodo(item, 1);
  });

  businessState.subscribe(({ keys }) => {
    if (!keys.includes(STORAGE_KEY)) return;
    store = loadStore();
    items = store.items;
    render();
  });

  if (store.invalid) setTimeout(() => showToast("待办数据损坏，已安全忽略"), 0);
  if (store.incompatible) setTimeout(() => showToast("待办数据来自更新版本，当前页面为只读"), 0);
  render({ animate: false });
})().catch(window.EntropyState.fail);
