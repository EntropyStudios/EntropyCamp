// Lumen Today — Scriptable iPhone widget
// The endpoint and bearer token are stored only in the iOS Keychain.

const ENDPOINT_KEY = "lumen.reminder.widget.endpoint";
const TOKEN_KEY = "lumen.reminder.widget.token";
const CACHE_NAME = "lumen-reminder-widget-cache.json";

function saved(key) {
  return Keychain.contains(key) ? Keychain.get(key) : "";
}

async function configure() {
  const alert = new Alert();
  alert.title = "设置微光提醒";
  alert.message = "输入Tailscale Funnel的摘要接口和专用访问令牌。配置会保存在iPhone钥匙串中。";
  alert.addTextField("https://设备名.tailnet.ts.net/lumen/api/today", saved(ENDPOINT_KEY));
  alert.addSecureTextField("访问令牌", saved(TOKEN_KEY));
  alert.addAction("保存并预览");
  alert.addCancelAction("取消");
  const choice = await alert.present();
  if (choice < 0) return false;
  const endpoint = alert.textFieldValue(0).trim();
  const token = alert.textFieldValue(1).trim();
  if (!endpoint.startsWith("https://") || !endpoint.endsWith("/api/today") || !token) {
    const error = new Alert();
    error.title = "配置无效";
    error.message = "接口必须是以 /api/today 结尾的HTTPS地址，令牌不能为空。";
    error.addAction("知道了");
    await error.present();
    return false;
  }
  Keychain.set(ENDPOINT_KEY, endpoint);
  Keychain.set(TOKEN_KEY, token);
  return true;
}

function cacheFile() {
  const manager = FileManager.local();
  return { manager, path: manager.joinPath(manager.documentsDirectory(), CACHE_NAME) };
}

async function loadSummary() {
  const endpoint = saved(ENDPOINT_KEY);
  const token = saved(TOKEN_KEY);
  if (!endpoint || !token) {
    return { data: null, cached: false, error: "请先打开Scriptable运行脚本完成配置" };
  }
  const cache = cacheFile();
  try {
    const request = new Request(endpoint);
    request.method = "GET";
    request.headers = { Authorization: `Bearer ${token}`, Accept: "application/json" };
    request.timeoutInterval = 15;
    const data = await request.loadJSON();
    if (!data?.ok) throw new Error(data?.error || "摘要服务异常");
    cache.manager.writeString(cache.path, JSON.stringify(data));
    return { data, cached: false, error: "" };
  } catch (error) {
    if (cache.manager.fileExists(cache.path)) {
      try {
        return {
          data: JSON.parse(cache.manager.readString(cache.path)),
          cached: true,
          error: String(error.message || error),
        };
      } catch {}
    }
    return { data: null, cached: false, error: String(error.message || error) };
  }
}

function addText(container, value, size, color, weight = "regular", lines = 1) {
  const text = container.addText(value || "—");
  text.font = weight === "bold" ? Font.boldSystemFont(size) : Font.systemFont(size);
  text.textColor = new Color(color);
  text.lineLimit = lines;
  text.minimumScaleFactor = 0.78;
  return text;
}

function formatDuration(work) {
  let duration = Number(work?.durationMs) || 0;
  if (work?.active && Number(work.startedAt)) duration = Math.max(duration, Date.now() - Number(work.startedAt));
  const totalMinutes = Math.max(0, Math.floor(duration / 60000));
  const hours = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;
  return hours ? `${hours}小时${String(minutes).padStart(2, "0")}分` : `${minutes}分钟`;
}

function addDuration(container, work, size) {
  if (work?.active && Number(work.startedAt)) {
    const timer = container.addDate(new Date(work.startedAt));
    timer.applyTimerStyle();
    timer.font = Font.boldSystemFont(size);
    timer.textColor = new Color("ffffff");
    timer.lineLimit = 1;
    timer.minimumScaleFactor = 0.72;
    return timer;
  }
  return addText(container, formatDuration(work), size, "ffffff", "bold");
}

function stateStyle(state) {
  const styles = {
    due: ["需要处理", "c83d2f", "fff0ed"],
    processing: ["正在处理", "147a46", "e9f7ef"],
    countdown: ["倒计时", "286da8", "eaf4fc"],
    attention: ["保持关注", "71529a", "f3edfa"],
    idle: ["未开始", "686863", "efefec"],
    paused: ["已暂停", "70706c", "ececea"],
  };
  return styles[state] || styles.idle;
}

