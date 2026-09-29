(function attachTodoCore(root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  if (root) root.TodoCore = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function createTodoCore() {
  "use strict";

  const STORE_VERSION = 1;
  const MAX_ITEMS = 1000;
  const MAX_TITLE_LENGTH = 120;
  const MAX_NOTE_LENGTH = 1600;
  const SECTIONS = Object.freeze(["open", "inbox", "today", "later"]);
  const PRIORITIES = Object.freeze(["high", "normal", "low"]);
  const PRIORITY_RANK = Object.freeze({ high: 0, normal: 1, low: 2 });

  function finiteTimestamp(value, fallback = null) {
    const number = Number(value);
    return Number.isFinite(number) && number > 0 ? number : fallback;
  }

  function normalizeStore(rawValue, now = Date.now()) {
    let source = rawValue;
    if (typeof source === "string") {
      try {
        source = JSON.parse(source);
      } catch {
        return { version: STORE_VERSION, updatedAt: 0, items: [], invalid: true };
      }
    }
    if (Array.isArray(source)) source = { version: 0, items: source };
    if (!source || typeof source !== "object") source = {};
    const sourceVersion = Number.isFinite(Number(source.version)) ? Number(source.version) : 0;
    if (sourceVersion > STORE_VERSION) {
      return { version: sourceVersion, updatedAt: finiteTimestamp(source.updatedAt, 0), items: [], incompatible: true };
    }

    const seen = new Set();
    const items = [];
    for (const [index, raw] of (Array.isArray(source.items) ? source.items : []).entries()) {
      if (items.length >= MAX_ITEMS || !raw || typeof raw !== "object") continue;
      const createdAt = finiteTimestamp(raw.createdAt, finiteTimestamp(raw.updatedAt, now));
      const updatedAt = finiteTimestamp(raw.updatedAt, createdAt);
      let id = typeof raw.id === "string" ? raw.id.trim().slice(0, 120) : "";
      if (!id || seen.has(id)) id = `todo-${createdAt}-${index}`;
      while (seen.has(id)) id += "-copy";
      seen.add(id);
      const title = typeof raw.title === "string" ? raw.title.trim().slice(0, MAX_TITLE_LENGTH) : "";
      if (!title) continue;
      const section = SECTIONS.includes(raw.section) ? raw.section : "open";
      const priority = PRIORITIES.includes(raw.priority) ? raw.priority : "normal";
      const completedAt = finiteTimestamp(raw.completedAt);
      const dueAt = finiteTimestamp(raw.dueAt);
      const order = Number.isFinite(Number(raw.order)) ? Number(raw.order) : index;
      items.push({
        id,
        title,
        note: typeof raw.note === "string" ? raw.note.trim().slice(0, MAX_NOTE_LENGTH) : "",
        section,
        priority,
        dueAt,
        completedAt,
        order,
        createdAt,
        updatedAt,
      });
    }
    return {
      version: STORE_VERSION,
      updatedAt: finiteTimestamp(source.updatedAt, 0),
      items,
      migrated: sourceVersion !== STORE_VERSION,
    };
  }

  function sortItems(items, view = "open") {
    const values = (Array.isArray(items) ? items : []).filter((item) => {
      if (view === "history" || view === "completed") return Boolean(item.completedAt);
      return !item.completedAt;
    });
    return values.slice().sort((left, right) => {
      if (view === "history" || view === "completed") return right.completedAt - left.completedAt || right.updatedAt - left.updatedAt;
      const priority = PRIORITY_RANK[left.priority] - PRIORITY_RANK[right.priority];
      if (priority) return priority;
      if (left.order !== right.order) return left.order - right.order;
      return left.createdAt - right.createdAt;
    });
  }

  function summary(items) {
    const values = Array.isArray(items) ? items : [];
    const completed = values.filter((item) => item.completedAt).length;
    return { total: values.length, completed, remaining: values.length - completed };
  }

  function nextOrder(items) {
    const orders = (Array.isArray(items) ? items : [])
      .filter((item) => !item.completedAt)
      .map((item) => Number(item.order))
      .filter(Number.isFinite);
    return orders.length ? Math.max(...orders) + 1 : 0;
  }

  function moveItem(items, id, direction) {
    const source = Array.isArray(items) ? items.map((item) => ({ ...item })) : [];
    const current = source.find((item) => item.id === id);
    if (!current || current.completedAt) return source;
    const ordered = sortItems(source, "open").filter((item) => item.priority === current.priority);
    const index = ordered.findIndex((item) => item.id === id);
    const targetIndex = Math.max(0, Math.min(ordered.length - 1, index + Math.sign(direction)));
    if (index < 0 || index === targetIndex) return source;
    [ordered[index], ordered[targetIndex]] = [ordered[targetIndex], ordered[index]];
    ordered.forEach((item, order) => {
      const stored = source.find((candidate) => candidate.id === item.id);
      stored.order = order;
    });
    return source;
  }

  return Object.freeze({
    STORE_VERSION,
    SECTIONS,
    PRIORITIES,
    normalizeStore,
    sortItems,
    summary,
    todaySummary: summary,
    nextOrder,
    moveItem,
  });
});
