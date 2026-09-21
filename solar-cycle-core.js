(function exposeSolarCycleCore(root, factory) {
  const core = factory();
  if (typeof module === "object" && module.exports) module.exports = core;
  else root.SolarCycleCore = core;
})(typeof globalThis !== "undefined" ? globalThis : this, function createSolarCycleCore() {
  "use strict";

  const DISPLAY_TIME_ZONE = "Asia/Shanghai";
  const CYCLE_START_MINUTE = 8 * 60;
  const CYCLE_END_MINUTE = 24 * 60;
  const CYCLE_LENGTH_MS = (CYCLE_END_MINUTE - CYCLE_START_MINUTE) * 60 * 1000;
  const DAY_MS = 24 * 60 * 60 * 1000;
  const TIME_PARTS = new Intl.DateTimeFormat("en-GB-u-ca-gregory-nu-latn", {
    timeZone: DISPLAY_TIME_ZONE,
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hourCycle: "h23",
  });

  function clamp01(value) {
    return Math.min(1, Math.max(0, Number(value) || 0));
  }

  function beijingCycleOffset(value = Date.now()) {
    const date = value instanceof Date ? value : new Date(value);
    if (!Number.isFinite(date.getTime())) throw new TypeError("Invalid date");
    const parts = Object.fromEntries(
      TIME_PARTS.formatToParts(date)
        .filter(({ type }) => type !== "literal")
        .map(({ type, value: part }) => [type, Number(part)]),
    );
    const minute = parts.hour * 60 + parts.minute + parts.second / 60;
    return ((minute - CYCLE_START_MINUTE + 24 * 60) % (24 * 60)) * 60 * 1000;
  }

  function beijingDayProgress(value = Date.now()) {
    const offset = beijingCycleOffset(value);
    return offset < CYCLE_LENGTH_MS ? clamp01(offset / CYCLE_LENGTH_MS) : 0;
  }

  function stateForSession(session, now = Date.now()) {
    const current = session && typeof session === "object" ? session : {};
    const sampledAt = Number(now);
    const dayProgress = beijingDayProgress(sampledAt);
    const cycleOffsetMs = beijingCycleOffset(sampledAt);
    if (current.active === true) {
      const startedAt = Number(current.startedAt) || sampledAt;
      return { mode: "working", event: "work-started", token: `start:${startedAt}`, dayProgress, cycleOffsetMs, sampledAt };
    }
    if (Number.isFinite(Number(current.endedAt)) && Number(current.endedAt) > 0) {
      const endedAt = Number(current.endedAt);
      return { mode: "destroyed", event: "work-ended", token: `end:${endedAt}`, dayProgress, cycleOffsetMs, sampledAt };
    }
    return { mode: "day", event: "none", token: "", dayProgress, cycleOffsetMs, sampledAt };
  }

  return Object.freeze({
    DISPLAY_TIME_ZONE,
    CYCLE_START_MINUTE,
    CYCLE_END_MINUTE,
    CYCLE_LENGTH_MS,
    DAY_MS,
    beijingCycleOffset,
    beijingDayProgress,
    stateForSession,
  });
});