function addPill(container, label, foreground, background) {
  const pill = container.addStack();
  pill.backgroundColor = new Color(background);
  pill.cornerRadius = 7;
  pill.setPadding(3, 6, 3, 6);
  addText(pill, label, 8, foreground, "bold");
  return pill;
}

function addReminder(widget, reminder, compact = false) {
  const row = widget.addStack();
  row.backgroundColor = new Color("ffffff", 0.9);
  row.cornerRadius = 9;
  row.setPadding(compact ? 6 : 8, 9, compact ? 6 : 8, 9);
  row.centerAlignContent();
  const [label, foreground, background] = stateStyle(reminder.state);
  addPill(row, label, foreground, background);
  row.addSpacer(8);
  const copy = row.addStack();
  copy.layoutVertically();
  addText(copy, reminder.title, compact ? 10.5 : 11.5, "151515", "bold", 1);
  if (reminder.state === "countdown" && Number(reminder.dueAt) > Date.now()) {
    const timer = copy.addDate(new Date(reminder.dueAt));
    timer.applyTimerStyle();
    timer.font = Font.boldSystemFont(8);
    timer.textColor = new Color("286da8");
    timer.lineLimit = 1;
  }
  if (!compact && reminder.tag) {
    copy.addSpacer(1);
    addText(copy, reminder.tag, 8, "858580", "regular", 1);
  }
}

function syncState(result, data) {
  if (result.cached) return ["缓存", "9a6515", "fff0d4"];
  if (data.stale) return ["等待主页", "9a6515", "fff0d4"];
  return ["已同步", "26663f", "e8f5eb"];
}

function addEmptyState(widget, stale) {
  const empty = widget.addStack();
  empty.layoutVertically();
  empty.backgroundColor = new Color("ffffff", 0.88);
  empty.cornerRadius = 10;
  empty.setPadding(12, 12, 12, 12);
  addText(empty, stale ? "等待主页同步" : "现在很安静", 16, "171717", "bold", 1);
  empty.addSpacer(3);
  addText(
    empty,
    stale ? "打开电脑上的提醒页面后会自动更新" : "当前没有需要处理或关注的卡片",
    10,
    "73736e",
    "regular",
    2,
  );
}

function addWorkCard(container, work, options = {}) {
  const compact = options.compact === true;
  const vertical = options.vertical === true;
  const card = container.addStack();
  if (options.width) card.size = new Size(options.width, 0);
  card.backgroundColor = new Color("111111");
  card.cornerRadius = 11;
  card.setPadding(compact ? 9 : 10, 11, compact ? 9 : 10, 11);
  if (vertical) card.layoutVertically();
  else card.centerAlignContent();

  const workCopy = card.addStack();
  workCopy.layoutVertically();
  addText(workCopy, work.statusLabel, 9, "bdbdb8", "bold");
  workCopy.addSpacer(1);
  addDuration(workCopy, work, compact ? 18 : 21);
  card.addSpacer();
  const completed = card.addStack();
  if (vertical) completed.centerAlignContent();
  else completed.layoutVertically();
  const number = addText(completed, String(work.completionCount || 0), compact ? 16 : 21, "ffffff", "bold");
  if (!vertical) number.rightAlignText();
  if (vertical) completed.addSpacer(4);
  const label = addText(completed, "次完成", 8, "bdbdb8", "bold");
  if (!vertical) label.rightAlignText();
  return card;
}

