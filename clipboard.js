(function initializeClipboardPage() {
  "use strict";

  const core = window.ClipboardCore;
  if (!core) throw new Error("ClipboardCore is required");

  const STORAGE_KEY = "lumen-multi-clipboard-v1";
  const MAX_STORAGE_BYTES = 3 * 1024 * 1024;
  const DISPLAY_TIME_ZONE = "Asia/Shanghai";
  const SVG_NS = "http://www.w3.org/2000/svg";
  const layoutMotion = window.matchMedia("(prefers-reduced-motion: reduce)");

  const grid = document.querySelector("#clipGrid");
  const emptyState = document.querySelector("#clipboardEmpty");
  const emptyTitle = document.querySelector("#clipboardEmptyTitle");
  const count = document.querySelector("#clipboardCount");
  const search = document.querySelector("#clipSearch");
  const clearSearch = document.querySelector("#clearClipSearch");
  const dialog = document.querySelector("#clipDialog");
  const form = document.querySelector("#clipForm");
  const dialogTitle = document.querySelector("#clipDialogTitle");
  const clipId = document.querySelector("#clipId");
  const clipTitle = document.querySelector("#clipTitle");
  const clipContent = document.querySelector("#clipContent");
  const deleteFromDialog = document.querySelector("#deleteClipFromDialog");
  const toast = document.querySelector("#clipboardToast");

  let storeState = loadStore();
  let items = storeState.items;
  let activeFormat = "all";
  let returnFocus = null;
  let toastTimer = 0;
  let armedDeleteId = null;
  let armedDeleteTimer = 0;
  const expandedIds = new Set();

  function loadStore(rawValue) {
    try {
      const raw = rawValue === undefined ? localStorage.getItem(STORAGE_KEY) : rawValue;
      return core.normalizeStore(raw);
    } catch {
      return { version: core.STORE_VERSION, updatedAt: 0, items: [], unavailable: true };
    }
  }

  function payloadSize(value) {
    if (typeof TextEncoder === "function") return new TextEncoder().encode(value).byteLength;
    return value.length * 2;
  }

  function persist(nextItems) {
    if (storeState.incompatible) {
      showToast("本地数据来自更新版本，当前页面不会覆盖它");
      return false;
    }
    const payload = JSON.stringify({
      version: core.STORE_VERSION,
      updatedAt: Date.now(),
      items: nextItems,
    });
    if (payloadSize(payload) > MAX_STORAGE_BYTES) {
      showToast("剪贴内容已接近本地存储上限，请先删除较长内容");
      return false;
    }
    try {
      localStorage.setItem(STORAGE_KEY, payload);
      items = nextItems;
      storeState = { version: core.STORE_VERSION, updatedAt: Date.now(), items };
      return true;
    } catch {
      showToast("保存失败，本地存储空间可能已满");
      return false;
    }
  }

  function showToast(message) {
    window.clearTimeout(toastTimer);
    toast.textContent = message;
    toast.classList.add("is-visible");
    toastTimer = window.setTimeout(() => toast.classList.remove("is-visible"), 2300);
  }

  function clearDeleteArm() {
    window.clearTimeout(armedDeleteTimer);
    armedDeleteId = null;
    armedDeleteTimer = 0;
    deleteFromDialog.classList.remove("is-delete-armed");
    deleteFromDialog.textContent = "删除";
    grid.querySelectorAll(".is-delete-armed").forEach((button) => {
      button.classList.remove("is-delete-armed");
      button.setAttribute("aria-label", "删除");
      button.title = "删除";
    });
  }

  function createIcon(name) {
    const svg = document.createElementNS(SVG_NS, "svg");
    svg.setAttribute("aria-hidden", "true");
    const use = document.createElementNS(SVG_NS, "use");
    use.setAttribute("href", `#icon-${name}`);
    svg.append(use);
    return svg;
  }

  function createAction(name, label, action, item, className = "") {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `clip-action ${className}`.trim();
    button.dataset.clipAction = action;
    button.dataset.clipId = item.id;
    button.setAttribute("aria-label", label);
    button.title = label;
    button.append(createIcon(name));
    return button;
  }

  function appendTextWithBreaks(parent, value) {
    const parts = String(value).split("\n");
    parts.forEach((part, index) => {
      if (index) parent.append(document.createElement("br"));
      parent.append(document.createTextNode(part));
    });
  }

  function appendInlineTokens(parent, tokens) {
    tokens.forEach((token) => {
      if (token.type === "text") {
        appendTextWithBreaks(parent, token.value);
        return;
      }
      if (token.type === "code") {
        const code = document.createElement("code");
        code.textContent = token.value;
        parent.append(code);
        return;
      }

      const tagByType = {
        strong: "strong",
        emphasis: "em",
        strike: "del",
        link: "a",
      };
      const tag = tagByType[token.type];
      if (!tag) return;
      const element = document.createElement(tag);
      if (token.type === "link") {
        element.href = token.href;
        element.target = "_blank";
        element.rel = "noopener noreferrer";
      }
      appendInlineTokens(element, token.children || []);
      parent.append(element);
    });
  }

  function renderMarkdown(target, source) {
    const fragment = document.createDocumentFragment();
    core.parseMarkdown(source).forEach((block) => {
      if (block.type === "heading") {
        const heading = document.createElement(`h${block.level}`);
        appendInlineTokens(heading, block.children);
        fragment.append(heading);
        return;
      }
      if (block.type === "rule") {
        fragment.append(document.createElement("hr"));
        return;
      }
      if (block.type === "codeBlock") {
        const pre = document.createElement("pre");
        const code = document.createElement("code");
        code.textContent = block.value;
        if (block.language) code.dataset.language = block.language;
        pre.append(code);
        fragment.append(pre);
        return;
      }
      if (block.type === "quote") {
        const quote = document.createElement("blockquote");
        appendInlineTokens(quote, block.children);
        fragment.append(quote);
        return;
      }
      if (block.type === "list") {
        const list = document.createElement(block.ordered ? "ol" : "ul");
        block.items.forEach((tokens) => {
          const item = document.createElement("li");
          appendInlineTokens(item, tokens);
          list.append(item);
        });
        fragment.append(list);
        return;
      }
      if (block.type === "table") {
        const wrap = document.createElement("div");
        wrap.className = "clip-table-wrap";
        const table = document.createElement("table");
        const head = document.createElement("thead");
        const headRow = document.createElement("tr");
        block.headers.forEach((tokens, index) => {
          const cell = document.createElement("th");
          cell.dataset.align = block.alignments[index] || "left";
          appendInlineTokens(cell, tokens);
          headRow.append(cell);
        });
        head.append(headRow);
        const body = document.createElement("tbody");
        block.rows.forEach((row) => {
          const tableRow = document.createElement("tr");
          row.forEach((tokens, index) => {
            const cell = document.createElement("td");
            cell.dataset.align = block.alignments[index] || "left";
            appendInlineTokens(cell, tokens);
            tableRow.append(cell);
          });
          body.append(tableRow);
        });
        table.append(head, body);
        wrap.append(table);
        fragment.append(wrap);
        return;
      }
      if (block.type === "paragraph") {
        const paragraph = document.createElement("p");
        block.lines.forEach((tokens, index) => {
          if (index) paragraph.append(document.createElement("br"));
          appendInlineTokens(paragraph, tokens);
        });
        fragment.append(paragraph);
      }
    });
    target.replaceChildren(fragment);
  }

  function formatUpdatedAt(timestamp) {
    return new Intl.DateTimeFormat("zh-CN", {
      timeZone: DISPLAY_TIME_ZONE,
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    }).format(new Date(timestamp));
  }

  function hasLongContent(item) {
    const lineCount = item.content.split("\n").length;
    return item.content.length > 440 || lineCount > 13;
  }

  function shouldSpanWide(item) {
    const lineCount = item.content.split("\n").length;
    return item.content.length > 850 || lineCount > 24;
  }

  function buildViewSwitch(item) {
    const switcher = document.createElement("div");
    switcher.className = "clip-view-switch";
    switcher.setAttribute("role", "group");
    switcher.setAttribute("aria-label", "Markdown 显示模式");
    [
      ["preview", "阅读"],
      ["source", "源码"],
    ].forEach(([mode, label]) => {
      const button = document.createElement("button");
      const active = item.viewMode === mode;
      button.type = "button";
      button.classList.toggle("is-active", active);
      button.dataset.clipAction = "view";
      button.dataset.clipId = item.id;
      button.dataset.viewMode = mode;
      button.setAttribute("aria-pressed", String(active));
      button.textContent = label;
      switcher.append(button);
    });
    return switcher;
  }

  function buildCard(item) {
    const card = document.createElement("article");
    const longContent = hasLongContent(item);
    const expanded = expandedIds.has(item.id);
    card.className = "clip-card";
    card.dataset.clipId = item.id;
    card.dataset.format = item.format;
    card.classList.toggle("is-pinned", item.pinned);
    card.classList.toggle("is-wide", shouldSpanWide(item));
    card.classList.toggle("has-overflow", longContent);
    card.classList.toggle("is-expanded", expanded);

    const head = document.createElement("div");
    head.className = "clip-card-head";
    const badge = document.createElement("span");
    badge.className = "clip-format-badge";
    badge.textContent = item.format === "markdown" ? "MD" : "TXT";
    const actions = document.createElement("div");
    actions.className = "clip-card-actions";
    const pin = createAction("pin", item.pinned ? "取消置顶" : "置顶", "pin", item);
    pin.setAttribute("aria-pressed", String(item.pinned));
    actions.append(
      pin,
      createAction("copy", "复制内容", "copy", item),
      createAction("pencil", "编辑", "edit", item),
      createAction("trash", "删除", "delete", item, "is-danger")
    );
    head.append(badge, actions);

    const title = document.createElement("h2");
    title.textContent = item.title || core.inferTitle(item.content);

    const bodyWrap = document.createElement("div");
    bodyWrap.className = "clip-card-body-wrap";
    const body = document.createElement("div");
    body.className = "clip-card-body";
    if (item.format === "markdown" && item.viewMode === "preview") {
      body.classList.add("clip-markdown");
      renderMarkdown(body, item.content);
    } else {
      const pre = document.createElement("pre");
      pre.className = item.format === "markdown" ? "clip-source" : "clip-plain-text";
      pre.textContent = item.content;
      body.append(pre);
    }
    bodyWrap.append(body);

    const foot = document.createElement("footer");
    foot.className = "clip-card-foot";
    const updated = document.createElement("time");
    updated.className = "clip-updated";
    updated.dateTime = new Date(item.updatedAt).toISOString();
    updated.textContent = formatUpdatedAt(item.updatedAt);
    const controls = document.createElement("div");
    controls.className = "clip-card-foot-controls";
    if (item.format === "markdown") controls.append(buildViewSwitch(item));
    if (longContent) {
      const expand = document.createElement("button");
      expand.type = "button";
      expand.className = "clip-expand-button";
      expand.dataset.clipAction = "expand";
      expand.dataset.clipId = item.id;
      expand.setAttribute("aria-expanded", String(expanded));
      expand.append(document.createTextNode(expanded ? "收起" : "展开"), createIcon("chevron"));
      controls.append(expand);
    }
    foot.append(updated, controls);
    card.append(head, title, bodyWrap, foot);
    return card;
  }

  function captureCardRects() {
    return new Map(
      [...grid.querySelectorAll("[data-clip-id]")].map((card) => [
        card.dataset.clipId,
        card.getBoundingClientRect(),
      ])
    );
  }

  function animateLayout(previousRects, enteringId) {
    if (layoutMotion.matches) return;
    requestAnimationFrame(() => {
      grid.querySelectorAll(".clip-card").forEach((card) => {
        const previous = previousRects.get(card.dataset.clipId);
        if (!previous || card.dataset.clipId === enteringId) {
          card.animate(
            [
              { opacity: 0, transform: "translateY(12px) scale(0.98)" },
              { opacity: 1, transform: "translateY(0) scale(1)" },
            ],
            { duration: 300, easing: "cubic-bezier(0.22, 1, 0.36, 1)" }
          );
          return;
        }
        const next = card.getBoundingClientRect();
        const deltaX = previous.left - next.left;
        const deltaY = previous.top - next.top;
        const scaleX = previous.width / next.width;
        const scaleY = previous.height / next.height;
        if (Math.abs(deltaX) < 0.5 && Math.abs(deltaY) < 0.5 && Math.abs(scaleX - 1) < 0.01 && Math.abs(scaleY - 1) < 0.01) return;
        card.animate(
          [
            { transform: `translate(${deltaX}px, ${deltaY}px) scale(${scaleX}, ${scaleY})` },
            { transform: "translate(0, 0) scale(1)" },
          ],
          { duration: 430, easing: "cubic-bezier(0.22, 1, 0.36, 1)" }
        );
      });
    });
  }

  function renderCards({ animate = true, enteringId = null } = {}) {
    const previousRects = animate ? captureCardRects() : new Map();
    const visibleItems = core.filterAndSortItems(items, search.value, activeFormat);
    const fragment = document.createDocumentFragment();
    visibleItems.forEach((item) => fragment.append(buildCard(item)));
    grid.replaceChildren(fragment);
    grid.hidden = visibleItems.length === 0;
    emptyState.hidden = visibleItems.length !== 0;
    emptyTitle.textContent = items.length ? "没有匹配的剪贴内容" : "还没有剪贴内容";
    count.textContent = visibleItems.length === items.length
      ? `${items.length} 条`
      : `${visibleItems.length} / ${items.length} 条`;
    clearSearch.hidden = !search.value;
    if (animate && visibleItems.length) animateLayout(previousRects, enteringId);
  }

  function createId() {
    if (window.crypto?.randomUUID) return window.crypto.randomUUID();
    return `clip-${Date.now()}-${Math.random().toString(16).slice(2)}`;
  }

  function selectedFormat() {
    return form.elements.clipFormat.value === "markdown" ? "markdown" : "text";
  }

  function openNewDialog(opener) {
    if (storeState.incompatible) {
      showToast("本地数据来自更新版本，当前页面暂不允许写入");
      return;
    }
    returnFocus = opener || document.activeElement;
    clearDeleteArm();
    form.reset();
    clipId.value = "";
    dialogTitle.textContent = "新建剪贴";
    deleteFromDialog.hidden = true;
    dialog.showModal();
    requestAnimationFrame(() => clipContent.focus());
  }

  function openEditDialog(id, opener) {
    const item = items.find((candidate) => candidate.id === id);
    if (!item) return;
    returnFocus = opener || document.activeElement;
    clearDeleteArm();
    form.reset();
    clipId.value = item.id;
    clipTitle.value = item.title;
    clipContent.value = item.content;
    const format = form.querySelector(`[name="clipFormat"][value="${item.format}"]`);
    if (format) format.checked = true;
    dialogTitle.textContent = "编辑剪贴";
    deleteFromDialog.hidden = false;
    dialog.showModal();
    requestAnimationFrame(() => clipContent.focus());
  }

  function closeDialog() {
    clearDeleteArm();
    if (dialog.open) dialog.close();
  }

  function saveClip(event) {
    event.preventDefault();
    const content = clipContent.value;
    if (!content.trim()) {
      clipContent.setCustomValidity("请输入内容");
      clipContent.reportValidity();
      return;
    }
    clipContent.setCustomValidity("");
    const now = Date.now();
    const existing = items.find((item) => item.id === clipId.value);
    const format = selectedFormat();
    const item = {
      id: existing?.id || createId(),
      title: clipTitle.value.trim() || core.inferTitle(content),
      content,
      format,
      viewMode: format === "markdown" ? (existing?.viewMode || "preview") : "preview",
      pinned: Boolean(existing?.pinned),
      createdAt: existing?.createdAt || now,
      updatedAt: now,
    };
    const nextItems = existing
      ? items.map((candidate) => candidate.id === item.id ? item : candidate)
      : [...items, item];
    if (!persist(nextItems)) return;
    closeDialog();
    renderCards({ enteringId: existing ? null : item.id });
    showToast(existing ? "已更新" : "已保存");
  }

  async function copyItem(item, button) {
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(item.content);
      } else {
        const textarea = document.createElement("textarea");
        textarea.value = item.content;
        textarea.style.position = "fixed";
        textarea.style.opacity = "0";
        document.body.append(textarea);
        textarea.select();
        const copied = document.execCommand("copy");
        textarea.remove();
        if (!copied) throw new Error("copy failed");
      }
      button.classList.add("is-copied");
      button.replaceChildren(createIcon("check"));
      showToast("已复制原文");
      window.setTimeout(() => {
        if (!button.isConnected) return;
        button.classList.remove("is-copied");
        button.replaceChildren(createIcon("copy"));
      }, 1400);
    } catch {
      showToast("复制失败，请在编辑窗口中手动复制");
    }
  }

  function updateItem(id, change, options = {}) {
    const nextItems = items.map((item) => item.id === id ? { ...item, ...change } : item);
    if (!persist(nextItems)) return false;
    renderCards({ animate: options.animate !== false });
    return true;
  }

  async function deleteItem(id) {
    const item = items.find((candidate) => candidate.id === id);
    if (!item) return false;
    const nextItems = items.filter((candidate) => candidate.id !== id);
    if (!persist(nextItems)) return false;
    const card = grid.querySelector(`[data-clip-id="${CSS.escape(id)}"]`);
    if (card && !layoutMotion.matches) {
      try {
        await card.animate(
          [
            { opacity: 1, transform: "scale(1)" },
            { opacity: 0, transform: "scale(0.96) translateY(6px)" },
          ],
          { duration: 180, easing: "ease-in", fill: "forwards" }
        ).finished;
      } catch {
        // A concurrent render can safely replace the card before the exit finishes.
      }
    }
    expandedIds.delete(id);
    renderCards();
    showToast("已删除");
    return true;
  }

  async function requestDelete(id, button) {
    if (armedDeleteId !== id) {
      clearDeleteArm();
      armedDeleteId = id;
      button.classList.add("is-delete-armed");
      if (button === deleteFromDialog) {
        button.textContent = "再次点击确认删除";
      } else {
        button.setAttribute("aria-label", "再次点击确认删除");
        button.title = "再次点击确认删除";
      }
      showToast("4 秒内再次点击即可删除");
      armedDeleteTimer = window.setTimeout(clearDeleteArm, 4000);
      return false;
    }
    clearDeleteArm();
    return deleteItem(id);
  }

  document.querySelector("#newClipButton").addEventListener("click", (event) => openNewDialog(event.currentTarget));
  document.querySelector("#emptyNewClipButton").addEventListener("click", (event) => openNewDialog(event.currentTarget));
  document.querySelector("#closeClipDialog").addEventListener("click", closeDialog);
  document.querySelector("#cancelClipDialog").addEventListener("click", closeDialog);
  form.addEventListener("submit", saveClip);

  deleteFromDialog.addEventListener("click", async () => {
    if (await requestDelete(clipId.value, deleteFromDialog)) closeDialog();
  });

  dialog.addEventListener("click", (event) => {
    if (event.target === dialog) closeDialog();
  });
  dialog.addEventListener("close", () => {
    returnFocus?.focus?.();
    returnFocus = null;
  });

  search.addEventListener("input", () => renderCards());
  clearSearch.addEventListener("click", () => {
    search.value = "";
    search.focus();
    renderCards();
  });

  document.querySelectorAll("[data-format-filter]").forEach((button) => {
    button.addEventListener("click", () => {
      activeFormat = button.dataset.formatFilter;
      document.querySelectorAll("[data-format-filter]").forEach((candidate) => {
        const active = candidate === button;
        candidate.classList.toggle("is-active", active);
        candidate.setAttribute("aria-pressed", String(active));
      });
      renderCards();
    });
  });

  grid.addEventListener("click", async (event) => {
    const button = event.target.closest("[data-clip-action]");
    if (!button) return;
    const item = items.find((candidate) => candidate.id === button.dataset.clipId);
    if (!item) return;
    if (button.dataset.clipAction === "copy") await copyItem(item, button);
    if (button.dataset.clipAction === "edit") openEditDialog(item.id, button);
    if (button.dataset.clipAction === "delete") await requestDelete(item.id, button);
    if (button.dataset.clipAction === "pin") {
      updateItem(item.id, { pinned: !item.pinned, updatedAt: Date.now() });
    }
    if (button.dataset.clipAction === "view") {
      updateItem(item.id, { viewMode: button.dataset.viewMode });
    }
    if (button.dataset.clipAction === "expand") {
      if (expandedIds.has(item.id)) expandedIds.delete(item.id);
      else expandedIds.add(item.id);
      renderCards();
    }
  });

  window.addEventListener("storage", (event) => {
    if (event.key !== STORAGE_KEY) return;
    const nextStore = loadStore(event.newValue);
    if (nextStore.incompatible) {
      showToast("另一页面保存了更新版本的数据");
      return;
    }
    storeState = nextStore;
    items = nextStore.items;
    renderCards();
  });

  if (storeState.invalid) window.setTimeout(() => showToast("本地剪贴数据已损坏，已安全忽略"), 0);
  if (storeState.unavailable) window.setTimeout(() => showToast("浏览器已禁用本地存储"), 0);
  if (storeState.incompatible) window.setTimeout(() => showToast("本地数据来自更新版本，当前页面为只读"), 0);
  renderCards({ animate: false });
})();
