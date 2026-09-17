(function exposeWorkHistoryCore(root, factory) {
  const core = factory();
  if (typeof module === "object" && module.exports) module.exports = core;
  if (root) root.WorkHistoryCore = core;
})(typeof globalThis !== "undefined" ? globalThis : this, function createWorkHistoryCore() {
  "use strict";

  const STORE_VERSION = 2;
  const DISPLAY_TIME_ZONE = "Asia/Shanghai";
  const MAX_NOTE_LENGTH = 1600;
  const MAX_CONVERSATIONS = 50;
  const DAY_MS = 24 * 60 * 60 * 1000;
  const MOODS = Object.freeze([
    Object.freeze({ id: "fulfilled", label: "充实", color: "#8fd1a7" }),
    Object.freeze({ id: "focused", label: "专注", color: "#85b9ef" }),
    Object.freeze({ id: "steady", label: "平稳", color: "#c7cbd1" }),
    Object.freeze({ id: "inspired", label: "有灵感", color: "#e9bf72" }),
    Object.freeze({ id: "tired", label: "疲惫", color: "#aa9bd1" }),
    Object.freeze({ id: "stressed", label: "有压力", color: "#df8b83" }),
  ]);
  const MOOD_IDS = new Set(MOODS.map((mood) => mood.id));
  const DISPLAY_PARTS = new Intl.DateTimeFormat("en-GB-u-ca-gregory-nu-latn", {
    timeZone: DISPLAY_TIME_ZONE,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  });

  function finiteTimestamp(value, fallback = null) {
    const number = Number(value);
    return Number.isFinite(number) && number >= 0 ? number : fallback;
  }

  function dateParts(value = Date.now()) {
    const date = value instanceof Date ? value : new Date(value);
    if (!Number.isFinite(date.getTime())) throw new TypeError("Invalid date");
    const values = Object.fromEntries(
      DISPLAY_PARTS.formatToParts(date)
        .filter(({ type }) => type !== "literal")
        .map(({ type, value: part }) => [type, Number(part)]),
    );
    return { year: values.year, month: values.month, day: values.day };
  }

  function dayKey(value = Date.now()) {
    const parts = dateParts(value);
    return `${parts.year}-${String(parts.month).padStart(2, "0")}-${String(parts.day).padStart(2, "0")}`;
  }

  function monthKey(value = Date.now()) {
    const parts = typeof value === "string" && /^\d{4}-\d{2}$/.test(value)
      ? { year: Number(value.slice(0, 4)), month: Number(value.slice(5, 7)) }
      : dateParts(value);
    return `${parts.year}-${String(parts.month).padStart(2, "0")}`;
  }

  function shiftMonth(value, delta) {
    const normalized = monthKey(value);
    const date = new Date(Date.UTC(Number(normalized.slice(0, 4)), Number(normalized.slice(5, 7)) - 1 + Number(delta), 1));
    return `${date.getUTCFullYear()}-${String(date.getUTCMonth() + 1).padStart(2, "0")}`;
  }

  function normalizeCounts(source) {
    const counts = {};
    if (!source || typeof source !== "object" || Array.isArray(source)) return counts;
    Object.entries(source).forEach(([cardId, count]) => {
      const number = Number(count);
      if (typeof cardId === "string" && cardId && Number.isFinite(number) && number >= 0) {
        counts[cardId] = Math.floor(number);
      }
    });
    return counts;
  }

  function normalizeBreakdown(source, countsByCardId = {}) {
    const seen = new Set();
    const rows = [];
    (Array.isArray(source) ? source : []).forEach((row) => {
      if (!row || typeof row !== "object") return;
      const cardId = typeof row.cardId === "string" ? row.cardId : "";
      if (!cardId || seen.has(cardId)) return;
      const count = Number.isFinite(Number(row.count))
        ? Math.max(0, Math.floor(Number(row.count)))
        : countsByCardId[cardId] || 0;
      if (!count) return;
      seen.add(cardId);
      rows.push({
        cardId,
        title: typeof row.title === "string" && row.title.trim() ? row.title.trim().slice(0, 80) : "Codex 对话",
        count,
      });
    });
    return rows;
  }

  function normalizeConversations(source) {
    const seen = new Set();
    const conversations = [];
    (Array.isArray(source) ? source : []).forEach((row) => {
      if (!row || typeof row !== "object") return;
      const threadId = typeof row.threadId === "string" ? row.threadId.trim().slice(0, 200) : "";
      const hostId = typeof row.hostId === "string" && /^ssh-[A-Za-z0-9][A-Za-z0-9._-]{0,63}$/.test(row.hostId)
        ? row.hostId
        : "local";
      const key = `${hostId}::${threadId}`;
      if (!threadId || seen.has(key) || conversations.length >= MAX_CONVERSATIONS) return;
      seen.add(key);
      const conversation = {
        threadId,
        title: typeof row.title === "string" && row.title.trim() ? row.title.trim().slice(0, 100) : "Codex 对话",
        threadName: typeof row.threadName === "string" && row.threadName.trim()
          ? row.threadName.trim().slice(0, 160)
          : "Codex 对话",
        count: Number.isFinite(Number(row.count)) ? Math.max(0, Math.floor(Number(row.count))) : 0,
      };
      if (hostId !== "local") conversation.hostId = hostId;
      conversations.push(conversation);
    });
    return conversations;
  }

  function groupConversationChoices(cards, countsByCardId = {}, savedConversations = []) {
    const counts = normalizeCounts(countsByCardId);
    const grouped = new Map();
    (Array.isArray(cards) ? cards : []).forEach((card) => {
      if (!card || typeof card !== "object") return;
      const cardId = typeof card.id === "string" ? card.id : "";
      const threadId = typeof card.codexThreadId === "string" ? card.codexThreadId.trim() : "";
      const hostId = typeof card.codexHost === "string" && /^ssh-[A-Za-z0-9][A-Za-z0-9._-]{0,63}$/.test(card.codexHost)
        ? card.codexHost
        : "local";
      const key = `${hostId}::${threadId}`;
      if (!threadId) return;
      const count = counts[cardId] || 0;
      const existing = grouped.get(key);
      if (existing) {
        existing.count += count;
        return;
      }
      const conversation = {
        threadId,
        title: typeof card.title === "string" && card.title.trim()
          ? card.title.trim()
          : card.codexThreadName || "Codex 对话",
        threadName: typeof card.codexThreadName === "string" && card.codexThreadName.trim()
          ? card.codexThreadName.trim()
          : "Codex 对话",
        count,
      };
      if (hostId !== "local") conversation.hostId = hostId;
      grouped.set(key, conversation);
    });
    normalizeConversations(savedConversations).forEach((conversation) => {
      const hostId = conversation.hostId || "local";
      const key = `${hostId}::${conversation.threadId}`;
      const existing = grouped.get(key);
      if (existing) {
        existing.count = Math.max(existing.count, conversation.count);
        return;
      }
      grouped.set(key, { ...conversation });
    });
    return normalizeConversations([...grouped.values()]).sort(
      (left, right) => right.count - left.count || left.title.localeCompare(right.title, "zh-CN"),
    );
  }

  function normalizeEntry(source, index = 0) {
    if (!source || typeof source !== "object") return null;
    const startedAt = finiteTimestamp(source.startedAt);
    const endedAt = finiteTimestamp(source.endedAt);
    if (startedAt === null || endedAt === null || endedAt < startedAt) return null;
    const countsByCardId = normalizeCounts(source.countsByCardId);
    const fallbackCount = Object.values(countsByCardId).reduce((total, count) => total + count, 0);
    const completionCount = Number.isFinite(Number(source.completionCount))
      ? Math.max(0, Math.floor(Number(source.completionCount)))
      : fallbackCount;
    const id = typeof source.id === "string" && source.id
      ? source.id.slice(0, 160)
      : `shift-${startedAt}-${endedAt}-${index}`;
    return {
      id,
      dayKey: dayKey(startedAt),
      startedAt,
      endedAt,
      durationMs: endedAt - startedAt,
      completionCount,
      countsByCardId,
      completions: normalizeBreakdown(source.completions, countsByCardId),
      conversations: normalizeConversations(source.conversations),
      mood: MOOD_IDS.has(source.mood) ? source.mood : "",
      note: typeof source.note === "string" ? source.note.trim().slice(0, MAX_NOTE_LENGTH) : "",
      createdAt: finiteTimestamp(source.createdAt, endedAt),
    };
  }

  function normalizeStore(raw) {
    let parsed = raw == null || raw === "" ? {} : raw;
    let invalid = false;
    if (typeof raw === "string") {
      try {
        parsed = raw ? JSON.parse(raw) : {};
      } catch {
        parsed = {};
        invalid = true;
      }
    }
    if (Array.isArray(parsed)) parsed = { version: STORE_VERSION, entries: parsed };
    if (!parsed || typeof parsed !== "object") {
      parsed = {};
      invalid = true;
    }
    const sourceVersion = Number(parsed.version || STORE_VERSION);
    if (sourceVersion > STORE_VERSION) {
      return { version: sourceVersion, updatedAt: finiteTimestamp(parsed.updatedAt, 0), entries: [], incompatible: true };
    }
    const seen = new Set();
    const entries = [];
    (Array.isArray(parsed.entries) ? parsed.entries : []).forEach((source, index) => {
      const entry = normalizeEntry(source, index);
      if (!entry || seen.has(entry.id)) return;
      seen.add(entry.id);
      entries.push(entry);
    });
    entries.sort((left, right) => left.startedAt - right.startedAt || left.endedAt - right.endedAt);
    return {
      version: STORE_VERSION,
      updatedAt: finiteTimestamp(parsed.updatedAt, 0),
      entries,
      invalid,
      migrated: sourceVersion !== STORE_VERSION,
    };
  }

  function createEntry({ id, session, endedAt = Date.now(), completionCount, completions = [], conversations = [], mood = "", note = "" }) {
    const startedAt = finiteTimestamp(session?.startedAt);
    const stop = finiteTimestamp(endedAt);
    if (startedAt === null || stop === null || stop < startedAt) throw new TypeError("Invalid work session");
    return normalizeEntry({
      id: id || `shift-${startedAt}-${stop}`,
      startedAt,
      endedAt: stop,
      completionCount,
      countsByCardId: session?.countsByCardId,
      completions,
      conversations,
      mood,
      note,
      createdAt: stop,
    });
  }

  function entriesForDay(entries, value) {
    const key = typeof value === "string" ? value : dayKey(value);
    return entries.filter((entry) => entry.dayKey === key).slice().sort((left, right) => left.startedAt - right.startedAt);
  }

  function summarize(entries) {
    const list = Array.isArray(entries) ? entries : [];
    return list.reduce((summary, entry) => {
      summary.shiftCount += 1;
      summary.durationMs += entry.durationMs;
      summary.completionCount += entry.completionCount;
      summary.firstStart = summary.firstStart === null ? entry.startedAt : Math.min(summary.firstStart, entry.startedAt);
      summary.lastEnd = summary.lastEnd === null ? entry.endedAt : Math.max(summary.lastEnd, entry.endedAt);
      if (entry.mood) summary.latestMood = entry.mood;
      if (entry.note) summary.noteCount += 1;
      return summary;
    }, {
      shiftCount: 0,
      durationMs: 0,
      completionCount: 0,
      firstStart: null,
      lastEnd: null,
      latestMood: "",
      noteCount: 0,
    });
  }

  function entriesForMonth(entries, value) {
    const prefix = `${monthKey(value)}-`;
    return entries.filter((entry) => entry.dayKey.startsWith(prefix));
  }

  function monthGrid(value, today = Date.now()) {
    const normalized = monthKey(value);
    const year = Number(normalized.slice(0, 4));
    const month = Number(normalized.slice(5, 7));
    const firstWeekdaySunday = new Date(Date.UTC(year, month - 1, 1)).getUTCDay();
    const leadingDays = (firstWeekdaySunday + 6) % 7;
    const start = Date.UTC(year, month - 1, 1 - leadingDays);
    const todayKey = dayKey(today);
    return Array.from({ length: 42 }, (_, index) => {
      const date = new Date(start + index * DAY_MS);
      const key = `${date.getUTCFullYear()}-${String(date.getUTCMonth() + 1).padStart(2, "0")}-${String(date.getUTCDate()).padStart(2, "0")}`;
      return {
        dayKey: key,
        day: date.getUTCDate(),
        inMonth: date.getUTCMonth() + 1 === month,
        isToday: key === todayKey,
      };
    });
  }

  function moodById(id) {
    return MOODS.find((mood) => mood.id === id) || null;
  }

  return Object.freeze({
    STORE_VERSION,
    DISPLAY_TIME_ZONE,
    MAX_NOTE_LENGTH,
    MAX_CONVERSATIONS,
    MOODS,
    dayKey,
    monthKey,
    shiftMonth,
    normalizeEntry,
    normalizeStore,
    groupConversationChoices,
    createEntry,
    entriesForDay,
    entriesForMonth,
    summarize,
    monthGrid,
    moodById,
  });
});
