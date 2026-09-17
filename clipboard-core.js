(function attachClipboardCore(root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  if (root) root.ClipboardCore = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function createClipboardCore() {
  "use strict";

  const STORE_VERSION = 1;
  const MAX_ITEMS = 500;
  const MAX_TITLE_LENGTH = 80;

  function finiteTimestamp(value, fallback) {
    const number = Number(value);
    return Number.isFinite(number) && number > 0 ? number : fallback;
  }

  function normalizeStore(rawValue, now = Date.now()) {
    let parsed = rawValue;
    if (typeof parsed === "string") {
      try {
        parsed = JSON.parse(parsed);
      } catch {
        return { version: STORE_VERSION, updatedAt: 0, items: [], invalid: true };
      }
    }

    if (Array.isArray(parsed)) parsed = { version: 0, items: parsed };
    if (!parsed || typeof parsed !== "object") {
      return { version: STORE_VERSION, updatedAt: 0, items: [] };
    }

    const sourceVersion = Number.isFinite(Number(parsed.version)) ? Number(parsed.version) : 0;
    if (sourceVersion > STORE_VERSION) {
      return {
        version: sourceVersion,
        updatedAt: finiteTimestamp(parsed.updatedAt, 0),
        items: [],
        incompatible: true,
      };
    }

    const seen = new Set();
    const sourceItems = Array.isArray(parsed.items) ? parsed.items : [];
    const items = [];
    for (let index = 0; index < sourceItems.length && items.length < MAX_ITEMS; index += 1) {
      const source = sourceItems[index];
      if (!source || typeof source !== "object") continue;
      const createdAt = finiteTimestamp(source.createdAt, finiteTimestamp(source.updatedAt, now));
      const updatedAt = finiteTimestamp(source.updatedAt, createdAt);
      let id = typeof source.id === "string" ? source.id.trim().slice(0, 120) : "";
      if (!id || seen.has(id)) id = `legacy-${createdAt}-${index}`;
      while (seen.has(id)) id = `${id}-copy`;
      seen.add(id);

      const format = source.format === "markdown" || source.format === "md" ? "markdown" : "text";
      items.push({
        id,
        title: typeof source.title === "string" ? source.title.slice(0, MAX_TITLE_LENGTH) : "",
        content: typeof source.content === "string" ? source.content : String(source.content ?? ""),
        format,
        viewMode: format === "markdown" && source.viewMode === "source" ? "source" : "preview",
        pinned: Boolean(source.pinned),
        createdAt,
        updatedAt,
      });
    }

    return {
      version: STORE_VERSION,
      updatedAt: finiteTimestamp(parsed.updatedAt, 0),
      items,
      migrated: sourceVersion !== STORE_VERSION,
    };
  }

  function filterAndSortItems(items, query = "", format = "all") {
    const needle = String(query).trim().toLocaleLowerCase("zh-CN");
    return items
      .filter((item) => format === "all" || item.format === format)
      .filter((item) => {
        if (!needle) return true;
        return `${item.title}\n${item.content}`.toLocaleLowerCase("zh-CN").includes(needle);
      })
      .slice()
      .sort((left, right) => {
        if (left.pinned !== right.pinned) return left.pinned ? -1 : 1;
        if (left.updatedAt !== right.updatedAt) return right.updatedAt - left.updatedAt;
        return left.createdAt - right.createdAt;
      });
  }

  function inferTitle(content) {
    const firstLine = String(content)
      .split(/\r?\n/)
      .map((line) => line.trim())
      .find(Boolean);
    if (!firstLine) return "未命名片段";
    const cleaned = firstLine
      .replace(/^#{1,6}\s+/, "")
      .replace(/^[-+*>]\s+/, "")
      .replace(/^\d+[.)]\s+/, "")
      .replace(/^[`*_~]+|[`*_~]+$/g, "")
      .trim();
    return (cleaned || "未命名片段").slice(0, 36);
  }

  function safeUrl(value) {
    const url = String(value).trim();
    return /^(?:https?:|mailto:)/i.test(url) ? url : null;
  }

  function parseInline(source) {
    const text = String(source);
    const tokens = [];
    let buffer = "";

    function flush() {
      if (!buffer) return;
      tokens.push({ type: "text", value: buffer });
      buffer = "";
    }

    function pushWrapped(type, start, end, markerLength) {
      flush();
      tokens.push({
        type,
        children: parseInline(text.slice(start + markerLength, end)),
      });
      return end + markerLength;
    }

    let index = 0;
    while (index < text.length) {
      if (text[index] === "\\" && index + 1 < text.length) {
        buffer += text[index + 1];
        index += 2;
        continue;
      }

      if (text[index] === "`") {
        const end = text.indexOf("`", index + 1);
        if (end !== -1) {
          flush();
          tokens.push({ type: "code", value: text.slice(index + 1, end) });
          index = end + 1;
          continue;
        }
      }

      const pair = text.slice(index, index + 2);
      if (pair === "**" || pair === "__") {
        const end = text.indexOf(pair, index + 2);
        if (end > index + 2) {
          index = pushWrapped("strong", index, end, 2);
          continue;
        }
      }
      if (pair === "~~") {
        const end = text.indexOf(pair, index + 2);
        if (end > index + 2) {
          index = pushWrapped("strike", index, end, 2);
          continue;
        }
      }

      if (text[index] === "[") {
        const labelEnd = text.indexOf("](", index + 1);
        let hrefEnd = -1;
        if (labelEnd !== -1) {
          let depth = 0;
          for (let cursor = labelEnd + 2; cursor < text.length; cursor += 1) {
            if (text[cursor] === "\\") {
              cursor += 1;
              continue;
            }
            if (text[cursor] === "(") {
              depth += 1;
              continue;
            }
            if (text[cursor] !== ")") continue;
            if (depth > 0) {
              depth -= 1;
              continue;
            }
            hrefEnd = cursor;
            break;
          }
        }
        if (labelEnd > index + 1 && hrefEnd > labelEnd + 2) {
          const hrefSource = text.slice(labelEnd + 2, hrefEnd);
          const href = safeUrl(hrefSource);
          flush();
          if (href) {
            tokens.push({
              type: "link",
              href,
              children: parseInline(text.slice(index + 1, labelEnd)),
            });
          } else {
            tokens.push({ type: "text", value: text.slice(index, hrefEnd + 1) });
          }
          index = hrefEnd + 1;
          continue;
        }
      }

      if (text[index] === "*" || text[index] === "_") {
        const marker = text[index];
        const end = text.indexOf(marker, index + 1);
        if (end > index + 1) {
          index = pushWrapped("emphasis", index, end, 1);
          continue;
        }
      }

      buffer += text[index];
      index += 1;
    }
    flush();
    return tokens;
  }

  function isHorizontalRule(line) {
    return /^\s{0,3}(?:(?:-\s*){3,}|(?:_\s*){3,}|(?:\*\s*){3,})$/.test(line);
  }

  function splitTableRow(line) {
    const text = String(line).trim();
    const cells = [];
    let cell = "";
    let inCode = false;
    let separators = 0;
    for (let index = 0; index < text.length; index += 1) {
      const character = text[index];
      if (character === "\\" && index + 1 < text.length) {
        cell += character + text[index + 1];
        index += 1;
        continue;
      }
      if (character === "`") {
        inCode = !inCode;
        cell += character;
        continue;
      }
      if (character === "|" && !inCode) {
        cells.push(cell.trim());
        cell = "";
        separators += 1;
        continue;
      }
      cell += character;
    }
    cells.push(cell.trim());
    if (!separators) return null;
    if (text.startsWith("|")) cells.shift();
    if (text.endsWith("|") && !text.endsWith("\\|")) cells.pop();
    return cells;
  }

  function tableAlignmentRow(line) {
    const cells = splitTableRow(line);
    if (!cells?.length) return null;
    const alignments = [];
    for (const cell of cells) {
      const marker = cell.replace(/\s+/g, "");
      if (!/^:?-{3,}:?$/.test(marker)) return null;
      alignments.push(marker.startsWith(":") && marker.endsWith(":")
        ? "center"
        : marker.endsWith(":")
          ? "right"
          : "left");
    }
    return alignments;
  }

  function tableAt(lines, index) {
    const headers = splitTableRow(lines[index]);
    const alignments = index + 1 < lines.length ? tableAlignmentRow(lines[index + 1]) : null;
    if (!headers?.length || !alignments || headers.length !== alignments.length) return null;
    return { headers, alignments };
  }

  function isBlockStart(line) {
    return /^\s{0,3}(?:```|~~~|#{1,6}\s+|>\s?|[-+*]\s+|\d+[.)]\s+)/.test(line)
      || isHorizontalRule(line);
  }

  function parseMarkdown(source) {
    const lines = String(source).replace(/\r\n?/g, "\n").split("\n");
    const blocks = [];
    let index = 0;

    while (index < lines.length) {
      const line = lines[index];
      if (!line.trim()) {
        index += 1;
        continue;
      }

      const fence = line.match(/^\s{0,3}(`{3,}|~{3,})\s*([^\s]*)\s*$/);
      if (fence) {
        const marker = fence[1][0];
        const minimum = fence[1].length;
        const code = [];
        index += 1;
        while (index < lines.length) {
          const close = lines[index].match(/^\s{0,3}(`{3,}|~{3,})\s*$/);
          if (close && close[1][0] === marker && close[1].length >= minimum) {
            index += 1;
            break;
          }
          code.push(lines[index]);
          index += 1;
        }
        blocks.push({ type: "codeBlock", language: fence[2].slice(0, 24), value: code.join("\n") });
        continue;
      }

      const heading = line.match(/^\s{0,3}(#{1,6})\s+(.+)$/);
      if (heading) {
        blocks.push({ type: "heading", level: heading[1].length, children: parseInline(heading[2]) });
        index += 1;
        continue;
      }

      const table = tableAt(lines, index);
      if (table) {
        const rows = [];
        index += 2;
        while (index < lines.length && lines[index].trim()) {
          const cells = splitTableRow(lines[index]);
          if (!cells) break;
          rows.push(Array.from(
            { length: table.headers.length },
            (_, cellIndex) => parseInline(cells[cellIndex] || ""),
          ));
          index += 1;
        }
        blocks.push({
          type: "table",
          alignments: table.alignments,
          headers: table.headers.map(parseInline),
          rows,
        });
        continue;
      }

      if (isHorizontalRule(line)) {
        blocks.push({ type: "rule" });
        index += 1;
        continue;
      }

      if (/^\s{0,3}>/.test(line)) {
        const quote = [];
        while (index < lines.length && /^\s{0,3}>/.test(lines[index])) {
          quote.push(lines[index].replace(/^\s{0,3}>\s?/, ""));
          index += 1;
        }
        blocks.push({ type: "quote", children: parseInline(quote.join("\n")) });
        continue;
      }

      const listMatch = line.match(/^\s{0,3}([-+*]|\d+[.)])\s+(.+)$/);
      if (listMatch) {
        const ordered = /^\d/.test(listMatch[1]);
        const items = [];
        while (index < lines.length) {
          const item = lines[index].match(/^\s{0,3}([-+*]|\d+[.)])\s+(.+)$/);
          if (!item || /^\d/.test(item[1]) !== ordered) break;
          items.push(parseInline(item[2]));
          index += 1;
        }
        blocks.push({ type: "list", ordered, items });
        continue;
      }

      const paragraph = [line];
      index += 1;
      while (
        index < lines.length
        && lines[index].trim()
        && !isBlockStart(lines[index])
        && !tableAt(lines, index)
      ) {
        paragraph.push(lines[index]);
        index += 1;
      }
      blocks.push({ type: "paragraph", lines: paragraph.map(parseInline) });
    }
    return blocks;
  }

  return Object.freeze({
    STORE_VERSION,
    MAX_ITEMS,
    MAX_TITLE_LENGTH,
    normalizeStore,
    filterAndSortItems,
    inferTitle,
    safeUrl,
    parseInline,
    parseMarkdown,
  });
});
