(function exposeSharedState() {
  "use strict";
  const keys = ["lumen-reminder-cards-v1", "lumen-reminder-work-session-v1", "lumen-reminder-work-history-v1", "lumen-multi-clipboard-v1"];
  const listeners = new Set();
  let data = {};
  let revision = -1;
  let pending = 0;
  let serial = 0;
  let generation = 0;
  let chain = Promise.resolve(true);
  const lastWrite = new Map();
  const clone = (value) => JSON.parse(JSON.stringify(value));

  function equal(left, right) {
    if (left === right) return true;
    if (!left || !right || typeof left !== "object" || typeof right !== "object") return false;
    if (Array.isArray(left) !== Array.isArray(right)) return false;
    const fields = Object.keys(left);
    return fields.length === Object.keys(right).length
      && fields.every((field) => Object.prototype.hasOwnProperty.call(right, field) && equal(left[field], right[field]));
  }

  async function request(path, body) {
    const response = await fetch(path, {
      method: body ? "POST" : "GET", cache: "no-store",
      headers: { "Content-Type": "application/json", "X-Lumen-Request": "1" },
      ...(body ? { body: JSON.stringify(body) } : {}),
      signal: AbortSignal.timeout(10000),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "数据库请求失败");
    return result;
  }

  function publish(changed) {
    if (changed.length) listeners.forEach((listener) => listener({ keys: changed }));
  }

  function apply(snapshot, writeId = Infinity, changed = []) {
    const updated = new Set(changed);
    keys.forEach((key) => {
      if ((lastWrite.get(key) || 0) > writeId) return;
      if (!equal(data[key], snapshot.data[key])) updated.add(key);
      data[key] = clone(snapshot.data[key]);
    });
    revision = snapshot.revision;
    publish([...updated]);
  }

  function fail(error) {
    console.error("EntropyCamp storage:", error);
    let notice = document.querySelector("#stateFailure");
    if (!notice) {
      notice = document.createElement("div");
      notice.id = "stateFailure";
      notice.setAttribute("role", "alert");
    }
    const target = document.querySelector("dialog[open] form") || document.querySelector("dialog[open]") || document.body;
    const placement = target === document.body ? "position:fixed;z-index:1000;bottom:12px;left:12px;right:12px;" : "margin-top:12px;";
    notice.style.cssText = placement + "padding:12px;background:#522522;color:#fff;font:13px system-ui;border-radius:6px;overflow-wrap:anywhere;max-height:35vh;overflow:auto";
    notice.textContent = `数据库操作失败：${error.message || error}。此次修改没有保存，请保留编辑内容并重试。`;
    if (notice.parentElement !== target) target.append(notice);
    notice.scrollIntoView?.({ block: "nearest" });
  }

  const ready = (async () => {
    let snapshot = await request("/api/state");
    if (!snapshot.initialized) {
      const legacy = {};
      keys.forEach((key) => {
        const raw = localStorage.getItem(key);
        if (raw !== null) legacy[key] = JSON.parse(raw);
      });
      for (const [key, core] of [[keys[2], window.WorkHistoryCore], [keys[3], window.ClipboardCore]]) {
        if (!(key in legacy)) continue;
        const normalized = core.normalizeStore(legacy[key]);
        if (normalized.invalid || normalized.incompatible) throw new Error("旧数据需要检查，已停止自动迁移");
        legacy[key] = normalized;
      }
      snapshot = await request("/api/state/import", { data: legacy });
    }
    apply(snapshot);
  })();

  function setItems(values, baselines = {}) {
    const updates = {};
    Object.entries(values).forEach(([key, raw]) => {
      if (!keys.includes(key)) throw new Error("Unknown business state key");
      const value = JSON.parse(raw);
      if (equal(value, data[key])) return;
      updates[key] = { base: key in baselines ? JSON.parse(baselines[key]) : clone(data[key]), value };
    });
    if (!Object.keys(updates).length) return pending ? chain : Promise.resolve(true);
    const id = ++serial;
    const epoch = generation;
    Object.entries(updates).forEach(([key, change]) => { data[key] = clone(change.value); lastWrite.set(key, id); });
    pending += 1;
    chain = chain.then(async () => {
      try {
        if (epoch !== generation) return false;
        const snapshot = await request("/api/state", { updates });
        apply(snapshot, id, Object.keys(updates));
        document.querySelector("#stateFailure")?.remove();
        return true;
      } catch (error) {
        generation += 1;
        const snapshot = await request("/api/state").catch(() => null);
        if (snapshot) apply(snapshot);
        fail(error);
        return false;
      } finally {
        pending -= 1;
      }
    });
    return chain;
  }

  async function refresh() {
    if (pending || document.hidden) return;
    try {
      await ready;
      const snapshot = await request(`/api/state?revision=${revision}`);
      if (!snapshot.unchanged && !pending) apply(snapshot);
    } catch (error) { console.warn("Shared state refresh failed:", error.message); }
  }

  window.EntropyState = {
    ready, fail, refresh,
    getItem: (key) => key in data ? JSON.stringify(data[key]) : null,
    setItem: (key, value, base) => setItems({ [key]: value }, base === undefined ? {} : { [key]: base }),
    setItems,
    subscribe: (listener) => { listeners.add(listener); return () => listeners.delete(listener); },
  };
  window.addEventListener("beforeunload", (event) => {
    if (pending) { event.preventDefault(); event.returnValue = ""; }
  });
  window.addEventListener("focus", refresh);
  document.addEventListener("visibilitychange", refresh);
  setInterval(refresh, 3000);
})();