function buildWidget(result) {
  const widget = new ListWidget();
  widget.backgroundColor = new Color("f1f1ee");
  widget.setPadding(13, 14, 12, 14);
  widget.refreshAfterDate = new Date(Date.now() + 15 * 60 * 1000);
  const runURL = URLScheme.forRunningScript();
  widget.url = `${runURL}${runURL.includes("?") ? "&" : "?"}refresh=1`;

  if (!result.data) {
    addText(widget, "提醒", 20, "111111", "bold");
    widget.addSpacer(12);
    addText(widget, "还没有连接电脑", 17, "242424", "bold", 2);
    widget.addSpacer(5);
    addText(widget, result.error || "请完成配置", 11, "73736e", "regular", 3);
    widget.addSpacer();
    addText(widget, "打开 Scriptable 运行脚本进行配置", 10, "8c8c86", "regular", 2);
    return widget;
  }

  const { data } = result;
  const family = config.widgetFamily || "medium";
  const isLarge = family === "large";
  const isSmall = family === "small";
  const header = widget.addStack();
  header.centerAlignContent();
  const title = header.addStack();
  title.layoutVertically();
  addText(title, "提醒", isSmall ? 15 : 17, "111111", "bold");
  addText(title, data.date.replaceAll("-", "."), 8, "7e7e79", "bold");
  header.addSpacer();
  if (data.weather) {
    const weather = header.addStack();
    weather.layoutVertically();
    addText(weather, `${Math.round(data.weather.current)}°`, isSmall ? 14 : 16, "111111", "bold");
    addText(weather, data.weather.type, 8, "71716c", "bold");
    header.addSpacer(8);
  }
  const [syncLabel, syncForeground, syncBackground] = syncState(result, data);
  addPill(header, syncLabel, syncForeground, syncBackground);

  const reminders = Array.isArray(data.reminders) ? data.reminders : [];
  const limit = isLarge ? 4 : isSmall ? 1 : 2;
  widget.addSpacer(isSmall ? 7 : 9);

  if (family === "medium") {
    const body = widget.addStack();
    addWorkCard(body, data.work, { compact: true, vertical: true, width: 112 });
    body.addSpacer(8);
    const attention = body.addStack();
    attention.layoutVertically();
    if (reminders.length) {
      const section = attention.addStack();
      addText(section, "当前关注", 10, "343432", "bold");
      section.addSpacer();
      addText(section, `${reminders.length} 项`, 9, "858580", "bold");
      attention.addSpacer(4);
      for (const reminder of reminders.slice(0, limit)) {
        addReminder(attention, reminder, true);
        attention.addSpacer(4);
      }
    } else {
      addEmptyState(attention, data.stale);
    }
  } else {
    addWorkCard(widget, data.work, { compact: isSmall });
    if (reminders.length) {
      widget.addSpacer(isSmall ? 7 : 9);
      if (!isSmall) {
        const section = widget.addStack();
        addText(section, "当前关注", 10, "343432", "bold");
        section.addSpacer();
        addText(section, `${reminders.length} 项`, 9, "858580", "bold");
        widget.addSpacer(4);
      }
      for (const reminder of reminders.slice(0, limit)) {
        addReminder(widget, reminder, !isLarge);
        widget.addSpacer(isLarge ? 5 : 4);
      }
    } else {
      widget.addSpacer(9);
      addEmptyState(widget, data.stale);
    }
  }

  if (isLarge && data.quote?.text) {
    widget.addSpacer(5);
    const quote = widget.addStack();
    quote.layoutVertically();
    quote.backgroundColor = new Color("e5e5e1");
    quote.cornerRadius = 9;
    quote.setPadding(9, 10, 9, 10);
    addText(quote, `“ ${data.quote.text}`, 11, "242424", "bold", 2);
    quote.addSpacer(2);
    addText(quote, data.quote.source || "一言", 8, "777772", "regular", 1);
  }

  if (isLarge) {
    widget.addSpacer();
    const updated = data.updatedAt ? new Date(data.updatedAt) : new Date(data.generatedAt || Date.now());
    addText(widget, `更新 ${updated.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" })} · iOS 自动刷新`, 8, "8a8a85", "regular", 1);
  }
  return widget;
}

const hasConfiguration = Boolean(saved(ENDPOINT_KEY) && saved(TOKEN_KEY));
const quickRefresh = args.queryParameters?.refresh === "1";
const wantsConfigure = args.queryParameters?.configure === "1";
if (!config.runsInWidget && (!hasConfiguration || wantsConfigure || !quickRefresh)) {
  const configured = await configure();
  if (!configured && (!saved(ENDPOINT_KEY) || !saved(TOKEN_KEY))) Script.complete();
}

const result = await loadSummary();
const widget = buildWidget(result);
Script.setWidget(widget);
if (!config.runsInWidget) await widget.presentMedium();
Script.complete();
