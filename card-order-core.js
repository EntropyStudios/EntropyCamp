(function exposeCardOrderCore(root, factory) {
  const api = factory();
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  if (root) root.CardOrderCore = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function createCardOrderCore() {
  const PRIORITY = Object.freeze({
    due: 0,
    processing: 1,
    countdown: 1,
    attention: 2,
    idle: 3,
    paused: 4,
  });
  const ACTIVE_CODEX_STATUSES = new Set(["active", "inProgress", "running", "working"]);

  function displayState(card, options = {}) {
    const workActive = options.workActive !== false;
    const now = Number.isFinite(options.now) ? options.now : Date.now();
    if (!workActive) return "paused";
    if (card?.codexThreadId) {
      if (card.codexDue) return "due";
      return ACTIVE_CODEX_STATUSES.has(card.codexStatus) || (card.codexPhase && card.codexPhase !== "idle")
        ? "processing"
        : "attention";
    }
    if (!card?.started) return "idle";
    if (Number.isFinite(card.nextAt) && card.nextAt <= now) return "due";
    return "countdown";
  }

  function sortCards(cards, options = {}) {
    if (!Array.isArray(cards)) return [];
    return cards
      .map((card, index) => ({ card, index, priority: PRIORITY[displayState(card, options)] }))
      .sort((left, right) => left.priority - right.priority || left.index - right.index)
      .map(({ card }) => card);
  }

  return Object.freeze({
    PRIORITY,
    displayState,
    sortCards,
  });
});
