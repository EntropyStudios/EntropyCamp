(async function initializeReminderApp() {
await window.EntropyState.ready;
const businessState = window.EntropyState;
const STORAGE_KEY = "lumen-reminder-cards-v1";
const WORK_SESSION_KEY = "lumen-reminder-work-session-v1";
const WORK_HISTORY_KEY = "lumen-reminder-work-history-v1";
const DAILY_QUOTE_KEY = "lumen-reminder-hourly-quote-v1";
const WEATHER_CACHE_KEY = "lumen-reminder-weather-v1";
const HEADER_CLOCK_KEY = "lumen-reminder-header-clock-v1";
const WIDGET_SOURCE_KEY = "lumen-reminder-widget-source-v1";
const UNIT_MS = {
  minute: 60 * 1000,
  hour: 60 * 60 * 1000,
  day: 24 * 60 * 60 * 1000,
};
const cardOrderCore = window.CardOrderCore;
const workHistoryCore = window.WorkHistoryCore;
const WORK_HISTORY_STORE_VERSION = workHistoryCore?.STORE_VERSION || 1;

let cards = loadCards();
let workSession = loadWorkSession();
let workHistoryStore = loadWorkHistory();
let codexThreads = [];
let codexAvailable = false;
let codexSyncing = false;
let codexEventSource = null;
let codexEventKey = "";
let workSessionBusy = false;
let workReflectionReturnFocus = null;
let workReflectionPreview = false;
let workReflectionConversationOptions = [];
let editingCardsBase;
let reflectionStartedFor;

const CODEX_FALLBACK_SYNC_MS = 60 * 1000;
const WIDGET_SNAPSHOT_SYNC_MS = 30 * 1000;
const CARD_LAYOUT_ANIMATION_MS = 680;
const QUOTE_REFRESH_MS = 60 * 60 * 1000;
const QUOTE_HISTORY_LIMIT = 400;
const QUOTE_API_URL = "https://v1.hitokoto.cn/?encode=json&charset=utf-8&min_length=6&max_length=36&c=k";
const WEATHER_REFRESH_MS = 30 * 60 * 1000;
const WEATHER_DEFAULT_LOCATION = {
  label: "杭州",
  latitude: 30.2741,
  longitude: 120.1551,
};
const DISPLAY_TIME_ZONE = "Asia/Shanghai";
const DISPLAY_UTC_OFFSET_MS = 8 * UNIT_MS.hour;
const DISPLAY_TIME_PARTS_FORMATTER = new Intl.DateTimeFormat("en-GB-u-ca-gregory-nu-latn", {
  timeZone: DISPLAY_TIME_ZONE,
  hourCycle: "h23",
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
});
const HEADER_CLOCKS = [
  {
    id: "corpus",
    label: "Corpus Clock 圣体钟",
    shortLabel: "圣体钟",
    meaning: "时间会吞噬一切",
    skinId: "corpusClockSkin",
    timeId: "corpusClockTime",
    titleNote: "显示北京时间",
  },
  {
    id: "big-ben",
    label: "Big Ben · 伊丽莎白塔",
    shortLabel: "大本钟",
    meaning: "精准与公共秩序",
    skinId: "bigBenClock",
    timeId: "bigBenClockTime",
    titleNote: "显示北京时间；塔顶灯借用议会夜间开会含义表示上班中",
  },
  {
    id: "prague-orloj",
    label: "Prague Orloj · 布拉格天文钟",
    shortLabel: "布拉格天文钟",
    meaning: "在宇宙秩序中珍惜此刻",
    skinId: "pragueOrlojClock",
    timeId: "pragueOrlojClockTime",
    titleNote: "金手显示北京时间；黄道、月相与旧捷克时保留布拉格天文结构",
  },
  {
    id: "bern-zytglogge",
    label: "Bern Zytglogge · 伯尔尼时钟塔",
    shortLabel: "伯尔尼时钟塔",
    meaning: "让公共生活与宇宙节律彼此相遇",
    skinId: "bernZytgloggeClock",
    timeId: "bernZytgloggeClockTime",
    titleNote: "上下表盘显示北京时间；黄道、月相与整点机关按同一时基运行",
  },
];
const BIG_BEN_CENTER = { x: 512, y: 710 };
const BIG_BEN_ROMAN_NUMERALS = [
  "XII", "I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI",
];
const BIG_BEN_HAND_TICK_MS = 2000;
const CORPUS_CLOCK_NS = "http://www.w3.org/2000/svg";
const PRAGUE_ORLOJ_CENTER = { x: 512, y: 612 };
const PRAGUE_ORLOJ_LATITUDE = 50.087;
const PRAGUE_ORLOJ_LONGITUDE = 14.421;
const PRAGUE_ORLOJ_EQUATOR_RADIUS = 190;
const PRAGUE_ORLOJ_ZODIAC_RADIUS = 207.5;
const PRAGUE_ORLOJ_ZODIAC_CENTER_OFFSET = { x: -81.8, y: 0 };
const PRAGUE_ORLOJ_SYNODIC_MONTH_DAYS = 29.5322986;
const PRAGUE_ORLOJ_NEW_MOON_JD = 2451550.2597;
const PRAGUE_ORLOJ_ROMAN_NUMERALS = [
  "XII", "I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI",
];
const PRAGUE_ORLOJ_ZODIAC_GLYPHS = ["♈︎", "♉︎", "♊︎", "♋︎", "♌︎", "♍︎", "♎︎", "♏︎", "♐︎", "♑︎", "♒︎", "♓︎"];
const PRAGUE_ORLOJ_MONTHS = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"];
const BERN_ZYTGLOGGE_SYNODIC_MONTH_DAYS = 29.530588853;
const BERN_ZYTGLOGGE_NEW_MOON_JD = 2451550.25972;
const BERN_ZYTGLOGGE_SIDEREAL_RATE = 1.00273790935;
const BERN_ZYTGLOGGE_LONGITUDE = 7.4474;
const BERN_ZYTGLOGGE_CENTER = Object.freeze({ x: 350, y: 820 });
const BERN_ZYTGLOGGE_ZODIAC_CENTER_OFFSET = Object.freeze({ x: 0, y: -38 });
const BERN_ZYTGLOGGE_ZODIAC_OUTER_RADIUS = 151;
const BERN_ZYTGLOGGE_AUTOMATON_LEAD_SECONDS = 210;
const BERN_ZYTGLOGGE_AUTOMATON_TIMELINE = Object.freeze({
  openingRoosterEnd: 12,
  bearParadeEnd: 176,
  jesterFeatureStart: 160,
  secondRoosterEnd: 188,
  hourThreshold: BERN_ZYTGLOGGE_AUTOMATON_LEAD_SECONDS,
  quarterBellsEnd: 216,
  chronosEnd: 222,
  hansStrikeSpacing: 1.45,
  hansRelease: 0.75,
  finalRoosterDuration: 9,
});
const CORPUS_CLOCK_CENTER = { x: 512, y: 690 };
const CORPUS_BODY_PIVOT = { x: 474, y: 241 };
const CORPUS_ESCAPE_TOOTH_COUNT = 60;
const CORPUS_ESCAPE_TOOTH_ANGLE = 360 / CORPUS_ESCAPE_TOOTH_COUNT;
const CORPUS_ESCAPE_TIP_PHASE = CORPUS_ESCAPE_TOOTH_ANGLE * 0.084;
// Align the live tooth crowns with the photographed pallet faces.  The pallet
// contact is solved from its fixed body joint; the tooth slides along that
// face instead of dragging the visible joint around the dial.
const CORPUS_ESCAPE_VISUAL_PHASE_ADJUST = 3.36;
const CORPUS_ESCAPE_TIP_RADIUS = 389;
const CORPUS_PALLET_CONTACT_RADIUS = 382;
const CORPUS_PALLET_AIRBORNE_RADIUS = 400;
// Each angle lands the photographed pallet face on a real swept-tooth phase.
// The pad centre sits at r=382; its outer 7 px contact edge meets the r=389 tip.
const CORPUS_PALLET_CONTACT_ANGLES = { front: -113.496, rear: -83.496 };
const CORPUS_ESCAPEMENT_TIMING = {
  handoffEnd: 0.025,
  releaseEnd: 0.16,
  // Start the returning foot shortly after the airborne apex.  Compressing
  // the whole descent into the final 115 ms reads as a loop restart even when
  // the mathematical endpoints are continuous.
  approachStart: 0.62,
  catchStart: 0.975,
};
const CORPUS_ESCAPE_BACKLASH_DEGREES = 0.24;
const CORPUS_REGISTERED_ASSET_PLACEMENT = {
  x: 242,
  y: -25,
  scaleX: 500 / 1024,
  scaleY: 420 / 861,
};
const CORPUS_RIG_UNIFORM_SCALE = CORPUS_REGISTERED_ASSET_PLACEMENT.scaleX;
const placeCorpusRegisteredPoint = (point) => ({
  x: CORPUS_REGISTERED_ASSET_PLACEMENT.x +
    point.x * CORPUS_REGISTERED_ASSET_PLACEMENT.scaleX,
  y: CORPUS_REGISTERED_ASSET_PLACEMENT.y +
    point.y * CORPUS_REGISTERED_ASSET_PLACEMENT.scaleY,
});
// v4 cover anchors are registered in the 1024x861 asset canvas.  Each visible
// pallet is one fixed-size photographed member.  Its foot follows the circle
// produced by the fixed carrier pivot and fixed pivot-to-contact length; scale
// never participates in tooth contact.
const CORPUS_PALLET_RIG = {
  front: {
    carrierPivot: placeCorpusRegisteredPoint({ x: 438.4, y: 441.374 }),
    sourcePivot: { x: 438.4, y: 441.374 },
    sourceContact: { x: 225.92, y: 743.94 },
    sourceContactEdge: [
      { x: 211.84, y: 747.138 },
      { x: 240, y: 740.741 },
    ],
  },
  rear: {
    carrierPivot: placeCorpusRegisteredPoint({ x: 535.68, y: 631.357 }),
    sourcePivot: { x: 535.68, y: 631.357 },
    sourceContact: { x: 668.8, y: 740.741 },
    sourceContactEdge: [
      { x: 652.16, y: 738.183 },
      { x: 685.44, y: 743.3 },
    ],
  },
};
const CORPUS_CLOCK_RING_SPECS = {
  hour: { total: 48, radius: 194, trail: 2, transitionMs: 760 },
  minute: { total: 60, radius: 258, trail: 3, transitionMs: 650 },
  second: { total: 60, radius: 316, trail: 5, transitionMs: 520 },
};

let corpusClockAnimationFrame = null;
let activeHeaderClockId = null;
let headerClockDayKey = null;
let bigBenLastBeat = null;
let bigBenMinuteAngle = null;
let bigBenHourAngle = null;
let bigBenLastLabel = null;
let bigBenLastNight = null;
let bigBenLastChiming = null;
let bigBenSyncToken = 0;
let pragueOrlojLastMinute = null;
let pragueOrlojLastLabel = null;
let pragueOrlojSyncToken = 0;
let pragueOrlojSunAngle = null;
let pragueOrlojZodiacAngle = null;
let pragueOrlojMoonAngle = null;
let pragueOrlojOldCzechAngle = null;
let pragueOrlojCalendarAngle = null;
let bernZytgloggeLastBeat = null;
let bernZytgloggeLastLabel = null;
let bernZytgloggeLastDayKey = null;
let bernZytgloggeSyncToken = 0;
let bernZytgloggeMainHourAngle = null;
let bernZytgloggeMainMinuteAngle = null;
let bernZytgloggeSunAngle = null;
let bernZytgloggeZodiacAngle = null;
let bernZytgloggeMoonAngle = null;
let bernZytgloggeCalendarAngle = null;
let dailyQuoteSlot = null;
let dailyQuoteSyncing = false;
let weatherSyncing = false;
let feishuStatusState = null;
let feishuSettingsBusy = false;
let widgetSnapshotTimer = null;
let widgetSnapshotSyncing = false;
let widgetSnapshotPending = false;
let conversationGraphController = null;
let conversationGraphMountVersion = 0;
let conversationGraphMountPromise = null;
let conversationGraphPending = null;
let conversationGraphRenderFrame = 0;
let conversationGraphDisposed = false;

const grid = document.querySelector("#cardGrid");
const dialog = document.querySelector("#cardDialog");
const form = document.querySelector("#cardForm");
const workSummary = document.querySelector("#workSummary");
const workToggleButton = document.querySelector("#workToggleButton");
const workReflectionDialog = document.querySelector("#workReflectionDialog");
const workReflectionForm = document.querySelector("#workReflectionForm");
const workReflectionNote = document.querySelector("#workReflectionNote");
const workReflectionStatus = document.querySelector("#workReflectionStatus");
const reflectionStartedAt = document.querySelector("#reflectionStartedAt");
const reflectionDuration = document.querySelector("#reflectionDuration");
const reflectionCount = document.querySelector("#reflectionCount");
const workReflectionThreads = document.querySelector("#workReflectionThreads");
const workReflectionThreadCount = document.querySelector("#workReflectionThreadCount");
const toggleReflectionThreads = document.querySelector("#toggleReflectionThreads");
const confirmWorkReflection = document.querySelector("#confirmWorkReflection");
const feishuQuickControl = document.querySelector("#feishuQuickControl");
const feishuSettingsButton = document.querySelector("#feishuSettingsButton");
const feishuQuickEnabled = document.querySelector("#feishuQuickEnabled");
const feishuDialog = document.querySelector("#feishuDialog");
const feishuForm = document.querySelector("#feishuForm");
const feishuEnabled = document.querySelector("#feishuEnabled");
const feishuWebhook = document.querySelector("#feishuWebhook");
const feishuSecret = document.querySelector("#feishuSecret");
const feishuConnection = document.querySelector("#feishuConnection");
const feishuConnectionTitle = document.querySelector("#feishuConnectionTitle");
const feishuConnectionDetail = document.querySelector("#feishuConnectionDetail");
const feishuFormStatus = document.querySelector("#feishuFormStatus");
const testFeishuButton = document.querySelector("#testFeishuButton");
const saveFeishuButton = document.querySelector("#saveFeishuButton");
const corpusClock = document.querySelector("#corpusClock");
const corpusClockSkin = document.querySelector("#corpusClockSkin");
const bigBenClock = document.querySelector("#bigBenClock");
const bigBenMinuteTicks = document.querySelector("#bigBenMinuteTicks");
const bigBenRomanNumerals = document.querySelector("#bigBenRomanNumerals");
const bigBenOpalLattice = document.querySelector("#bigBenOpalLattice");
const bigBenHourHand = document.querySelector("#bigBenHourHand");
const bigBenMinuteHand = document.querySelector("#bigBenMinuteHand");
const bigBenClockTime = document.querySelector("#bigBenClockTime");
const pragueOrlojClock = document.querySelector("#pragueOrlojClock");
const pragueOrlojClockTime = document.querySelector("#pragueOrlojClockTime");
const pragueOrlojOldCzechRing = document.querySelector("#pragueOrlojOldCzechRing");
const pragueOrlojOldCzechNumerals = document.querySelector("#pragueOrlojOldCzechNumerals");
const pragueOrlojCivilNumerals = document.querySelector("#pragueOrlojCivilNumerals");
const pragueOrlojBabylonianLines = document.querySelector("#pragueOrlojBabylonianLines");
const pragueOrlojZodiac = document.querySelector("#pragueOrlojZodiac");
const pragueOrlojZodiacDivisions = document.querySelector("#pragueOrlojZodiacDivisions");
const pragueOrlojZodiacGlyphs = document.querySelector("#pragueOrlojZodiacGlyphs");
const pragueOrlojSunHand = document.querySelector("#pragueOrlojSunHand");
const pragueOrlojSunSymbol = document.querySelector("#pragueOrlojSunSymbol");
const pragueOrlojMoonHand = document.querySelector("#pragueOrlojMoonHand");
const pragueOrlojMoonSymbol = document.querySelector("#pragueOrlojMoonSymbol");
const pragueOrlojMoonLight = document.querySelector("#pragueOrlojMoonLight");
const pragueOrlojCalendarDisk = document.querySelector("#pragueOrlojCalendarDisk");
const pragueOrlojCalendarMarks = document.querySelector("#pragueOrlojCalendarMarks");
const pragueOrlojLeftApostles = document.querySelector("#pragueOrlojLeftApostles");
const pragueOrlojRightApostles = document.querySelector("#pragueOrlojRightApostles");
const bernZytgloggeClock = document.querySelector("#bernZytgloggeClock");
const bernZytgloggeClockTime = document.querySelector("#bernZytgloggeClockTime");
const bernZytgloggeMainHourHand = document.querySelector("#bernZytgloggeMainHourHand");
const bernZytgloggeMainMinuteHand = document.querySelector("#bernZytgloggeMainMinuteHand");
const bernZytgloggeAstrolabeZodiac = document.querySelector("#bernZytgloggeAstrolabeZodiac");
const bernZytgloggeSunHand = document.querySelector("#bernZytgloggeSunHand");
const bernZytgloggeSunSymbol = document.querySelector("#bernZytgloggeSunSymbol");
const bernZytgloggeMoonSymbol = document.querySelector("#bernZytgloggeMoonSymbol");
const bernZytgloggeMoonLight = document.querySelector("#bernZytgloggeMoonLight");
const bernZytgloggeCalendarDisk = document.querySelector("#bernZytgloggeCalendarDisk");
const bernZytgloggeCalendarDate = document.querySelector("#bernZytgloggeCalendarDate");
const bernZytgloggeBearParade = document.querySelector("#bernZytgloggeBearParade");
const bernZytgloggeJesterArm = document.querySelector("#bernZytgloggeJesterArm");
const bernZytgloggeRooster = document.querySelector("#bernZytgloggeRooster");
const bernZytgloggeChronosArm = document.querySelector("#bernZytgloggeChronosArm");
const bernZytgloggeChronosHourglass = document.querySelector("#bernZytgloggeChronosHourglass");
const bernZytgloggeChronosMouth = document.querySelector("#bernZytgloggeChronosMouth");
const bernZytgloggeLion = document.querySelector("#bernZytgloggeLion");
const bernZytgloggeJacquemartArm = document.querySelector("#bernZytgloggeJacquemartArm");
const bernZytgloggeBell = document.querySelector("#bernZytgloggeBell");
const bernZytgloggeQuarterBell = document.querySelector("#bernZytgloggeQuarterBell");
const clockSkinSwitch = document.querySelector("#clockSkinSwitch");
const clockSkinCaption = document.querySelector("#clockSkinCaption");
const clockSkinStatus = document.querySelector("#clockSkinStatus");
const corpusHourRing = document.querySelector("#corpusHourRing");
const corpusMinuteRing = document.querySelector("#corpusMinuteRing");
const corpusSecondRing = document.querySelector("#corpusSecondRing");
const corpusEscapeWheel = document.querySelector("#corpusEscapeWheel");
const corpusEscapeTeeth = document.querySelector("#corpusEscapeTeeth");
const corpusContactToothLips = document.querySelector("#corpusContactToothLips");
const corpusContactLipElements = {
  front: document.querySelector("#corpusFrontContactLips"),
  rear: document.querySelector("#corpusRearContactLips"),
};
const corpusRipples = document.querySelector("#corpusRipples");
const corpusClockTime = document.querySelector("#corpusClockTime");
const currentTime = document.querySelector("#currentTime");
const currentDate = document.querySelector("#currentDate");
const dailyQuote = document.querySelector("#dailyQuote");
const dailyQuoteText = document.querySelector("#dailyQuoteText");
const dailyQuoteSource = document.querySelector("#dailyQuoteSource");
const weatherWidget = document.querySelector("#weatherWidget");
const weatherLocation = document.querySelector("#weatherLocation");
const weatherStatus = document.querySelector("#weatherStatus");
const weatherDays = document.querySelector("#weatherDays");
const corpusChronophage = document.querySelector("#chronophage");
const corpusClockQaSecondRaw =
  typeof window === "undefined"
    ? null
    : new URLSearchParams(window.location.search).get("clockSecond");
const corpusClockQaSeconds =
  corpusClockQaSecondRaw === null ? Number.NaN : Number(corpusClockQaSecondRaw);
const headerClockQaDateRaw =
  typeof window === "undefined"
    ? null
    : new URLSearchParams(window.location.search).get("clockDate");
const headerClockQaDateMs = headerClockQaDateRaw === null
  ? Number.NaN
  : Date.parse(headerClockQaDateRaw);
const corpusClockQaReduceMotion =
  typeof window !== "undefined" &&
  new URLSearchParams(window.location.search).get("reduceMotion") === "1";
const corpusPalletElements = {
  front: {
    root: document.querySelector("#chronoFrontPallet"),
    photoCover: document.querySelector("#chronoFrontPhotoCover"),
  },
  rear: {
    root: document.querySelector("#chronoRearPallet"),
    photoCover: document.querySelector("#chronoRearPhotoCover"),
  },
};

function loadCards() {
  try {
    const saved = JSON.parse(businessState.getItem(STORAGE_KEY) || "[]");
    return Array.isArray(saved)
      ? saved
          .filter((card) => card && typeof card.id === "string" && Number.isFinite(card.intervalMs))
          .map((card) => ({
            ...card,
            // Existing cards predate the explicit start state, so keep their timers running.
            started: card.started === false ? false : Number.isFinite(card.nextAt),
            nextAt: Number.isFinite(card.nextAt) ? card.nextAt : null,
            codexThreadId: typeof card.codexThreadId === "string" ? card.codexThreadId : "",
            codexHost: typeof card.codexHost === "string" && /^ssh-[A-Za-z0-9][A-Za-z0-9._-]{0,63}$/.test(card.codexHost)
              ? card.codexHost
              : "local",
            codexThreadName: typeof card.codexThreadName === "string" ? card.codexThreadName : "",
            codexArmed: card.codexArmed === true,
            codexDue: card.codexDue === true,
            codexLastSeenTurnId: typeof card.codexLastSeenTurnId === "string" ? card.codexLastSeenTurnId : null,
            codexLatestTurnId: typeof card.codexLatestTurnId === "string" ? card.codexLatestTurnId : null,
            codexLatestCompletedAt: Number.isFinite(card.codexLatestCompletedAt) ? card.codexLatestCompletedAt : null,
            codexModel: typeof card.codexModel === "string" ? card.codexModel : "",
            codexReasoningEffort: typeof card.codexReasoningEffort === "string" ? card.codexReasoningEffort : "",
            codexPhase: typeof card.codexPhase === "string" ? card.codexPhase : "idle",
            codexPhaseLabel: typeof card.codexPhaseLabel === "string" ? card.codexPhaseLabel : "",
            codexActivityStartedAt: Number.isFinite(card.codexActivityStartedAt) ? card.codexActivityStartedAt : null,
            codexToolKind: typeof card.codexToolKind === "string" ? card.codexToolKind : "",
            codexCwd: typeof card.codexCwd === "string" ? card.codexCwd : "",
            codexStatus: typeof card.codexStatus === "string" ? card.codexStatus : "unknown",
          }))
      : [];
  } catch {
    return [];
  }
}

function saveCards(base) {
  return businessState.setItems({ [STORAGE_KEY]: JSON.stringify(cards), [WORK_SESSION_KEY]: JSON.stringify(workSession) }, base === undefined ? {} : { [STORAGE_KEY]: base });
}

function emptyWorkSession() {
  return {
    active: false,
    startedAt: null,
    endedAt: null,
    countsByCardId: {},
    countedTurnIdsByCardId: {},
  };
}

function loadWorkSession() {
  try {
    const saved = JSON.parse(businessState.getItem(WORK_SESSION_KEY) || "{}");
    if (!saved || typeof saved !== "object") return emptyWorkSession();
    const countsByCardId = {};
    Object.entries(saved.countsByCardId || {}).forEach(([cardId, count]) => {
      if (typeof cardId === "string" && Number.isFinite(count) && count >= 0) {
        countsByCardId[cardId] = count;
      }
    });
    const countedTurnIdsByCardId = {};
    Object.entries(saved.countedTurnIdsByCardId || {}).forEach(([cardId, turnId]) => {
      if (typeof cardId === "string" && (typeof turnId === "string" || turnId === null)) {
        countedTurnIdsByCardId[cardId] = turnId;
      }
    });
    return {
      active: saved.active === true,
      startedAt: Number.isFinite(saved.startedAt) ? saved.startedAt : null,
      endedAt: Number.isFinite(saved.endedAt) ? saved.endedAt : null,
      countsByCardId,
      countedTurnIdsByCardId,
    };
  } catch {
    return emptyWorkSession();
  }
}

function saveWorkSession() {
  return saveCards();
}

function loadWorkHistory(rawValue) {
  try {
    const raw = rawValue === undefined ? businessState.getItem(WORK_HISTORY_KEY) : rawValue;
    return workHistoryCore.normalizeStore(raw);
  } catch {
    return {
      version: WORK_HISTORY_STORE_VERSION,
      updatedAt: 0,
      entries: [],
      unavailable: true,
    };
  }
}

async function persistWorkHistoryEntry(entry, finalSession, finalCards) {
  const latest = loadWorkHistory();
  if (latest.incompatible) {
    workReflectionStatus.textContent = "历史数据来自更新版本，当前页面不能安全写入";
    return false;
  }
  const entries = [...latest.entries.filter((candidate) => candidate.id !== entry.id), entry];
  entries.sort((left, right) => left.startedAt - right.startedAt);
  const payload = {
    version: WORK_HISTORY_STORE_VERSION,
    updatedAt: Date.now(),
    entries,
  };
  try {
    const values = { [WORK_HISTORY_KEY]: JSON.stringify(payload) };
    if (finalSession) values[WORK_SESSION_KEY] = JSON.stringify(finalSession);
    if (finalCards) values[STORAGE_KEY] = JSON.stringify(finalCards);
    if (!await businessState.setItems(values)) return false;
    workHistoryStore = loadWorkHistory();
    return true;
  } catch {
    workReflectionStatus.textContent = "历史记录保存失败，请检查本地数据库服务";
    return false;
  }
}

function escapeHtml(value = "") {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function makeId() {
  return crypto.randomUUID?.() || `card-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function codexThreadRef(hostId, threadId) {
  const id = String(threadId || "").trim();
  const host = String(hostId || "local").trim();
  return id && host !== "local" ? `${host}::${id}` : id;
}

function parseCodexThreadRef(value, fallbackHost = "local") {
  const raw = String(value || "").trim();
  if (raw.includes("::")) {
    const [hostId, ...rest] = raw.split("::");
    if (hostId && rest.join("::")) return { hostId, threadId: rest.join("::"), ref: raw };
  }
  return { hostId: fallbackHost || "local", threadId: raw, ref: raw };
}

function cardCodexThreadRef(card) {
  return codexThreadRef(card?.codexHost, card?.codexThreadId);
}

function conversationCodexThreadRef(conversation) {
  return codexThreadRef(conversation?.hostId, conversation?.threadId);
}

function widgetSourceId() {
  try {
    const existing = localStorage.getItem(WIDGET_SOURCE_KEY);
    if (existing) return existing;
    const created = crypto.randomUUID?.() || `browser-${Date.now()}-${Math.random().toString(16).slice(2)}`;
    localStorage.setItem(WIDGET_SOURCE_KEY, created);
    return created;
  } catch {
    return "browser-session";
  }
}

function intervalText(card) {
  const units = { minute: "分钟", hour: "小时", day: "天" };
  return `${card.intervalValue} ${units[card.intervalUnit] || "分钟"}`;
}

function formatDateTime(timestamp) {
  const date = new Date(timestamp);
  const today = new Date();
  const tomorrow = new Date(today);
  tomorrow.setDate(today.getDate() + 1);
  const time = new Intl.DateTimeFormat("zh-CN", { hour: "2-digit", minute: "2-digit", hour12: false }).format(date);
  if (date.toDateString() === today.toDateString()) return `今天 ${time}`;
  if (date.toDateString() === tomorrow.toDateString()) return `明天 ${time}`;
  return new Intl.DateTimeFormat("zh-CN", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit", hour12: false }).format(date);
}

function formatCountdown(timestamp) {
  const diff = timestamp - Date.now();
  if (diff <= 0) return "现在";
  const seconds = Math.ceil(diff / 1000);
  if (seconds < 60) return `${seconds} 秒后`;
  const minutes = Math.ceil(seconds / 60);
  if (minutes < 60) return `${minutes} 分钟后`;
  const hours = Math.floor(minutes / 60);
  const restMinutes = minutes % 60;
  if (hours < 24) return restMinutes ? `${hours} 小时 ${restMinutes} 分后` : `${hours} 小时后`;
  const days = Math.floor(hours / 24);
  const restHours = hours % 24;
  return restHours ? `${days} 天 ${restHours} 小时后` : `${days} 天后`;
}

function pad2(value) {
  return String(Math.floor(value)).padStart(2, "0");
}

function displayTimeParts(value = new Date()) {
  const date = value instanceof Date ? value : new Date(value);
  if (!Number.isFinite(date.getTime())) throw new TypeError("Invalid display time");
  const parts = Object.fromEntries(
    DISPLAY_TIME_PARTS_FORMATTER
      .formatToParts(date)
      .filter(({ type }) => type !== "literal")
      .map(({ type, value: partValue }) => [type, Number(partValue)]),
  );
  const year = parts.year;
  const month = parts.month - 1;
  const day = parts.day;
  const hour = parts.hour;
  const minute = parts.minute;
  const second = parts.second;
  const millisecond = date.getUTCMilliseconds();
  const dayOfYear = Math.floor(
    (Date.UTC(year, month, day) - Date.UTC(year, 0, 1)) / UNIT_MS.day,
  ) + 1;
  const daysInYear = (Date.UTC(year + 1, 0, 1) - Date.UTC(year, 0, 1)) / UNIT_MS.day;
  return {
    year,
    month,
    day,
    hour,
    minute,
    second,
    millisecond,
    dayOfYear,
    daysInYear,
    decimalHour: hour + minute / 60 + second / 3600 + millisecond / 3600000,
    clockTime: `${pad2(hour)}:${pad2(minute)}:${pad2(second)}`,
  };
}

const wallClockTimeFormatter = new Intl.DateTimeFormat("zh-CN", {
  timeZone: DISPLAY_TIME_ZONE,
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
  hourCycle: "h23",
});

const wallClockDateFormatter = new Intl.DateTimeFormat("zh-CN", {
  timeZone: DISPLAY_TIME_ZONE,
  month: "2-digit",
  day: "2-digit",
  weekday: "short",
});

const wallClockFullFormatter = new Intl.DateTimeFormat("zh-CN", {
  timeZone: DISPLAY_TIME_ZONE,
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  weekday: "long",
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
  hourCycle: "h23",
});

const FALLBACK_QUOTES = [
  { text: "把眼前这一小时做好。", source: "本地" },
  { text: "重要的事，先往前推一小步。", source: "本地" },
  { text: "稳住节奏，答案会在动作里变清楚。", source: "本地" },
  { text: "复杂的工作，也从下一次提交开始。", source: "本地" },
  { text: "今天不求完美，先求可验证。", source: "本地" },
  { text: "注意力放回手边，进度就会回来。", source: "本地" },
  { text: "做完一个闭环，比想十个方向更有用。", source: "本地" },
  { text: "把噪声关小，把结果做实。", source: "本地" },
  { text: "先交付能工作的版本，再打磨漂亮的版本。", source: "本地" },
  { text: "每个清晰的下一步，都会降低一点难度。", source: "本地" },
  { text: "别急着扩大问题，先固定一个变量。", source: "本地" },
  { text: "保持记录，今天的碎片会变成明天的日报。", source: "本地" },
];

function updateWallClock(now = new Date()) {
  if (!currentTime || !currentDate) return;
  currentTime.textContent = wallClockTimeFormatter.format(now);
  currentTime.dateTime = now.toISOString();
  currentDate.textContent = `${wallClockDateFormatter.format(now).replace(/^(\d{2}\/\d{2})(.+)$/, "$1 $2")} · 北京时间`;
  currentTime.setAttribute("aria-label", `北京时间 ${wallClockFullFormatter.format(now)}`);
}

function emptyQuoteCache() {
  return {
    slot: null,
    quote: null,
    history: [],
  };
}

function loadQuoteCache() {
  try {
    const saved = JSON.parse(localStorage.getItem(DAILY_QUOTE_KEY) || "{}");
    if (!saved || typeof saved !== "object") return emptyQuoteCache();
    return {
      slot: Number.isFinite(saved.slot) ? saved.slot : null,
      quote: saved.quote && typeof saved.quote.text === "string" ? saved.quote : null,
      history: Array.isArray(saved.history)
        ? saved.history.filter((item) => typeof item === "string").slice(0, QUOTE_HISTORY_LIMIT)
        : [],
    };
  } catch {
    return emptyQuoteCache();
  }
}

function saveQuoteCache(cache) {
  localStorage.setItem(DAILY_QUOTE_KEY, JSON.stringify({
    slot: cache.slot,
    quote: cache.quote,
    history: cache.history.slice(0, QUOTE_HISTORY_LIMIT),
  }));
}

function quoteSlotFor(timestamp = Date.now()) {
  return Math.floor(timestamp / QUOTE_REFRESH_MS);
}

function quoteKey(quote) {
  return quote.uuid || quote.text;
}

function addQuoteToHistory(history, quote) {
  const key = quoteKey(quote);
  return [key, ...history.filter((item) => item !== key)].slice(0, QUOTE_HISTORY_LIMIT);
}

function fallbackQuote(slot, history = []) {
  const start = positiveModulo(slot, FALLBACK_QUOTES.length);
  for (let offset = 0; offset < FALLBACK_QUOTES.length; offset += 1) {
    const quote = FALLBACK_QUOTES[(start + offset) % FALLBACK_QUOTES.length];
    if (!history.includes(quoteKey(quote))) return quote;
  }
  return FALLBACK_QUOTES[start];
}

function normalizeQuote(payload) {
  const text = String(payload?.hitokoto || "").trim();
  if (!text) return null;
  const sourceParts = [payload.from_who, payload.from]
    .map((part) => String(part || "").trim())
    .filter(Boolean);
  return {
    text,
    source: sourceParts.length ? [...new Set(sourceParts)].join(" · ") : "一言",
    uuid: typeof payload.uuid === "string" ? payload.uuid : "",
    type: typeof payload.type === "string" ? payload.type : "",
    url: typeof payload.uuid === "string" ? `https://hitokoto.cn?uuid=${encodeURIComponent(payload.uuid)}` : "https://hitokoto.cn/",
  };
}

function quoteFitsWorkspace(quote) {
  const joined = `${quote?.text || ""} ${quote?.source || ""}`;
  if (!quote?.text || quote.text.length > 42) return false;
  if (quote.type && quote.type !== "k") return false;
  if (/[\u3040-\u30ff]/.test(joined)) return false;
  if (/歌词|唱片|专辑|网易云|VOCALOID|ボカロ/i.test(joined)) return false;
  return true;
}

async function fetchRemoteQuote() {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), 5200);
  try {
    const response = await fetch(QUOTE_API_URL, {
      cache: "no-store",
      signal: controller.signal,
    });
    if (!response.ok) throw new Error(`quote api ${response.status}`);
    const quote = normalizeQuote(await response.json());
    return quoteFitsWorkspace(quote) ? quote : null;
  } finally {
    window.clearTimeout(timeout);
  }
}

function renderDailyQuote(quote) {
  if (!dailyQuote || !dailyQuoteText || !dailyQuoteSource || !quote) return;
  dailyQuoteText.textContent = quote.text;
  dailyQuoteSource.textContent = quote.source || "一言";
  dailyQuote.href = quote.url || "https://hitokoto.cn/";
  dailyQuote.title = `${quote.text}${quote.source ? ` · ${quote.source}` : ""}`;
}

async function updateDailyQuote() {
  if (!dailyQuote || dailyQuoteSyncing) return;
  const slot = quoteSlotFor();
  if (dailyQuoteSlot === slot) return;
  const cache = loadQuoteCache();
  const cachedQuote = quoteFitsWorkspace(cache.quote) ? cache.quote : null;
  if (cache.slot === slot && cachedQuote) {
    dailyQuoteSlot = slot;
    renderDailyQuote(cachedQuote);
    return;
  }

  dailyQuoteSyncing = true;
  try {
    const remoteQuote = await fetchRemoteQuote();
    const quote = remoteQuote && !cache.history.includes(quoteKey(remoteQuote))
      ? remoteQuote
      : fallbackQuote(slot, cache.history);
    const nextCache = {
      slot,
      quote,
      history: addQuoteToHistory(cache.history, quote),
    };
    saveQuoteCache(nextCache);
    dailyQuoteSlot = slot;
    renderDailyQuote(quote);
  } catch {
    const quote = cachedQuote || fallbackQuote(slot, cache.history);
    const nextCache = {
      slot,
      quote,
      history: addQuoteToHistory(cache.history, quote),
    };
    saveQuoteCache(nextCache);
    dailyQuoteSlot = slot;
    renderDailyQuote(quote);
  } finally {
    dailyQuoteSyncing = false;
  }
}

function weatherCodeText(code) {
  if (code === 0) return "晴";
  if (code === 1) return "少云";
  if (code === 2) return "多云";
  if (code === 3) return "阴";
  if (code === 45 || code === 48) return "雾";
  if (code >= 51 && code <= 57) return "毛毛雨";
  if (code >= 61 && code <= 67) return "雨";
  if (code >= 71 && code <= 77) return "雪";
  if (code >= 80 && code <= 82) return "阵雨";
  if (code === 85 || code === 86) return "阵雪";
  if (code >= 95) return "雷雨";
  return "天气";
}

function loadWeatherCache() {
  try {
    const saved = JSON.parse(localStorage.getItem(WEATHER_CACHE_KEY) || "{}");
    if (!saved || typeof saved !== "object") return null;
    if (!Number.isFinite(saved.fetchedAt) || !Array.isArray(saved.days)) return null;
    return saved;
  } catch {
    return null;
  }
}

function saveWeatherCache(cache) {
  localStorage.setItem(WEATHER_CACHE_KEY, JSON.stringify(cache));
}

function geolocationPosition(timeout = 5200) {
  return new Promise((resolve, reject) => {
    if (!navigator.geolocation) {
      reject(new Error("geolocation unavailable"));
      return;
    }
    navigator.geolocation.getCurrentPosition(resolve, reject, {
      enableHighAccuracy: false,
      maximumAge: 60 * 60 * 1000,
      timeout,
    });
  });
}

async function resolveWeatherLocation() {
  try {
    if (!navigator.permissions || !navigator.geolocation) return WEATHER_DEFAULT_LOCATION;
    const permission = await navigator.permissions.query({ name: "geolocation" });
    if (permission.state !== "granted") return WEATHER_DEFAULT_LOCATION;
    const position = await geolocationPosition();
    return {
      label: "当前位置",
      latitude: position.coords.latitude,
      longitude: position.coords.longitude,
    };
  } catch {
    return WEATHER_DEFAULT_LOCATION;
  }
}

function weatherApiUrl(location) {
  const params = new URLSearchParams({
    latitude: location.latitude.toFixed(4),
    longitude: location.longitude.toFixed(4),
    timezone: "auto",
    forecast_days: "7",
    current: "temperature_2m,weather_code",
    daily: "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
    hourly: "temperature_2m,weather_code,precipitation_probability,wind_speed_10m",
  });
  return `https://api.open-meteo.com/v1/forecast?${params.toString()}`;
}

async function fetchWeatherForecast(location) {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), 7000);
  try {
    const response = await fetch(weatherApiUrl(location), {
      cache: "no-store",
      signal: controller.signal,
    });
    if (!response.ok) throw new Error(`weather api ${response.status}`);
    return normalizeWeatherForecast(await response.json(), location);
  } finally {
    window.clearTimeout(timeout);
  }
}

function normalizeWeatherForecast(payload, location) {
  const hourly = payload?.hourly || {};
  const hourlyItems = (hourly.time || []).map((time, index) => ({
    time,
    date: String(time).slice(0, 10),
    hour: String(time).slice(11, 16),
    temp: Number(hourly.temperature_2m?.[index]),
    code: Number(hourly.weather_code?.[index]),
    rain: Number(hourly.precipitation_probability?.[index]),
    wind: Number(hourly.wind_speed_10m?.[index]),
  })).filter((item) => item.time && Number.isFinite(item.temp));

  const days = (payload?.daily?.time || []).slice(0, 7).map((date, index) => ({
    date,
    code: Number(payload.daily.weather_code?.[index]),
    max: Number(payload.daily.temperature_2m_max?.[index]),
    min: Number(payload.daily.temperature_2m_min?.[index]),
    rain: Number(payload.daily.precipitation_probability_max?.[index]),
    hours: hourlyItems.filter((item) => item.date === date),
  })).filter((day) => day.date && Number.isFinite(day.max) && Number.isFinite(day.min));

  if (!days.length) throw new Error("empty weather forecast");
  return {
    fetchedAt: Date.now(),
    location,
    current: payload.current || null,
    timezone: payload.timezone || "",
    days,
  };
}

function weatherDayName(dateString, index) {
  if (index === 0) return "今天";
  if (index === 1) return "明天";
  return new Intl.DateTimeFormat("zh-CN", { weekday: "short" }).format(new Date(`${dateString}T12:00:00`));
}

function weatherDateLabel(dateString) {
  return new Intl.DateTimeFormat("zh-CN", { month: "2-digit", day: "2-digit" }).format(new Date(`${dateString}T12:00:00`));
}

function formatTemp(value) {
  return Number.isFinite(value) ? `${Math.round(value)}°` : "--";
}

function formatRain(value) {
  return Number.isFinite(value) ? `${Math.round(value)}%` : "--";
}

function weatherChartSvg(hours) {
  const chartHours = hours.filter((item) => Number.isFinite(item.temp));
  if (!chartHours.length) return "";
  const width = 300;
  const height = 98;
  const padX = 12;
  const padTop = 9;
  const padBottom = 21;
  const plotWidth = width - padX * 2;
  const plotHeight = height - padTop - padBottom;
  const temps = chartHours.map((item) => item.temp);
  const minTemp = Math.floor(Math.min(...temps) - 1);
  const maxTemp = Math.ceil(Math.max(...temps) + 1);
  const tempRange = Math.max(1, maxTemp - minTemp);
  const xFor = (index) => padX + (chartHours.length === 1 ? 0 : (plotWidth * index) / (chartHours.length - 1));
  const yForTemp = (temp) => padTop + plotHeight - ((temp - minTemp) / tempRange) * plotHeight;
  const points = chartHours.map((item, index) => `${xFor(index).toFixed(1)},${yForTemp(item.temp).toFixed(1)}`).join(" ");
  const rainBars = chartHours.map((item, index) => {
    const rain = clamp(Number.isFinite(item.rain) ? item.rain / 100 : 0);
    const barHeight = rain * 30;
    const x = xFor(index) - 2.2;
    const y = height - padBottom - barHeight;
    return `<rect class="weather-chart-rain" x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="4.4" height="${barHeight.toFixed(1)}" rx="2" />`;
  }).join("");
  const dots = chartHours
    .filter((_, index) => index % 6 === 0 || index === chartHours.length - 1)
    .map((item, index, filtered) => {
      const originalIndex = index === filtered.length - 1 ? chartHours.length - 1 : chartHours.indexOf(item);
      return `<circle class="weather-chart-dot" cx="${xFor(originalIndex).toFixed(1)}" cy="${yForTemp(item.temp).toFixed(1)}" r="2.6" />`;
    })
    .join("");

  return `
    <svg class="weather-chart" viewBox="0 0 ${width} ${height}" role="img" aria-label="小时温度和降雨概率图">
      <line class="weather-chart-grid" x1="${padX}" y1="${padTop}" x2="${width - padX}" y2="${padTop}" />
      <line class="weather-chart-grid" x1="${padX}" y1="${height - padBottom}" x2="${width - padX}" y2="${height - padBottom}" />
      ${rainBars}
      <polyline class="weather-chart-line" points="${points}" />
      ${dots}
    </svg>
  `;
}

function weatherHourTicks(hours) {
  const tickHours = [0, 6, 12, 18]
    .map((hour) => hours.find((item) => item.hour === `${String(hour).padStart(2, "0")}:00`))
    .filter(Boolean);
  if (!tickHours.length) return "";
  return `
    <div class="weather-hour-ticks">
      ${tickHours.map((item) => `
        <span>${escapeHtml(item.hour.slice(0, 2))}时 ${formatTemp(item.temp)} ${escapeHtml(weatherCodeText(item.code))}</span>
      `).join("")}
    </div>
  `;
}

function weatherDayMarkup(day, index) {
  const type = weatherCodeText(day.code);
  const dayName = weatherDayName(day.date, index);
  const dateLabel = weatherDateLabel(day.date);
  return `
    <div class="weather-day" role="button" tabindex="0" aria-label="${escapeHtml(`${dayName} ${type} ${formatTemp(day.min)}到${formatTemp(day.max)} 降雨${formatRain(day.rain)}`)}">
      <span class="weather-day-name">${escapeHtml(dayName)}</span>
      <span class="weather-day-temp">${formatTemp(day.min)}-${formatTemp(day.max)}</span>
      <span class="weather-day-type">${escapeHtml(type)}</span>
      <span class="weather-day-rain">雨 ${formatRain(day.rain)}</span>
      <div class="weather-detail" role="tooltip">
        <div class="weather-detail-head">
          <span>${escapeHtml(dayName)} · ${escapeHtml(dateLabel)}</span>
          <small>${escapeHtml(type)} · 降雨 ${formatRain(day.rain)}</small>
        </div>
        ${weatherChartSvg(day.hours)}
        ${weatherHourTicks(day.hours)}
      </div>
    </div>
  `;
}

function renderWeatherForecast(forecast, statusText = "") {
  if (!weatherWidget || !weatherDays || !weatherLocation || !weatherStatus || !forecast) return;
  weatherLocation.textContent = `${forecast.location?.label || "天气"} · 未来 7 天`;
  weatherStatus.textContent = statusText ||
    `更新 ${new Intl.DateTimeFormat("zh-CN", { hour: "2-digit", minute: "2-digit", hour12: false }).format(new Date(forecast.fetchedAt))}`;
  weatherDays.innerHTML = forecast.days.map(weatherDayMarkup).join("");
  weatherWidget.dataset.weatherState = "ready";
}

async function updateWeatherForecast(force = false) {
  if (!weatherWidget || weatherSyncing) return;
  const cache = loadWeatherCache();
  if (!force && cache && Date.now() - cache.fetchedAt < WEATHER_REFRESH_MS) {
    renderWeatherForecast(cache);
    return;
  }

  if (cache) renderWeatherForecast(cache, "正在更新");
  weatherSyncing = true;
  try {
    const location = await resolveWeatherLocation();
    const forecast = await fetchWeatherForecast(location);
    saveWeatherCache(forecast);
    renderWeatherForecast(forecast);
  } catch {
    if (cache) {
      renderWeatherForecast(cache, "离线缓存");
    } else if (weatherStatus) {
      weatherStatus.textContent = "天气暂不可用";
      weatherWidget.dataset.weatherState = "error";
    }
  } finally {
    weatherSyncing = false;
  }
}

function clamp(value, minimum = 0, maximum = 1) {
  return Math.min(maximum, Math.max(minimum, value));
}

function smoothstep(value) {
  const x = clamp(value);
  return x * x * (3 - 2 * x);
}

function smootherstep(value) {
  const x = clamp(value);
  return x * x * x * (x * (x * 6 - 15) + 10);
}

function positiveModulo(value, divisor) {
  return ((value % divisor) + divisor) % divisor;
}

function seededFraction(seed) {
  const value = Math.sin(seed * 12.9898 + 78.233) * 43758.5453;
  return value - Math.floor(value);
}

function localDayKey(date = new Date()) {
  const display = displayTimeParts(date);
  return [
    display.year,
    String(display.month + 1).padStart(2, "0"),
    String(display.day).padStart(2, "0"),
  ].join("-");
}

function hashClockDay(dayKey) {
  let hash = 2166136261;
  for (const character of dayKey) {
    hash ^= character.charCodeAt(0);
    hash = Math.imul(hash, 16777619);
  }
  return hash >>> 0;
}

function loadHeaderClockState() {
  try {
    const saved = JSON.parse(localStorage.getItem(HEADER_CLOCK_KEY) || "{}");
    return saved && typeof saved === "object" ? saved : {};
  } catch {
    return {};
  }
}

function saveHeaderClockState(state) {
  try {
    localStorage.setItem(HEADER_CLOCK_KEY, JSON.stringify(state));
  } catch {
    // The clock still works when local storage is unavailable; only daily persistence is lost.
  }
}

function headerClockDefinition(clockId) {
  return HEADER_CLOCKS.find((clock) => clock.id === clockId) || HEADER_CLOCKS[0];
}

function chooseDailyHeaderClock(dayKey, previousClockId = null) {
  const candidates = HEADER_CLOCKS.length > 1
    ? HEADER_CLOCKS.filter((clock) => clock.id !== previousClockId)
    : HEADER_CLOCKS;
  return candidates[hashClockDay(dayKey) % candidates.length].id;
}

function refreshHeaderClockTitle() {
  if (!corpusClock || !activeHeaderClockId) return;
  const definition = headerClockDefinition(activeHeaderClockId);
  const label = document.getElementById(definition.timeId)?.textContent;
  const suffix = label ? ` · ${label}` : "";
  const titleNote = definition.titleNote ? ` · ${definition.titleNote}` : "";
  corpusClock.setAttribute("aria-label", `每日名钟：${definition.label}${suffix}${titleNote}`);
  corpusClock.setAttribute("title", `${definition.label} 动态模拟${suffix}${titleNote} · 右上角可切换`);
  if (clockSkinSwitch) {
    clockSkinSwitch.setAttribute("aria-label", `切换名钟，当前为${definition.shortLabel}`);
    clockSkinSwitch.title = `当前：${definition.label}；点击切换`;
  }
}

function syncActiveBigBenClock(date = corpusClockRenderDate()) {
  if (!bigBenClock || activeHeaderClockId !== "big-ben") return;
  const syncToken = ++bigBenSyncToken;
  bigBenClock.classList.add("is-hand-syncing");
  bigBenLastBeat = null;
  bigBenMinuteAngle = null;
  bigBenHourAngle = null;
  bigBenLastLabel = null;
  updateBigBenClock(date, true);
  requestAnimationFrame(() => requestAnimationFrame(() => {
    if (syncToken === bigBenSyncToken) bigBenClock.classList.remove("is-hand-syncing");
  }));
}

function syncActivePragueOrlojClock(date = corpusClockRenderDate()) {
  if (!pragueOrlojClock || activeHeaderClockId !== "prague-orloj") return;
  const syncToken = ++pragueOrlojSyncToken;
  pragueOrlojClock.classList.add("is-celestial-syncing");
  pragueOrlojLastMinute = null;
  pragueOrlojLastLabel = null;
  pragueOrlojSunAngle = null;
  pragueOrlojZodiacAngle = null;
  pragueOrlojMoonAngle = null;
  pragueOrlojOldCzechAngle = null;
  pragueOrlojCalendarAngle = null;
  updatePragueOrlojClock(date, true);
  requestAnimationFrame(() => requestAnimationFrame(() => {
    if (syncToken === pragueOrlojSyncToken) {
      pragueOrlojClock.classList.remove("is-celestial-syncing");
    }
  }));
}

function syncActiveBernZytgloggeClock(date = corpusClockRenderDate()) {
  if (!bernZytgloggeClock || activeHeaderClockId !== "bern-zytglogge") return;
  const syncToken = ++bernZytgloggeSyncToken;
  bernZytgloggeClock.classList.add("is-mechanism-syncing");
  bernZytgloggeLastBeat = null;
  bernZytgloggeLastLabel = null;
  bernZytgloggeLastDayKey = null;
  bernZytgloggeMainHourAngle = null;
  bernZytgloggeMainMinuteAngle = null;
  bernZytgloggeSunAngle = null;
  bernZytgloggeZodiacAngle = null;
  bernZytgloggeMoonAngle = null;
  bernZytgloggeCalendarAngle = null;
  updateBernZytgloggeClock(date, true);
  requestAnimationFrame(() => requestAnimationFrame(() => {
    if (syncToken === bernZytgloggeSyncToken) {
      bernZytgloggeClock.classList.remove("is-mechanism-syncing");
    }
  }));
}

function revealHeaderClockAfterHydration() {
  if (!corpusClock || corpusClock.dataset.clockReady === "true") return;
  requestAnimationFrame(() => requestAnimationFrame(() => {
    corpusClock.dataset.clockReady = "true";
  }));
}

function applyHeaderClock(clockId, { announce = false } = {}) {
  const definition = headerClockDefinition(clockId);
  const switchingClock = activeHeaderClockId !== definition.id;
  activeHeaderClockId = definition.id;
  corpusClock?.setAttribute("data-clock-skin", definition.id);
  if (corpusClock) corpusClock.dataset.reducedMotion = String(shouldReduceMotion());
  HEADER_CLOCKS.forEach((clock) => {
    const skin = document.getElementById(clock.skinId);
    const active = clock.id === definition.id;
    skin?.classList.toggle("is-active", active);
    skin?.setAttribute("aria-hidden", String(!active));
  });
  HEADER_CLOCK_RUNTIMES[definition.id]?.activate({
    date: corpusClockRenderDate(),
    now: performance.now(),
    switching: switchingClock,
  });
  if (clockSkinCaption) {
    clockSkinCaption.textContent = `${definition.shortLabel} · ${definition.meaning}`;
  }
  refreshHeaderClockTitle();
  if (announce && clockSkinStatus) {
    clockSkinStatus.textContent = `已切换到${definition.label}`;
  }
}

function ensureDailyHeaderClock(force = false) {
  if (!corpusClock) return;
  const now = new Date();
  const dayKey = localDayKey(now);
  const queryClock = new URLSearchParams(window.location.search).get("clock");
  const queryDefinition = HEADER_CLOCKS.find((clock) => clock.id === queryClock);
  if (queryDefinition) {
    if (clockSkinSwitch) clockSkinSwitch.hidden = true;
    if (
      !force &&
      headerClockDayKey === dayKey &&
      activeHeaderClockId === queryDefinition.id &&
      corpusClock.dataset.clockMode === "qa-override"
    ) return;
    headerClockDayKey = dayKey;
    corpusClock.dataset.clockMode = "qa-override";
    corpusClock.dataset.clockDay = dayKey;
    applyHeaderClock(queryDefinition.id);
    return;
  }
  if (clockSkinSwitch) clockSkinSwitch.hidden = false;
  if (!force && headerClockDayKey === dayKey && activeHeaderClockId) return;

  const saved = loadHeaderClockState();
  let clockId = saved.dayKey === dayKey &&
    HEADER_CLOCKS.some((clock) => clock.id === saved.clockId)
    ? saved.clockId
    : null;
  if (!clockId) {
    const previousClockId = HEADER_CLOCKS.some((clock) => clock.id === saved.clockId)
      ? saved.clockId
      : saved.previousClockId;
    clockId = chooseDailyHeaderClock(dayKey, previousClockId);
    saveHeaderClockState({
      dayKey,
      clockId,
      previousClockId: previousClockId || null,
      selectedAt: Date.now(),
    });
  }
  headerClockDayKey = dayKey;
  corpusClock.dataset.clockMode = "daily";
  corpusClock.dataset.clockDay = dayKey;
  applyHeaderClock(clockId);
}

function cycleHeaderClock() {
  const queryClock = new URLSearchParams(window.location.search).get("clock");
  if (HEADER_CLOCKS.some((clock) => clock.id === queryClock)) return;
  const currentIndex = Math.max(
    0,
    HEADER_CLOCKS.findIndex((clock) => clock.id === activeHeaderClockId),
  );
  const nextClock = HEADER_CLOCKS[(currentIndex + 1) % HEADER_CLOCKS.length];
  const dayKey = localDayKey();
  headerClockDayKey = dayKey;
  saveHeaderClockState({
    dayKey,
    clockId: nextClock.id,
    previousClockId: activeHeaderClockId,
    selectedAt: Date.now(),
    manual: true,
  });
  corpusClock.dataset.clockMode = "manual-today";
  applyHeaderClock(nextClock.id, { announce: true });
}

function bigBenPolar(radius, angle) {
  return {
    x: BIG_BEN_CENTER.x + Math.cos(angle) * radius,
    y: BIG_BEN_CENTER.y + Math.sin(angle) * radius,
  };
}

function bigBenSegmentPath(x1, y1, x2, y2, width) {
  const length = Math.max(0.001, Math.hypot(x2 - x1, y2 - y1));
  const normalX = (-(y2 - y1) / length) * (width / 2);
  const normalY = ((x2 - x1) / length) * (width / 2);
  return [
    `M${(x1 + normalX).toFixed(2)} ${(y1 + normalY).toFixed(2)}`,
    `L${(x2 + normalX).toFixed(2)} ${(y2 + normalY).toFixed(2)}`,
    `L${(x2 - normalX).toFixed(2)} ${(y2 - normalY).toFixed(2)}`,
    `L${(x1 - normalX).toFixed(2)} ${(y1 - normalY).toFixed(2)}Z`,
  ].join("");
}

function bigBenGlyphPath(character, centerX) {
  if (character === "I") {
    return [
      bigBenSegmentPath(centerX, -29, centerX, 29, 8.5),
      bigBenSegmentPath(centerX - 10, -29, centerX + 10, -29, 6),
      bigBenSegmentPath(centerX - 10, 29, centerX + 10, 29, 6),
    ].join("");
  }
  if (character === "V") {
    return [
      bigBenSegmentPath(centerX - 13, -28, centerX, 29, 8.5),
      bigBenSegmentPath(centerX + 13, -28, centerX, 29, 8.5),
      bigBenSegmentPath(centerX - 18, -29, centerX - 7, -29, 6),
      bigBenSegmentPath(centerX + 7, -29, centerX + 18, -29, 6),
    ].join("");
  }
  // Pugin's dial replaces the conventional crossed Roman X with a distinctive
  // F-shaped character. Keep its single upper arm and shorter middle arm clear
  // after the complete dial is reduced to 70–110 px.
  return [
    bigBenSegmentPath(centerX - 6, -29, centerX - 6, 29, 8.5),
    bigBenSegmentPath(centerX - 10, -29, centerX + 16, -29, 7),
    bigBenSegmentPath(centerX - 8, -4, centerX + 11, -4, 7),
    bigBenSegmentPath(centerX - 15, 29, centerX + 3, 29, 6),
  ].join("");
}

function createBigBenRomanNumeral(text, index) {
  const widths = { I: 20, V: 34, X: 36 };
  const gap = 3;
  const totalWidth = [...text].reduce(
    (total, character) => total + widths[character],
    Math.max(0, text.length - 1) * gap,
  );
  let cursor = -totalWidth / 2;
  const pathData = [];
  [...text].forEach((character) => {
    const width = widths[character];
    pathData.push(bigBenGlyphPath(character, cursor + width / 2));
    cursor += width + gap;
  });
  const angleDegrees = index * 30;
  const angle = (angleDegrees * Math.PI) / 180 - Math.PI / 2;
  const position = bigBenPolar(253, angle);
  const group = document.createElementNS(CORPUS_CLOCK_NS, "g");
  group.setAttribute(
    "transform",
    `translate(${position.x.toFixed(2)} ${position.y.toFixed(2)}) rotate(${angleDegrees})`,
  );
  group.dataset.index = String(index);
  group.dataset.numeral = text;
  const path = document.createElementNS(CORPUS_CLOCK_NS, "path");
  path.setAttribute("d", pathData.join(""));
  group.append(path);
  return group;
}

function populateBigBenClockDecoration() {
  if (bigBenMinuteTicks && !bigBenMinuteTicks.childElementCount) {
    const ticks = document.createDocumentFragment();
    for (let index = 0; index < 60; index += 1) {
      const angle = (index / 60) * Math.PI * 2 - Math.PI / 2;
      const inner = bigBenPolar(index % 5 === 0 ? 289 : 296, angle);
      const outer = bigBenPolar(311, angle);
      const line = document.createElementNS(CORPUS_CLOCK_NS, "line");
      line.setAttribute("x1", inner.x.toFixed(2));
      line.setAttribute("y1", inner.y.toFixed(2));
      line.setAttribute("x2", outer.x.toFixed(2));
      line.setAttribute("y2", outer.y.toFixed(2));
      line.dataset.index = String(index);
      if (index % 5 === 0) line.classList.add("is-major");
      ticks.append(line);
    }
    bigBenMinuteTicks.append(ticks);
  }

  if (bigBenRomanNumerals && !bigBenRomanNumerals.childElementCount) {
    const numerals = document.createDocumentFragment();
    BIG_BEN_ROMAN_NUMERALS.forEach((numeral, index) => {
      numerals.append(createBigBenRomanNumeral(numeral, index));
    });
    bigBenRomanNumerals.append(numerals);
  }

  if (bigBenOpalLattice && !bigBenOpalLattice.childElementCount) {
    const lattice = document.createDocumentFragment();
    for (let index = 0; index < 24; index += 1) {
      const angle = (index / 24) * Math.PI * 2 - Math.PI / 2;
      const inner = bigBenPolar(45, angle);
      const outer = bigBenPolar(220, angle);
      const line = document.createElementNS(CORPUS_CLOCK_NS, "line");
      line.setAttribute("x1", inner.x.toFixed(2));
      line.setAttribute("y1", inner.y.toFixed(2));
      line.setAttribute("x2", outer.x.toFixed(2));
      line.setAttribute("y2", outer.y.toFixed(2));
      lattice.append(line);
    }
    [120, 198].forEach((radius) => {
      const circle = document.createElementNS(CORPUS_CLOCK_NS, "circle");
      circle.setAttribute("cx", String(BIG_BEN_CENTER.x));
      circle.setAttribute("cy", String(BIG_BEN_CENTER.y));
      circle.setAttribute("r", String(radius));
      lattice.append(circle);
    });
    bigBenOpalLattice.append(lattice);
  }
}

function unwrapClockAngle(previousAngle, nextNormalizedAngle) {
  if (!Number.isFinite(previousAngle)) return nextNormalizedAngle;
  const previousNormalized = positiveModulo(previousAngle, 360);
  const delta = positiveModulo(nextNormalizedAngle - previousNormalized + 180, 360) - 180;
  return previousAngle + delta;
}

function bigBenPulseStrength(elapsed, start, duration, intensity = 1) {
  const progress = elapsed - start;
  if (progress < 0 || progress >= duration) return 0;
  const attack = Math.min(1, progress / 0.045);
  const decay = 1 - progress / duration;
  return attack * decay * intensity;
}

function bigBenChimeState(date, displayTime = displayTimeParts(date)) {
  const minute = displayTime.minute;
  const elapsed = displayTime.second + displayTime.millisecond / 1000;
  const phraseSpacing = 2.32;
  const noteOffsets = [0, 0.47, 0.94, 1.41];
  const noteDurations = [0.19, 0.19, 0.19, 0.54];
  let strength = 0;

  const quarterStrength = (quarterElapsed, phraseCount) => {
    let result = 0;
    for (let phrase = 0; phrase < phraseCount; phrase += 1) {
      noteOffsets.forEach((offset, note) => {
        result = Math.max(
          result,
          bigBenPulseStrength(
            quarterElapsed,
            phrase * phraseSpacing + offset,
            noteDurations[note],
            1 - phrase * 0.035,
          ),
        );
      });
    }
    return result;
  };

  if (minute === 59) {
    // The four Westminster quarter phrases precede the hour. Their final long
    // note clears just before :00 so Big Ben's first hour strike marks :00:00.
    strength = quarterStrength(elapsed - 50.64, 4);
    if (strength > 0) return { strength, phase: "westminster-hour-lead" };
  } else if (minute > 0 && minute % 15 === 0) {
    strength = quarterStrength(elapsed, minute / 15);
    if (strength > 0) return { strength, phase: "westminster-quarter" };
  }

  // The silent visual twin preserves the Great Bell's normal 4.5-second
  // striking rate, with the first strike exactly on the hour.
  if (minute === 0) {
    const strikeCount = displayTime.hour % 12 || 12;
    for (let strike = 0; strike < strikeCount; strike += 1) {
      strength = Math.max(
        strength,
        bigBenPulseStrength(elapsed, strike * 4.5, 0.7, 0.86),
      );
    }
    if (strength > 0) return { strength, phase: "great-bell-hour" };
  }
  return { strength: 0, phase: "silent" };
}

function bigBenClockState(date = new Date()) {
  const beatTime = Math.floor(date.getTime() / BIG_BEN_HAND_TICK_MS) * BIG_BEN_HAND_TICK_MS;
  const beatDate = new Date(beatTime);
  const beatDisplayTime = displayTimeParts(beatDate);
  const displayTime = displayTimeParts(date);
  const seconds = beatDisplayTime.second + beatDisplayTime.millisecond / 1000;
  const minuteAngle = positiveModulo(
    (beatDisplayTime.minute + seconds / 60) * 6,
    360,
  );
  const hourAngle = positiveModulo(
    ((beatDisplayTime.hour % 12) + beatDisplayTime.minute / 60 + seconds / 3600) * 30,
    360,
  );
  const beatProgress = positiveModulo(date.getTime(), BIG_BEN_HAND_TICK_MS) /
    BIG_BEN_HAND_TICK_MS;
  const chime = bigBenChimeState(date, displayTime);
  return {
    timeZone: DISPLAY_TIME_ZONE,
    displayHour24: displayTime.hour,
    displayMinute: displayTime.minute,
    displaySecond: displayTime.second,
    beat: Math.floor(beatTime / BIG_BEN_HAND_TICK_MS),
    beatProgress,
    beatPulse: Math.exp(-beatProgress * 8.4),
    minuteAngle,
    hourAngle,
    chimeStrength: chime.strength,
    chimePhase: chime.phase,
    night: displayTime.hour < 7 || displayTime.hour >= 18,
    clockTime: displayTime.clockTime,
    label: `${displayTime.clockTime} 北京时间`,
  };
}

function updateBigBenClock(date = new Date(), force = false) {
  if (!bigBenClock || !corpusClock) return;
  const state = bigBenClockState(date);
  const reduceMotion = shouldReduceMotion();
  const beatPulse = reduceMotion ? 0 : state.beatPulse;
  const chimeStrength = reduceMotion ? 0 : state.chimeStrength;
  corpusClock.dataset.reducedMotion = String(reduceMotion);
  if (force || state.beat !== bigBenLastBeat) {
    bigBenMinuteAngle = unwrapClockAngle(bigBenMinuteAngle, state.minuteAngle);
    bigBenHourAngle = unwrapClockAngle(bigBenHourAngle, state.hourAngle);
    corpusClock.style.setProperty("--bb-minute-angle", `${bigBenMinuteAngle.toFixed(6)}deg`);
    corpusClock.style.setProperty("--bb-hour-angle", `${bigBenHourAngle.toFixed(6)}deg`);
    bigBenMinuteHand?.setAttribute("data-angle", state.minuteAngle.toFixed(6));
    bigBenHourHand?.setAttribute("data-angle", state.hourAngle.toFixed(6));
    bigBenLastBeat = state.beat;
  }
  corpusClock.style.setProperty("--bb-beat-pulse", beatPulse.toFixed(4));
  corpusClock.style.setProperty("--bb-chime-strength", chimeStrength.toFixed(4));
  if (force || state.night !== bigBenLastNight) {
    bigBenClock.classList.toggle("is-night", state.night);
    bigBenClock.dataset.period = state.night ? "night" : "day";
    bigBenLastNight = state.night;
  }
  const isChiming = chimeStrength > 0.01;
  if (force || isChiming !== bigBenLastChiming) {
    bigBenClock.classList.toggle("is-chiming", isChiming);
    bigBenLastChiming = isChiming;
  }
  if (force || state.beat !== Number(bigBenClock.dataset.beat)) {
    bigBenClock.dataset.beat = String(state.beat);
    bigBenClock.dataset.tickMs = String(BIG_BEN_HAND_TICK_MS);
  }
  bigBenClock.dataset.chimeStrength = chimeStrength.toFixed(4);
  bigBenClock.dataset.chimePhase = reduceMotion ? "reduced-motion" : state.chimePhase;
  bigBenClock.dataset.timeZone = state.timeZone;
  bigBenClock.dataset.displayTime = state.clockTime;
  if (bigBenClockTime && (force || state.label !== bigBenLastLabel)) {
    bigBenClockTime.textContent = state.label;
    bigBenClockTime.dateTime = state.clockTime;
    bigBenLastLabel = state.label;
    if (activeHeaderClockId === "big-ben") refreshHeaderClockTitle();
  }
}

function initializeBigBenClock() {
  populateBigBenClockDecoration();
  updateBigBenClock(corpusClockRenderDate(), true);
}

function bigBenClockSnapshot(value = new Date()) {
  const date = value instanceof Date ? new Date(value.getTime()) : new Date(value);
  if (!Number.isFinite(date.getTime())) throw new TypeError("Invalid Big Ben snapshot date");
  return Object.freeze({ ...bigBenClockState(date) });
}

if (typeof window !== "undefined") {
  Object.defineProperty(window, "__bigBenClockSnapshot", {
    value: bigBenClockSnapshot,
    configurable: false,
    writable: false,
  });
}

function degreesToRadians(value) {
  return (value * Math.PI) / 180;
}

function radiansToDegrees(value) {
  return (value * 180) / Math.PI;
}

function pragueOrlojPolar(radius, clockwiseDegrees, center = PRAGUE_ORLOJ_CENTER) {
  const angle = degreesToRadians(clockwiseDegrees);
  return {
    x: center.x + Math.sin(angle) * radius,
    y: center.y - Math.cos(angle) * radius,
  };
}

function pragueOrlojJulianDate(date) {
  return date.getTime() / UNIT_MS.day + 2440587.5;
}

function pragueOrlojCETParts(date) {
  const fixedCET = new Date(date.getTime() + UNIT_MS.hour);
  const year = fixedCET.getUTCFullYear();
  const month = fixedCET.getUTCMonth();
  const day = fixedCET.getUTCDate();
  const hour = fixedCET.getUTCHours();
  const minute = fixedCET.getUTCMinutes();
  const second = fixedCET.getUTCSeconds();
  const millisecond = fixedCET.getUTCMilliseconds();
  const dayOfYear = Math.floor(
    (Date.UTC(year, month, day) - Date.UTC(year, 0, 1)) / UNIT_MS.day,
  ) + 1;
  const daysInYear = (Date.UTC(year + 1, 0, 1) - Date.UTC(year, 0, 1)) / UNIT_MS.day;
  return {
    year,
    month,
    day,
    hour,
    minute,
    second,
    millisecond,
    dayOfYear,
    daysInYear,
    decimalHour: hour + minute / 60 + second / 3600 + millisecond / 3600000,
  };
}

function pragueOrlojSolarState(julianDate) {
  const days = julianDate - 2451545;
  const meanAnomaly = positiveModulo(357.529 + 0.98560028 * days, 360);
  const meanLongitude = positiveModulo(280.459 + 0.98564736 * days, 360);
  const longitude = positiveModulo(
    meanLongitude +
      1.915 * Math.sin(degreesToRadians(meanAnomaly)) +
      0.02 * Math.sin(degreesToRadians(2 * meanAnomaly)),
    360,
  );
  const obliquity = 23.439 - 0.00000036 * days;
  const declination = radiansToDegrees(Math.asin(
    Math.sin(degreesToRadians(obliquity)) * Math.sin(degreesToRadians(longitude)),
  ));
  return { longitude, obliquity, declination };
}

function pragueOrlojLocalSiderealHours(julianDate) {
  const julianMidnight = Math.floor(julianDate - 0.5) + 0.5;
  const hours = (julianDate - julianMidnight) * 24;
  const daysAtMidnight = julianMidnight - 2451545;
  const centuries = (julianDate - 2451545) / 36525;
  const gmst =
    6.697375 +
    0.065709824279 * daysAtMidnight +
    1.0027379 * hours +
    0.0000258 * centuries * centuries;
  return positiveModulo(gmst + PRAGUE_ORLOJ_LONGITUDE / 15, 24);
}

function pragueOrlojSunTimes(cet, declination) {
  const gamma =
    (2 * Math.PI / cet.daysInYear) *
    (cet.dayOfYear - 1 + (cet.decimalHour - 12) / 24);
  const equationOfTime = 229.18 * (
    0.000075 +
    0.001868 * Math.cos(gamma) -
    0.032077 * Math.sin(gamma) -
    0.014615 * Math.cos(2 * gamma) -
    0.040849 * Math.sin(2 * gamma)
  );
  const latitude = degreesToRadians(PRAGUE_ORLOJ_LATITUDE);
  const declinationRadians = degreesToRadians(declination);
  const zenith = degreesToRadians(90.833);
  const cosineHourAngle = clamp(
    Math.cos(zenith) / (Math.cos(latitude) * Math.cos(declinationRadians)) -
      Math.tan(latitude) * Math.tan(declinationRadians),
    -1,
    1,
  );
  const hourAngle = radiansToDegrees(Math.acos(cosineHourAngle));
  const solarNoonUTC = 720 - 4 * PRAGUE_ORLOJ_LONGITUDE - equationOfTime;
  return {
    equationOfTime,
    sunriseCET: (solarNoonUTC - 4 * hourAngle + 60) / 60,
    sunsetCET: (solarNoonUTC + 4 * hourAngle + 60) / 60,
  };
}

function pragueOrlojEclipticBasePoint(longitude) {
  const lambda = degreesToRadians(longitude);
  const obliquity = degreesToRadians(23.5);
  const rightAscension = Math.atan2(
    Math.sin(lambda) * Math.cos(obliquity),
    Math.cos(lambda),
  );
  const declination = Math.asin(Math.sin(obliquity) * Math.sin(lambda));
  const radius = PRAGUE_ORLOJ_EQUATOR_RADIUS * Math.tan(Math.PI / 4 + declination / 2);
  const hourAngle = -rightAscension;
  return {
    x: radius * Math.sin(hourAngle),
    y: -radius * Math.cos(hourAngle),
  };
}

function pragueOrlojClockwiseAngle(point) {
  return radiansToDegrees(Math.atan2(point.x, -point.y));
}

function pragueOrlojRotatePoint(point, clockwiseDegrees) {
  const angle = degreesToRadians(clockwiseDegrees);
  return {
    x: point.x * Math.cos(angle) - point.y * Math.sin(angle),
    y: point.x * Math.sin(angle) + point.y * Math.cos(angle),
  };
}

function pragueOrlojRayCircleIntersection(clockwiseDegrees, circleCenter, radius) {
  const angle = degreesToRadians(clockwiseDegrees);
  const unit = { x: Math.sin(angle), y: -Math.cos(angle) };
  const projection = unit.x * circleCenter.x + unit.y * circleCenter.y;
  const discriminant = Math.max(
    0,
    projection * projection + radius * radius -
      circleCenter.x * circleCenter.x - circleCenter.y * circleCenter.y,
  );
  return projection + Math.sqrt(discriminant);
}

function pragueOrlojMoonLightPath(phase) {
  const radius = 24;
  const litFraction = (1 - Math.cos(phase * Math.PI * 2)) / 2;
  const waxing = phase <= 0.5;
  const outer = [];
  const terminator = [];
  for (let index = 0; index <= 32; index += 1) {
    const y = -radius + (2 * radius * index) / 32;
    const edge = Math.sqrt(Math.max(0, radius * radius - y * y));
    if (waxing) {
      outer.push({ x: edge, y });
      terminator.unshift({ x: edge - 2 * edge * litFraction, y });
    } else {
      outer.push({ x: -edge, y });
      terminator.unshift({ x: -edge + 2 * edge * litFraction, y });
    }
  }
  const points = [...outer, ...terminator];
  if (litFraction < 0.0001) return "";
  return `${points.map((point, index) =>
    `${index === 0 ? "M" : "L"}${point.x.toFixed(2)} ${point.y.toFixed(2)}`
  ).join(" ")}Z`;
}

function pragueOrlojAutomatonState(displayTime) {
  const elapsed = displayTime.minute * 60 + displayTime.second + displayTime.millisecond / 1000;
  const scheduled = displayTime.hour >= 8 && displayTime.hour <= 23 && displayTime.minute === 0;
  if (!scheduled || elapsed >= 40) {
    return {
      active: false,
      phase: "waiting",
      windowOpen: 0,
      procession: 0,
      bellPulse: 0,
      roosterPulse: 0,
      figurePulse: 0,
    };
  }
  const open = smoothstep(elapsed / 3);
  const close = 1 - smoothstep((elapsed - 34) / 3);
  const windowOpen = Math.min(open, close);
  const procession = clamp((elapsed - 3) / 31);
  const bellPulse = elapsed < 35
    ? Math.max(0, Math.sin(elapsed * Math.PI * 1.7))
    : 0;
  const roosterPulse = elapsed >= 37
    ? Math.sin(clamp((elapsed - 37) / 3) * Math.PI)
    : 0;
  const figurePulse = Math.sin(elapsed * Math.PI * 0.86) * windowOpen;
  return {
    active: true,
    phase: elapsed < 3
      ? "opening"
      : elapsed < 34
        ? "apostles"
        : elapsed < 37
          ? "closing"
          : "rooster",
    windowOpen,
    procession,
    bellPulse,
    roosterPulse,
    figurePulse,
  };
}

function pragueOrlojClockState(value = new Date()) {
  const date = value instanceof Date ? new Date(value.getTime()) : new Date(value);
  if (!Number.isFinite(date.getTime())) throw new TypeError("Invalid Prague Orloj snapshot date");
  const quantizedDate = new Date(Math.floor(date.getTime() / UNIT_MS.minute) * UNIT_MS.minute);
  const cet = pragueOrlojCETParts(quantizedDate);
  const displayTime = displayTimeParts(date);
  const quantizedDisplayTime = displayTimeParts(quantizedDate);
  const julianDate = pragueOrlojJulianDate(quantizedDate);
  const solar = pragueOrlojSolarState(julianDate);
  const sunTimes = pragueOrlojSunTimes(cet, solar.declination);
  const siderealHours = pragueOrlojLocalSiderealHours(julianDate);
  const mechanicalSunAngle = positiveModulo((cet.hour + cet.minute / 60 - 12) * 15, 360);
  // The office-facing gold hand uses Beijing time. The zodiac, lunar and old
  // Czech mechanisms below retain their Prague astronomical reference frame.
  const sunAngle = positiveModulo(
    (quantizedDisplayTime.hour + quantizedDisplayTime.minute / 60 - 12) * 15,
    360,
  );
  const zodiacAngle = positiveModulo(siderealHours * 15, 360);
  const zodiacCenter = pragueOrlojRotatePoint(
    PRAGUE_ORLOJ_ZODIAC_CENTER_OFFSET,
    zodiacAngle,
  );
  const sunRadius = pragueOrlojRayCircleIntersection(
    sunAngle,
    zodiacCenter,
    PRAGUE_ORLOJ_ZODIAC_RADIUS,
  );
  const lunarPhase = positiveModulo(
    (julianDate - PRAGUE_ORLOJ_NEW_MOON_JD) / PRAGUE_ORLOJ_SYNODIC_MONTH_DAYS,
    1,
  );
  const lunarElongation = lunarPhase * 360;
  const moonLongitude = positiveModulo(solar.longitude + lunarElongation, 360);
  const moonZodiacPoint = pragueOrlojEclipticBasePoint(moonLongitude);
  const moonWorldPoint = pragueOrlojRotatePoint(moonZodiacPoint, zodiacAngle);
  const moonAngle = positiveModulo(pragueOrlojClockwiseAngle(moonWorldPoint), 360);
  const moonRadius = Math.hypot(moonWorldPoint.x, moonWorldPoint.y);
  const sunsetAngle = positiveModulo((sunTimes.sunsetCET - 12) * 15, 360);
  const dayLength = Math.max(0.001, sunTimes.sunsetCET - sunTimes.sunriseCET);
  const babylonianTime = cet.decimalHour >= sunTimes.sunriseCET && cet.decimalHour < sunTimes.sunsetCET
    ? clamp(Math.floor(12 * (cet.decimalHour - sunTimes.sunriseCET) / dayLength) + 1, 1, 12)
    : 0;
  const calendarProgress = (
    quantizedDisplayTime.dayOfYear - 1 + quantizedDisplayTime.decimalHour / 24
  ) / quantizedDisplayTime.daysInYear;
  const automaton = pragueOrlojAutomatonState(displayTime);
  return {
    timeZone: DISPLAY_TIME_ZONE,
    quantizedMinute: Math.floor(quantizedDate.getTime() / UNIT_MS.minute),
    displayHour24: displayTime.hour,
    displayMinute: displayTime.minute,
    displaySecond: displayTime.second,
    clockTime: `${pad2(displayTime.hour)}:${pad2(displayTime.minute)}`,
    mechanicalCetHour: cet.hour,
    mechanicalCetMinute: cet.minute,
    mechanicalSunAngle,
    sunAngle,
    sunRadius,
    solarLongitude: solar.longitude,
    solarDeclination: solar.declination,
    zodiacAngle,
    siderealHours,
    moonAngle,
    moonRadius,
    moonLongitude,
    lunarPhase,
    lunarIllumination: (1 - Math.cos(degreesToRadians(lunarElongation))) / 2,
    sunriseCET: sunTimes.sunriseCET,
    sunsetCET: sunTimes.sunsetCET,
    oldCzechRingAngle: sunsetAngle,
    oldCzechTime: positiveModulo(cet.decimalHour - sunTimes.sunsetCET, 24),
    babylonianTime,
    calendarAngle: positiveModulo(-calendarProgress * 360, 360),
    civilHour: displayTime.hour,
    automaton,
    label: `${pad2(displayTime.hour)}:${pad2(displayTime.minute)} 北京时间 · 月相${Math.round((1 - Math.cos(degreesToRadians(lunarElongation))) * 50)}%`,
  };
}

function createPragueOrlojText(content, x, y, className = "") {
  const text = document.createElementNS(CORPUS_CLOCK_NS, "text");
  text.textContent = content;
  text.setAttribute("x", x.toFixed(2));
  text.setAttribute("y", y.toFixed(2));
  if (className) text.setAttribute("class", className);
  return text;
}

function populatePragueOrlojApostles(container, side) {
  if (!container || container.childElementCount) return;
  const robeColors = side === "left"
    ? ["#7b3e37", "#3f7467", "#6b4a70", "#365c74", "#795735", "#4c6b4a"]
    : ["#365c74", "#795735", "#3f7467", "#7b3e37", "#6b4a70", "#4c6b4a"];
  const startX = side === "left" ? 396 : 628;
  for (let index = 0; index < 6; index += 1) {
    const group = document.createElementNS(CORPUS_CLOCK_NS, "g");
    group.setAttribute("class", "orloj-apostle");
    group.setAttribute("transform", `translate(${startX + index * 164} 0)`);
    group.style.setProperty("--apostle-robe", robeColors[index]);
    const halo = document.createElementNS(CORPUS_CLOCK_NS, "circle");
    halo.setAttribute("class", "halo");
    halo.setAttribute("cx", "0");
    halo.setAttribute("cy", "128");
    halo.setAttribute("r", "27");
    const body = document.createElementNS(CORPUS_CLOCK_NS, "path");
    body.setAttribute("class", "body");
    body.setAttribute("d", "M-31 226v-58q0-34 31-34t31 34v58Z");
    const head = document.createElementNS(CORPUS_CLOCK_NS, "circle");
    head.setAttribute("class", "head");
    head.setAttribute("cx", "0");
    head.setAttribute("cy", "128");
    head.setAttribute("r", "20");
    const attribute = document.createElementNS(CORPUS_CLOCK_NS, "path");
    attribute.setAttribute("class", "attribute");
    const attributePaths = side === "left"
      ? ["M-24 161l43 50M-20 205l40-42", "M-23 170h46M0 154v63", "M-17 161v52M17 161v52M-17 184h34", "M-21 166l42 45M21 166l-42 45", "M0 156v59M-20 176h40", "M-24 206l48-37M-17 164l34 47"]
      : ["M-22 160h44v52h-44ZM0 160v52", "M0 153v65M-10 168h20", "M-24 181h48M-20 164l40 34M-20 198l40-34", "M-22 160h44v51h-44M-15 174h30M-15 190h30", "M-23 164q23 15 46 0v47q-23 15-46 0Z", "M-22 160h44v52h-44M-14 174h28M-14 190h28"];
    attribute.setAttribute("d", attributePaths[index]);
    group.append(halo, body, head, attribute);
    container.append(group);
  }
}

function populatePragueOrlojDecoration() {
  if (pragueOrlojOldCzechNumerals && !pragueOrlojOldCzechNumerals.childElementCount) {
    for (let index = 0; index < 24; index += 1) {
      const angle = index * 15;
      const point = pragueOrlojPolar(333, angle);
      const text = createPragueOrlojText(String(index || 24), point.x, point.y);
      text.setAttribute("transform", `rotate(${angle} ${point.x.toFixed(2)} ${point.y.toFixed(2)})`);
      pragueOrlojOldCzechNumerals.append(text);
    }
  }
  if (pragueOrlojCivilNumerals && !pragueOrlojCivilNumerals.childElementCount) {
    for (let index = 0; index < 24; index += 1) {
      const angle = index * 15;
      const point = pragueOrlojPolar(281, angle);
      const numeral = PRAGUE_ORLOJ_ROMAN_NUMERALS[index % 12];
      const text = createPragueOrlojText(numeral, point.x, point.y);
      text.setAttribute("transform", `rotate(${angle} ${point.x.toFixed(2)} ${point.y.toFixed(2)})`);
      pragueOrlojCivilNumerals.append(text);
    }
  }
  if (pragueOrlojZodiacDivisions && !pragueOrlojZodiacDivisions.childElementCount) {
    const zodiacCenter = {
      x: PRAGUE_ORLOJ_CENTER.x + PRAGUE_ORLOJ_ZODIAC_CENTER_OFFSET.x,
      y: PRAGUE_ORLOJ_CENTER.y + PRAGUE_ORLOJ_ZODIAC_CENTER_OFFSET.y,
    };
    for (let index = 0; index < 72; index += 1) {
      const angle = index * 5;
      const radians = degreesToRadians(angle - 90);
      const outerRadius = PRAGUE_ORLOJ_ZODIAC_RADIUS - 5;
      const innerRadius = index % 6 === 0 ? 166 : 194;
      const path = document.createElementNS(CORPUS_CLOCK_NS, "path");
      path.setAttribute(
        "d",
        `M${(zodiacCenter.x + Math.cos(radians) * innerRadius).toFixed(2)} ${(zodiacCenter.y + Math.sin(radians) * innerRadius).toFixed(2)} ` +
        `L${(zodiacCenter.x + Math.cos(radians) * outerRadius).toFixed(2)} ${(zodiacCenter.y + Math.sin(radians) * outerRadius).toFixed(2)}`,
      );
      if (index % 6 !== 0) path.classList.add("is-day-mark");
      pragueOrlojZodiacDivisions.append(path);
    }
  }
  if (pragueOrlojZodiacGlyphs && !pragueOrlojZodiacGlyphs.childElementCount) {
    PRAGUE_ORLOJ_ZODIAC_GLYPHS.forEach((glyph, index) => {
      const eclipticPoint = pragueOrlojEclipticBasePoint(index * 30);
      const point = {
        x: PRAGUE_ORLOJ_CENTER.x + eclipticPoint.x,
        y: PRAGUE_ORLOJ_CENTER.y + eclipticPoint.y,
      };
      const angle = pragueOrlojClockwiseAngle(eclipticPoint);
      const text = createPragueOrlojText(glyph, point.x, point.y);
      text.setAttribute("transform", `rotate(${angle} ${point.x.toFixed(2)} ${point.y.toFixed(2)})`);
      pragueOrlojZodiacGlyphs.append(text);
    });
  }
  if (pragueOrlojBabylonianLines && !pragueOrlojBabylonianLines.childElementCount) {
    for (let index = 1; index <= 12; index += 1) {
      const angle = -90 + (index / 12) * 180;
      const inner = pragueOrlojPolar(112, angle);
      const outer = pragueOrlojPolar(276, angle);
      const control = pragueOrlojPolar(205, angle + (index - 6.5) * 0.9);
      const path = document.createElementNS(CORPUS_CLOCK_NS, "path");
      path.setAttribute(
        "d",
        `M${inner.x.toFixed(2)} ${inner.y.toFixed(2)} Q${control.x.toFixed(2)} ${control.y.toFixed(2)} ${outer.x.toFixed(2)} ${outer.y.toFixed(2)}`,
      );
      path.dataset.hour = String(index);
      pragueOrlojBabylonianLines.append(path);
    }
  }
  if (pragueOrlojCalendarMarks && !pragueOrlojCalendarMarks.childElementCount) {
    PRAGUE_ORLOJ_MONTHS.forEach((month, index) => {
      const angle = index * 30;
      const inner = pragueOrlojPolar(55, angle, { x: 512, y: 1067 });
      const outer = pragueOrlojPolar(96, angle, { x: 512, y: 1067 });
      const label = pragueOrlojPolar(78, angle + 15, { x: 512, y: 1067 });
      const path = document.createElementNS(CORPUS_CLOCK_NS, "path");
      path.setAttribute("d", `M${inner.x.toFixed(2)} ${inner.y.toFixed(2)}L${outer.x.toFixed(2)} ${outer.y.toFixed(2)}`);
      const text = createPragueOrlojText(month, label.x, label.y);
      text.setAttribute("transform", `rotate(${angle + 15} ${label.x.toFixed(2)} ${label.y.toFixed(2)})`);
      pragueOrlojCalendarMarks.append(path, text);
    });
  }
  populatePragueOrlojApostles(pragueOrlojLeftApostles, "left");
  populatePragueOrlojApostles(pragueOrlojRightApostles, "right");
}

function updatePragueOrlojClock(date = new Date(), force = false) {
  if (!pragueOrlojClock || !corpusClock) return;
  const state = pragueOrlojClockState(date);
  const reduceMotion = shouldReduceMotion();
  corpusClock.dataset.reducedMotion = String(reduceMotion);
  if (force || state.quantizedMinute !== pragueOrlojLastMinute) {
    pragueOrlojSunAngle = unwrapClockAngle(pragueOrlojSunAngle, state.sunAngle);
    pragueOrlojZodiacAngle = unwrapClockAngle(pragueOrlojZodiacAngle, state.zodiacAngle);
    pragueOrlojMoonAngle = unwrapClockAngle(pragueOrlojMoonAngle, state.moonAngle);
    pragueOrlojOldCzechAngle = unwrapClockAngle(
      pragueOrlojOldCzechAngle,
      state.oldCzechRingAngle,
    );
    pragueOrlojCalendarAngle = unwrapClockAngle(
      pragueOrlojCalendarAngle,
      state.calendarAngle,
    );
    corpusClock.style.setProperty("--orloj-zodiac-angle", `${pragueOrlojZodiacAngle.toFixed(6)}deg`);
    corpusClock.style.setProperty("--orloj-sun-angle", `${pragueOrlojSunAngle.toFixed(6)}deg`);
    corpusClock.style.setProperty("--orloj-moon-angle", `${pragueOrlojMoonAngle.toFixed(6)}deg`);
    corpusClock.style.setProperty("--orloj-old-czech-angle", `${pragueOrlojOldCzechAngle.toFixed(6)}deg`);
    corpusClock.style.setProperty("--orloj-calendar-angle", `${pragueOrlojCalendarAngle.toFixed(6)}deg`);
    const sunPoint = pragueOrlojPolar(state.sunRadius, state.sunAngle);
    const moonPoint = pragueOrlojPolar(state.moonRadius, state.moonAngle);
    pragueOrlojSunSymbol?.setAttribute(
      "transform",
      `translate(${sunPoint.x.toFixed(3)} ${sunPoint.y.toFixed(3)})`,
    );
    pragueOrlojMoonSymbol?.setAttribute(
      "transform",
      `translate(${moonPoint.x.toFixed(3)} ${moonPoint.y.toFixed(3)})`,
    );
    pragueOrlojMoonLight?.setAttribute("d", pragueOrlojMoonLightPath(state.lunarPhase));
    pragueOrlojBabylonianLines?.querySelectorAll("path").forEach((path) => {
      path.classList.toggle("is-current", Number(path.dataset.hour) === state.babylonianTime);
    });
    pragueOrlojClock.dataset.sunAngle = state.sunAngle.toFixed(6);
    pragueOrlojClock.dataset.mechanicalSunAngle = state.mechanicalSunAngle.toFixed(6);
    pragueOrlojClock.dataset.timeZone = state.timeZone;
    pragueOrlojClock.dataset.sunRadius = state.sunRadius.toFixed(6);
    pragueOrlojClock.dataset.zodiacAngle = state.zodiacAngle.toFixed(6);
    pragueOrlojClock.dataset.moonAngle = state.moonAngle.toFixed(6);
    pragueOrlojClock.dataset.moonRadius = state.moonRadius.toFixed(6);
    pragueOrlojClock.dataset.moonIllumination = state.lunarIllumination.toFixed(6);
    pragueOrlojClock.dataset.solarDeclination = state.solarDeclination.toFixed(6);
    pragueOrlojClock.dataset.sunriseCet = state.sunriseCET.toFixed(6);
    pragueOrlojClock.dataset.sunsetCet = state.sunsetCET.toFixed(6);
    pragueOrlojClock.dataset.oldCzechRingAngle = state.oldCzechRingAngle.toFixed(6);
    pragueOrlojClock.dataset.oldCzechTime = state.oldCzechTime.toFixed(4);
    pragueOrlojClock.dataset.babylonianHour = String(state.babylonianTime);
    pragueOrlojClock.dataset.siderealHours = state.siderealHours.toFixed(6);
    pragueOrlojClock.dataset.civilHour = String(state.civilHour);
    pragueOrlojClock.dataset.displayTime = state.clockTime;
    pragueOrlojLastMinute = state.quantizedMinute;
  }
  const automaton = reduceMotion
    ? { ...state.automaton, windowOpen: 0, procession: 0, bellPulse: 0, roosterPulse: 0, figurePulse: 0 }
    : state.automaton;
  corpusClock.style.setProperty("--orloj-window-open", automaton.windowOpen.toFixed(4));
  corpusClock.style.setProperty("--orloj-automaton", automaton.figurePulse.toFixed(4));
  corpusClock.style.setProperty("--orloj-bell-pulse", automaton.bellPulse.toFixed(4));
  corpusClock.style.setProperty("--orloj-rooster-pulse", automaton.roosterPulse.toFixed(4));
  const processionOffset = automaton.procession * 820;
  pragueOrlojLeftApostles?.setAttribute("transform", `translate(${-processionOffset.toFixed(3)} 0)`);
  pragueOrlojRightApostles?.setAttribute("transform", `translate(${-processionOffset.toFixed(3)} 0)`);
  pragueOrlojClock.classList.toggle("is-automaton-active", automaton.active && !reduceMotion);
  pragueOrlojClock.dataset.automatonPhase = reduceMotion ? "reduced-motion" : automaton.phase;
  if (pragueOrlojClockTime && (force || state.label !== pragueOrlojLastLabel)) {
    pragueOrlojClockTime.textContent = state.label;
    pragueOrlojClockTime.dateTime = state.clockTime;
    pragueOrlojLastLabel = state.label;
    if (activeHeaderClockId === "prague-orloj") refreshHeaderClockTitle();
  }
}

function initializePragueOrlojClock() {
  populatePragueOrlojDecoration();
  updatePragueOrlojClock(corpusClockRenderDate(), true);
}

function pragueOrlojClockSnapshot(value = new Date()) {
  const state = pragueOrlojClockState(value);
  return Object.freeze({
    ...state,
    automaton: Object.freeze({ ...state.automaton }),
  });
}

if (typeof window !== "undefined") {
  Object.defineProperty(window, "__pragueOrlojClockSnapshot", {
    value: pragueOrlojClockSnapshot,
    configurable: false,
    writable: false,
  });
}

function bernZytgloggePulseTrain(elapsed, start, end, count = 1) {
  if (elapsed < start || elapsed >= end || end <= start || count <= 0) return 0;
  const progress = (elapsed - start) / (end - start);
  const cycle = positiveModulo(progress * count, 1);
  const edgeEnvelope = smoothstep(progress * 10) * smoothstep((1 - progress) * 10);
  return Math.sin(cycle * Math.PI) ** 1.35 * edgeEnvelope;
}

function bernZytgloggeLocalSiderealHours(julianDate) {
  const daysSinceJ2000 = julianDate - 2451545;
  const julianCenturies = daysSinceJ2000 / 36525;
  const gmstDegrees =
    280.46061837 +
    360.98564736629 * daysSinceJ2000 +
    0.000387933 * julianCenturies * julianCenturies -
    (julianCenturies * julianCenturies * julianCenturies) / 38710000;
  return positiveModulo(
    (gmstDegrees + BERN_ZYTGLOGGE_LONGITUDE) / 15,
    24,
  );
}

function bernZytgloggeAutomatonState(displayTime) {
  const secondsIntoHour =
    displayTime.minute * 60 + displayTime.second + displayTime.millisecond / 1000;
  const secondsWithinMinute = displayTime.second + displayTime.millisecond / 1000;
  const startSecond = 3600 - BERN_ZYTGLOGGE_AUTOMATON_LEAD_SECONDS;
  const beforeHour = secondsIntoHour >= startSecond;
  const targetHour24 = beforeHour
    ? (displayTime.hour + 1) % 24
    : displayTime.hour;
  const hourStrikeCount = targetHour24 % 12 || 12;
  const timeline = BERN_ZYTGLOGGE_AUTOMATON_TIMELINE;
  const hansStart = timeline.chronosEnd;
  const hansEnd = hansStart +
    hourStrikeCount * timeline.hansStrikeSpacing + timeline.hansRelease;
  const finalRoosterEnd = hansEnd + timeline.finalRoosterDuration;
  const elapsed = beforeHour
    ? secondsIntoHour - startSecond
    : BERN_ZYTGLOGGE_AUTOMATON_LEAD_SECONDS + secondsIntoHour;
  const active = (beforeHour || secondsIntoHour < finalRoosterEnd -
    BERN_ZYTGLOGGE_AUTOMATON_LEAD_SECONDS) && elapsed < finalRoosterEnd;
  const secondsUntilHour = beforeHour || !active ? 3600 - secondsIntoHour : 0;

  if (!active) {
    const quarterCount = displayTime.minute > 0 && displayTime.minute % 15 === 0
      ? displayTime.minute / 15
      : 0;
    const quarterEnd = quarterCount * timeline.hansStrikeSpacing + timeline.hansRelease;
    if (quarterCount && secondsWithinMinute < quarterEnd) {
      const quarterPulse = bernZytgloggePulseTrain(
        secondsWithinMinute,
        0,
        quarterEnd,
        quarterCount,
      );
      return {
        active: true,
        phase: "quarter-bells",
        elapsed: secondsWithinMinute,
        progress: clamp(secondsWithinMinute / quarterEnd),
        secondsUntilHour,
        targetHour24: displayTime.hour,
        hourStrikeCount: 0,
        quarterStrikeCount: quarterCount,
        bearLap: 0,
        roosterPulse: 0,
        bearParade: 0,
        jesterAngle: 0,
        jesterLeftAngle: 0,
        jesterRightAngle: 0,
        quarterPulse,
        chronosAngle: 0,
        hourglassAngle: 0,
        jacquemartAngle: 0,
        bellPulse: 0,
      };
    }
    return {
      active: false,
      phase: "waiting",
      elapsed: -1,
      progress: 0,
      secondsUntilHour,
      targetHour24,
      hourStrikeCount,
      quarterStrikeCount: 0,
      bearLap: 0,
      roosterPulse: 0,
      bearParade: 0,
      jesterAngle: 0,
      jesterLeftAngle: 0,
      jesterRightAngle: 0,
      quarterPulse: 0,
      chronosAngle: 0,
      hourglassAngle: 0,
      jacquemartAngle: 0,
      bellPulse: 0,
    };
  }

  const openingRoosterPulse = bernZytgloggePulseTrain(
    elapsed,
    0,
    timeline.openingRoosterEnd,
    3,
  );
  const bearRouteProgress = clamp(
    (elapsed - timeline.openingRoosterEnd) /
      (timeline.bearParadeEnd - timeline.openingRoosterEnd),
  ) * hourStrikeCount;
  const bearParade = elapsed >= timeline.openingRoosterEnd &&
    elapsed < timeline.bearParadeEnd
    ? positiveModulo(bearRouteProgress, 1)
    : 0;
  const bearLap = elapsed >= timeline.openingRoosterEnd && elapsed < timeline.bearParadeEnd
    ? Math.min(hourStrikeCount, Math.floor(bearRouteProgress) + 1)
    : 0;
  const jesterPulse = bernZytgloggePulseTrain(
    elapsed,
    timeline.openingRoosterEnd,
    timeline.bearParadeEnd,
    hourStrikeCount,
  );
  const secondRoosterPulse = bernZytgloggePulseTrain(
    elapsed,
    timeline.bearParadeEnd,
    timeline.secondRoosterEnd,
    3,
  );
  const quarterPulse = bernZytgloggePulseTrain(
    elapsed,
    timeline.hourThreshold,
    timeline.quarterBellsEnd,
    4,
  );
  const chronosProgress = clamp(
    (elapsed - timeline.quarterBellsEnd) /
      (timeline.chronosEnd - timeline.quarterBellsEnd),
  );
  const hansPulse = bernZytgloggePulseTrain(
    elapsed,
    hansStart,
    hansEnd,
    hourStrikeCount,
  );
  const finalRoosterPulse = bernZytgloggePulseTrain(
    elapsed,
    hansEnd,
    finalRoosterEnd,
    3,
  );
  const finalRoosterProgress = clamp(
    (elapsed - hansEnd) / (finalRoosterEnd - hansEnd),
  );
  const chronosRaised = elapsed < timeline.quarterBellsEnd
    ? 0
    : elapsed < timeline.chronosEnd
      ? smootherstep(chronosProgress)
      : elapsed < hansEnd
        ? 1
        : 1 - smootherstep(finalRoosterProgress);
  const jesterLeftAngle = -34 * jesterPulse;
  const jesterRightAngle = 34 * jesterPulse;
  const phase = elapsed < timeline.openingRoosterEnd
    ? "opening-rooster"
    : elapsed < timeline.jesterFeatureStart
      ? "bear-parade"
      : elapsed < timeline.bearParadeEnd
        ? "jester"
        : elapsed < timeline.secondRoosterEnd
          ? "second-rooster"
          : elapsed < timeline.hourThreshold
            ? "hour-ready"
            : elapsed < timeline.quarterBellsEnd
              ? "quarter-bells"
              : elapsed < timeline.chronosEnd
                ? "chronos"
                : elapsed < hansEnd
                  ? "hans-strikes"
                  : "final-rooster";

  return {
    active: true,
    phase,
    elapsed,
    progress: clamp(elapsed / finalRoosterEnd),
    secondsUntilHour,
    targetHour24,
    hourStrikeCount,
    quarterStrikeCount: 4,
    bearLap,
    roosterPulse: Math.max(
      openingRoosterPulse,
      secondRoosterPulse,
      finalRoosterPulse,
    ),
    bearParade,
    jesterAngle: jesterLeftAngle,
    jesterLeftAngle,
    jesterRightAngle,
    quarterPulse,
    chronosAngle: 28 * chronosRaised - 12 * hansPulse,
    hourglassAngle: 180 * chronosRaised,
    jacquemartAngle: -42 * hansPulse,
    bellPulse: hansPulse,
  };
}

function bernZytgloggeClockState(value = new Date()) {
  const date = value instanceof Date ? new Date(value.getTime()) : new Date(value);
  if (!Number.isFinite(date.getTime())) {
    throw new TypeError("Invalid Bern Zytglogge snapshot date");
  }
  const displayTime = displayTimeParts(date);
  const seconds = displayTime.second + displayTime.millisecond / 1000;
  const decimalMinute = displayTime.minute + seconds / 60;
  const decimalHour = displayTime.hour + decimalMinute / 60;
  const julianDate = pragueOrlojJulianDate(date);
  const siderealHours = bernZytgloggeLocalSiderealHours(julianDate);
  const lunarPhase = positiveModulo(
    (julianDate - BERN_ZYTGLOGGE_NEW_MOON_JD) /
      BERN_ZYTGLOGGE_SYNODIC_MONTH_DAYS,
    1,
  );
  const lunarElongation = lunarPhase * 360;
  const mainMinuteAngle = positiveModulo(decimalMinute * 6, 360);
  const mainHourAngle = positiveModulo(((displayTime.hour % 12) + decimalMinute / 60) * 30, 360);
  // The Bern astrolabe places local noon at the crown and midnight below.
  const sunAngle = positiveModulo((decimalHour - 12) * 15, 360);
  const zodiacAngle = positiveModulo(siderealHours * 15, 360);
  const zodiacCenterOffset = pragueOrlojRotatePoint(
    BERN_ZYTGLOGGE_ZODIAC_CENTER_OFFSET,
    zodiacAngle,
  );
  const zodiacCenter = {
    x: BERN_ZYTGLOGGE_CENTER.x + zodiacCenterOffset.x,
    y: BERN_ZYTGLOGGE_CENTER.y + zodiacCenterOffset.y,
  };
  const sunRadius = pragueOrlojRayCircleIntersection(
    sunAngle,
    zodiacCenterOffset,
    BERN_ZYTGLOGGE_ZODIAC_OUTER_RADIUS,
  );
  // Subtracting elongation makes the lunar hand complete a circuit in about
  // 24 h 50 m while the gold solar hand completes one in 24 h.
  const moonAngle = positiveModulo(sunAngle - lunarElongation, 360);
  const lunarIllumination = (1 - Math.cos(degreesToRadians(lunarElongation))) / 2;
  const automaton = bernZytgloggeAutomatonState(displayTime);
  return {
    timeZone: DISPLAY_TIME_ZONE,
    beat: Math.floor(date.getTime() / 1000),
    dayKey: `${displayTime.year}-${pad2(displayTime.month + 1)}-${pad2(displayTime.day)}`,
    displayYear: displayTime.year,
    displayMonth: displayTime.month + 1,
    displayDay: displayTime.day,
    displayHour24: displayTime.hour,
    displayMinute: displayTime.minute,
    displaySecond: displayTime.second,
    mainHourAngle,
    mainHourCounterAngle: -mainHourAngle,
    mainMinuteAngle,
    upperQuarterAngle: mainMinuteAngle,
    sunAngle,
    sunRadius,
    twentyFourHourAngle: sunAngle,
    zodiacAngle,
    zodiacCenter,
    siderealHours,
    moonAngle,
    lunarPhase,
    lunarIllumination,
    calendarAngle: zodiacAngle,
    automaton,
    clockTime: displayTime.clockTime,
    label: `${displayTime.clockTime} 北京时间 · 月相${Math.round(lunarIllumination * 100)}%`,
  };
}

function updateBernZytgloggeClock(date = new Date(), force = false) {
  if (!bernZytgloggeClock || !corpusClock) return;
  const state = bernZytgloggeClockState(date);
  const reduceMotion = shouldReduceMotion();
  corpusClock.dataset.reducedMotion = String(reduceMotion);
  if (force || state.beat !== bernZytgloggeLastBeat) {
    bernZytgloggeMainHourAngle = unwrapClockAngle(
      bernZytgloggeMainHourAngle,
      state.mainHourAngle,
    );
    bernZytgloggeMainMinuteAngle = unwrapClockAngle(
      bernZytgloggeMainMinuteAngle,
      state.mainMinuteAngle,
    );
    bernZytgloggeSunAngle = unwrapClockAngle(bernZytgloggeSunAngle, state.sunAngle);
    bernZytgloggeZodiacAngle = unwrapClockAngle(
      bernZytgloggeZodiacAngle,
      state.zodiacAngle,
    );
    bernZytgloggeMoonAngle = unwrapClockAngle(bernZytgloggeMoonAngle, state.moonAngle);
    bernZytgloggeCalendarAngle = unwrapClockAngle(
      bernZytgloggeCalendarAngle,
      state.calendarAngle,
    );
    corpusClock.style.setProperty(
      "--zyt-main-hour-angle",
      `${bernZytgloggeMainHourAngle.toFixed(6)}deg`,
    );
    corpusClock.style.setProperty(
      "--zyt-main-hour-counter-angle",
      `${(-bernZytgloggeMainHourAngle).toFixed(6)}deg`,
    );
    corpusClock.style.setProperty(
      "--zyt-main-minute-angle",
      `${bernZytgloggeMainMinuteAngle.toFixed(6)}deg`,
    );
    corpusClock.style.setProperty("--zyt-sun-angle", `${bernZytgloggeSunAngle.toFixed(6)}deg`);
    corpusClock.style.setProperty(
      "--zyt-zodiac-angle",
      `${bernZytgloggeZodiacAngle.toFixed(6)}deg`,
    );
    corpusClock.style.setProperty("--zyt-moon-angle", `${bernZytgloggeMoonAngle.toFixed(6)}deg`);
    corpusClock.style.setProperty(
      "--zyt-calendar-angle",
      `${bernZytgloggeCalendarAngle.toFixed(6)}deg`,
    );
    corpusClock.style.setProperty(
      "--zyt-moon-illumination",
      state.lunarIllumination.toFixed(6),
    );
    bernZytgloggeMainHourHand?.setAttribute("data-angle", state.mainHourAngle.toFixed(6));
    bernZytgloggeMainMinuteHand?.setAttribute("data-angle", state.mainMinuteAngle.toFixed(6));
    bernZytgloggeSunHand?.setAttribute("data-angle", state.sunAngle.toFixed(6));
    bernZytgloggeAstrolabeZodiac?.setAttribute("data-angle", state.zodiacAngle.toFixed(6));
    bernZytgloggeMoonSymbol?.setAttribute("data-angle", state.moonAngle.toFixed(6));
    bernZytgloggeMoonLight?.setAttribute("d", pragueOrlojMoonLightPath(state.lunarPhase));
    bernZytgloggeMoonLight?.setAttribute("transform", "translate(350 693)");
    bernZytgloggeCalendarDisk?.setAttribute("data-angle", state.calendarAngle.toFixed(6));
    bernZytgloggeClock.dataset.timeZone = state.timeZone;
    bernZytgloggeClock.dataset.displayTime = state.clockTime;
    bernZytgloggeClock.dataset.mainHourAngle = state.mainHourAngle.toFixed(6);
    bernZytgloggeClock.dataset.mainHourCounterAngle =
      (-bernZytgloggeMainHourAngle).toFixed(6);
    bernZytgloggeClock.dataset.mainMinuteAngle = state.mainMinuteAngle.toFixed(6);
    bernZytgloggeClock.dataset.sunAngle = state.sunAngle.toFixed(6);
    bernZytgloggeClock.dataset.zodiacAngle = state.zodiacAngle.toFixed(6);
    bernZytgloggeClock.dataset.siderealHours = state.siderealHours.toFixed(6);
    bernZytgloggeClock.dataset.moonAngle = state.moonAngle.toFixed(6);
    bernZytgloggeClock.dataset.moonIllumination = state.lunarIllumination.toFixed(6);
    bernZytgloggeLastBeat = state.beat;
  }
  const sunSymbolY = BERN_ZYTGLOGGE_CENTER.y - state.sunRadius;
  bernZytgloggeSunSymbol?.setAttribute(
    "transform",
    `translate(${BERN_ZYTGLOGGE_CENTER.x.toFixed(3)} ${sunSymbolY.toFixed(3)})`,
  );
  bernZytgloggeSunSymbol?.setAttribute("data-radius", state.sunRadius.toFixed(6));
  bernZytgloggeClock.dataset.sunRadius = state.sunRadius.toFixed(6);
  bernZytgloggeClock.dataset.zodiacCenterX = state.zodiacCenter.x.toFixed(6);
  bernZytgloggeClock.dataset.zodiacCenterY = state.zodiacCenter.y.toFixed(6);
  if (force || state.dayKey !== bernZytgloggeLastDayKey) {
    if (bernZytgloggeCalendarDate) {
      bernZytgloggeCalendarDate.textContent = String(state.displayDay);
    }
    bernZytgloggeClock.dataset.displayDate = state.dayKey;
    bernZytgloggeLastDayKey = state.dayKey;
  }

  const automaton = reduceMotion
    ? {
      ...state.automaton,
      roosterPulse: 0,
      bearParade: 0,
      jesterAngle: 0,
      jesterLeftAngle: 0,
      jesterRightAngle: 0,
      quarterPulse: 0,
      chronosAngle: 0,
      hourglassAngle: 0,
      jacquemartAngle: 0,
      bellPulse: 0,
    }
    : state.automaton;
  corpusClock.style.setProperty("--zyt-rooster-pulse", automaton.roosterPulse.toFixed(4));
  corpusClock.style.setProperty("--zyt-bear-parade", automaton.bearParade.toFixed(4));
  corpusClock.style.setProperty("--zyt-jester-angle", `${automaton.jesterAngle.toFixed(4)}deg`);
  corpusClock.style.setProperty(
    "--zyt-jester-left-angle",
    `${automaton.jesterLeftAngle.toFixed(4)}deg`,
  );
  corpusClock.style.setProperty(
    "--zyt-jester-right-angle",
    `${automaton.jesterRightAngle.toFixed(4)}deg`,
  );
  corpusClock.style.setProperty("--zyt-quarter-pulse", automaton.quarterPulse.toFixed(4));
  corpusClock.style.setProperty("--zyt-chronos-angle", `${automaton.chronosAngle.toFixed(4)}deg`);
  corpusClock.style.setProperty(
    "--zyt-hourglass-angle",
    `${automaton.hourglassAngle.toFixed(4)}deg`,
  );
  const hourStrikePulse = Math.abs(automaton.jacquemartAngle) / 42;
  corpusClock.style.setProperty("--zyt-chronos-count", hourStrikePulse.toFixed(4));
  corpusClock.style.setProperty("--zyt-lion-pulse", hourStrikePulse.toFixed(4));
  corpusClock.style.setProperty(
    "--zyt-jacquemart-angle",
    `${automaton.jacquemartAngle.toFixed(4)}deg`,
  );
  corpusClock.style.setProperty("--zyt-bell-pulse", automaton.bellPulse.toFixed(4));
  bernZytgloggeClock.classList.toggle(
    "is-mechanism-active",
    state.automaton.active && !reduceMotion,
  );
  bernZytgloggeClock.dataset.mechanismPhase = reduceMotion
    ? "reduced-motion"
    : automaton.phase;
  bernZytgloggeClock.dataset.secondsUntilHour = automaton.secondsUntilHour.toFixed(3);
  bernZytgloggeClock.dataset.hourStrikeCount = String(automaton.hourStrikeCount);
  bernZytgloggeClock.dataset.quarterStrikeCount = String(automaton.quarterStrikeCount);
  bernZytgloggeClock.dataset.bearLap = String(automaton.bearLap);
  bernZytgloggeClock.dataset.quarterPulse = automaton.quarterPulse.toFixed(4);
  bernZytgloggeClock.dataset.bellPulse = automaton.bellPulse.toFixed(4);
  bernZytgloggeClock.dataset.jesterLeftAngle = automaton.jesterLeftAngle.toFixed(4);
  bernZytgloggeClock.dataset.jesterRightAngle = automaton.jesterRightAngle.toFixed(4);
  bernZytgloggeClock.dataset.hourglassAngle = automaton.hourglassAngle.toFixed(4);
  bernZytgloggeBearParade?.setAttribute("data-progress", automaton.bearParade.toFixed(4));
  bernZytgloggeJesterArm?.setAttribute("data-angle", automaton.jesterAngle.toFixed(4));
  bernZytgloggeJesterArm?.setAttribute("data-left-angle", automaton.jesterLeftAngle.toFixed(4));
  bernZytgloggeJesterArm?.setAttribute("data-right-angle", automaton.jesterRightAngle.toFixed(4));
  bernZytgloggeRooster?.setAttribute("data-pulse", automaton.roosterPulse.toFixed(4));
  bernZytgloggeChronosArm?.setAttribute("data-angle", automaton.chronosAngle.toFixed(4));
  bernZytgloggeChronosHourglass?.setAttribute(
    "data-angle",
    automaton.hourglassAngle.toFixed(4),
  );
  bernZytgloggeChronosMouth?.setAttribute("data-pulse", hourStrikePulse.toFixed(4));
  bernZytgloggeLion?.setAttribute("data-pulse", hourStrikePulse.toFixed(4));
  bernZytgloggeJacquemartArm?.setAttribute("data-angle", automaton.jacquemartAngle.toFixed(4));
  bernZytgloggeBell?.setAttribute("data-pulse", automaton.bellPulse.toFixed(4));
  bernZytgloggeQuarterBell?.setAttribute("data-pulse", automaton.quarterPulse.toFixed(4));
  if (bernZytgloggeClockTime && (force || state.label !== bernZytgloggeLastLabel)) {
    bernZytgloggeClockTime.textContent = state.label;
    bernZytgloggeClockTime.dateTime = state.clockTime;
    bernZytgloggeLastLabel = state.label;
    if (activeHeaderClockId === "bern-zytglogge") refreshHeaderClockTitle();
  }
}

function initializeBernZytgloggeClock() {
  updateBernZytgloggeClock(corpusClockRenderDate(), true);
}

function bernZytgloggeClockSnapshot(value = new Date()) {
  const state = bernZytgloggeClockState(value);
  return Object.freeze({
    ...state,
    zodiacCenter: Object.freeze({ ...state.zodiacCenter }),
    automaton: Object.freeze({ ...state.automaton }),
  });
}

if (typeof window !== "undefined") {
  Object.defineProperty(window, "__bernZytgloggeClockSnapshot", {
    value: bernZytgloggeClockSnapshot,
    configurable: false,
    writable: false,
  });
}

function corpusClockOffsetSeconds(secondsOfDay) {
  const cycle = positiveModulo(secondsOfDay, 5 * 60);
  const progress = cycle / (5 * 60);
  const envelope = Math.sin(Math.PI * progress) ** 2;
  const hesitation = Math.sin(cycle * 0.091 + 0.7) * 4.2;
  const lurch = Math.sin(cycle * 0.029 - 0.4) * 3.1;
  const bite = Math.sin(Math.floor(cycle / 15) * 2.174) * 1.15;
  return (hesitation + lurch + bite) * envelope;
}

function corpusClockBlinking(realSeconds) {
  const minute = Math.floor(realSeconds / 60);
  const second = positiveModulo(realSeconds, 60);
  const firstBlink = 5 + seededFraction(minute) * 19;
  const secondBlink = 34 + seededFraction(minute + 0.571) * 18;
  const blinkTimes = [firstBlink, secondBlink];
  if (seededFraction(minute + 9.17) > 0.58) blinkTimes.push(firstBlink + 0.34);
  return blinkTimes.some((blinkAt) => Math.abs(second - blinkAt) < 0.15);
}

function mix(start, end, progress) {
  return start + (end - start) * clamp(progress);
}

function corpusPalletPoint(side, toothAngleOffset = 0, radialLift = 0) {
  const angle = ((CORPUS_PALLET_CONTACT_ANGLES[side] + toothAngleOffset) * Math.PI) / 180;
  const radius = CORPUS_PALLET_CONTACT_RADIUS + radialLift;
  return {
    x: CORPUS_CLOCK_CENTER.x + Math.cos(angle) * radius,
    y: CORPUS_CLOCK_CENTER.y + Math.sin(angle) * radius,
  };
}

function corpusPalletToothIndex(point, wheelAngle) {
  const contactAngle =
    (Math.atan2(
      point.y - CORPUS_CLOCK_CENTER.y,
      point.x - CORPUS_CLOCK_CENTER.x,
    ) *
      180) /
    Math.PI;
  return positiveModulo(
    Math.round(
      (contactAngle + 90 - wheelAngle - CORPUS_ESCAPE_TIP_PHASE) /
        CORPUS_ESCAPE_TOOTH_ANGLE,
    ),
    CORPUS_ESCAPE_TOOTH_COUNT,
  );
}

function corpusEscapeToothTip(index, wheelAngle) {
  const angle =
    ((-90 + index * CORPUS_ESCAPE_TOOTH_ANGLE + CORPUS_ESCAPE_TIP_PHASE + wheelAngle) *
      Math.PI) /
    180;
  return polarPoint(CORPUS_ESCAPE_TIP_RADIUS, angle);
}

function corpusBacklashOffset(phase) {
  return -CORPUS_ESCAPE_BACKLASH_DEGREES *
    (1 - smootherstep(phase / CORPUS_ESCAPEMENT_TIMING.releaseEnd));
}

function corpusEscapementState(realSeconds) {
  const wholeSecond = Math.floor(realSeconds);
  const phase = positiveModulo(realSeconds, 1);
  const reduceMotion = shouldReduceMotion();
  const guidePallet = positiveModulo(wholeSecond, 2) === 0 ? "front" : "rear";
  const receivingPallet = guidePallet === "front" ? "rear" : "front";
  let escapementMode = "guide";
  let wheelRelativeAngle = 0;
  let collisionPulse = 0;

  if (reduceMotion) {
    wheelRelativeAngle = Number(phase >= CORPUS_ESCAPEMENT_TIMING.catchStart) *
      CORPUS_ESCAPE_TOOTH_ANGLE;
  } else if (phase < CORPUS_ESCAPEMENT_TIMING.handoffEnd) {
    // The newly landed guide and the old foot overlap for 50 ms around the second boundary.
    escapementMode = "handoff";
    wheelRelativeAngle = corpusBacklashOffset(phase);
    collisionPulse = 1 - smoothstep(phase / CORPUS_ESCAPEMENT_TIMING.handoffEnd);
  } else if (phase < CORPUS_ESCAPEMENT_TIMING.releaseEnd) {
    // The old foot lifts quickly, but the new guide remains seated on the same tooth.
    escapementMode = "release";
    wheelRelativeAngle = corpusBacklashOffset(phase);
  } else if (phase < CORPUS_ESCAPEMENT_TIMING.catchStart) {
    // Spring bias advances the wheel; the guide face follows its tooth along the pitch circle.
    escapementMode = phase < CORPUS_ESCAPEMENT_TIMING.approachStart ? "spring" : "approach";
    const springProgress = clamp(
      (phase - CORPUS_ESCAPEMENT_TIMING.releaseEnd) /
        (CORPUS_ESCAPEMENT_TIMING.catchStart - CORPUS_ESCAPEMENT_TIMING.releaseEnd),
    );
    wheelRelativeAngle = CORPUS_ESCAPE_TOOTH_ANGLE * springProgress * springProgress;
  } else {
    // The next foot catches one tooth ahead and elastically nudges the wheel 0.24° backward.
    escapementMode = "catch";
    const catchProgress = smootherstep(
      (phase - CORPUS_ESCAPEMENT_TIMING.catchStart) /
        (1 - CORPUS_ESCAPEMENT_TIMING.catchStart),
    );
    wheelRelativeAngle =
      CORPUS_ESCAPE_TOOTH_ANGLE - CORPUS_ESCAPE_BACKLASH_DEGREES * catchProgress;
    collisionPulse = catchProgress;
  }

  const guideTarget = corpusPalletPoint(guidePallet, wheelRelativeAngle);
  let receivingTarget;
  if (reduceMotion) {
    receivingTarget = phase >= CORPUS_ESCAPEMENT_TIMING.catchStart
      ? corpusPalletPoint(receivingPallet, wheelRelativeAngle - CORPUS_ESCAPE_TOOTH_ANGLE)
      : corpusPalletPoint(receivingPallet, 0, 18);
  } else if (phase < CORPUS_ESCAPEMENT_TIMING.handoffEnd) {
    receivingTarget = corpusPalletPoint(
      receivingPallet,
      CORPUS_ESCAPE_TOOTH_ANGLE + wheelRelativeAngle,
    );
  } else if (phase < CORPUS_ESCAPEMENT_TIMING.releaseEnd) {
    const releaseProgress = smootherstep(
      (phase - CORPUS_ESCAPEMENT_TIMING.handoffEnd) /
        (CORPUS_ESCAPEMENT_TIMING.releaseEnd - CORPUS_ESCAPEMENT_TIMING.handoffEnd),
    );
    const handoffAngle =
      CORPUS_ESCAPE_TOOTH_ANGLE + corpusBacklashOffset(CORPUS_ESCAPEMENT_TIMING.handoffEnd);
    receivingTarget = corpusPalletPoint(
      receivingPallet,
      mix(handoffAngle, CORPUS_ESCAPE_TOOTH_ANGLE, releaseProgress),
      18 * releaseProgress,
    );
  } else if (phase < CORPUS_ESCAPEMENT_TIMING.approachStart) {
    const flightProgress = smootherstep(
      (phase - CORPUS_ESCAPEMENT_TIMING.releaseEnd) /
        (CORPUS_ESCAPEMENT_TIMING.approachStart - CORPUS_ESCAPEMENT_TIMING.releaseEnd),
    );
    receivingTarget = corpusPalletPoint(
      receivingPallet,
      CORPUS_ESCAPE_TOOTH_ANGLE * (1 - flightProgress),
      18,
    );
  } else if (phase < CORPUS_ESCAPEMENT_TIMING.catchStart) {
    const approachProgress = smootherstep(
      (phase - CORPUS_ESCAPEMENT_TIMING.approachStart) /
        (CORPUS_ESCAPEMENT_TIMING.catchStart - CORPUS_ESCAPEMENT_TIMING.approachStart),
    );
    receivingTarget = corpusPalletPoint(receivingPallet, 0, 18 * (1 - approachProgress));
  } else {
    receivingTarget = corpusPalletPoint(
      receivingPallet,
      wheelRelativeAngle - CORPUS_ESCAPE_TOOTH_ANGLE,
    );
  }

  const palletTargets = {
    [guidePallet]: guideTarget,
    [receivingPallet]: receivingTarget,
  };
  const carrierWave = Math.cos(realSeconds * Math.PI);

  return {
    phase,
    wheelRelativeAngle,
    wheelAngle:
      wholeSecond * CORPUS_ESCAPE_TOOTH_ANGLE +
      wheelRelativeAngle +
      CORPUS_ESCAPE_VISUAL_PHASE_ADJUST,
    wheelStepping: escapementMode !== "guide",
    wheelRebounding:
      escapementMode === "handoff" || escapementMode === "release" || escapementMode === "catch",
    escapementMode,
    guidePallet,
    receivingPallet,
    palletTargets,
    collisionPulse,
    carrierWave: reduceMotion ? 0 : carrierWave,
  };
}

function corpusClockState(date = new Date()) {
  const displayTime = displayTimeParts(date);
  const realSeconds =
    displayTime.hour * 3600 +
    displayTime.minute * 60 +
    displayTime.second +
    displayTime.millisecond / 1000;
  const offset = corpusClockOffsetSeconds(realSeconds);
  const displaySeconds = positiveModulo(realSeconds + offset, 24 * 3600);
  const displayHour24 = Math.floor(displaySeconds / 3600);
  const displayMinute = Math.floor(displaySeconds / 60) % 60;
  const displaySecond = Math.floor(displaySeconds) % 60;
  const escapement = corpusEscapementState(realSeconds);
  const minuteProgress = positiveModulo(displaySeconds, 60);
  const jawAngle =
    minuteProgress < 59
      ? 18 * (1 - smoothstep(minuteProgress / 59))
      : 18 * smoothstep(minuteProgress - 59);
  const quarterProgress = positiveModulo(displaySeconds, 15 * 60);
  let tailAngle = 0;
  if (quarterProgress >= 898.8) {
    tailAngle = -18 * smoothstep((quarterProgress - 898.8) / 1.2);
  } else if (quarterProgress < 4.2) {
    tailAngle = -18 * (1 - smoothstep(quarterProgress / 4.2));
  }
  const clockTime = `${pad2(displayHour24)}:${pad2(displayMinute)}:${pad2(displaySecond)}`;
  return {
    timeZone: DISPLAY_TIME_ZONE,
    displayHour24,
    displayMinute,
    displaySecond,
    hourIndex: (displayHour24 % 12) * 4 + Math.floor(displayMinute / 15),
    minuteIndex: displayMinute,
    secondIndex: displaySecond,
    jawAngle,
    pendulumAngle: escapement.carrierWave * 7.2,
    bodyAngle: escapement.carrierWave * -0.75,
    bodyLift: escapement.carrierWave * 21,
    ...escapement,
    tailAngle,
    blinking: corpusClockBlinking(realSeconds),
    clockTime,
    label: `${clockTime} 北京时间`,
  };
}

function corpusClockTwinSnapshot(value = new Date()) {
  const date = value instanceof Date ? new Date(value.getTime()) : new Date(value);
  if (!Number.isFinite(date.getTime())) throw new TypeError("Invalid Corpus Clock snapshot date");
  const state = corpusClockState(date);
  const pallets = {};
  ["front", "rear"].forEach((side) => {
    const pose = corpusRigidPalletPose(side, state);
    pallets[side] = Object.freeze({
      engaged: pose.contactBound,
      contactBound: pose.contactBound,
      contactPhase: pose.contactPhase,
      rigidity: "fixed-scale-rigid-matrix",
      matrix: Object.freeze({ ...pose.matrix }),
      scale: pose.scale,
      rotation: pose.rotation,
      linkLength: pose.linkLength,
      linkError: pose.linkError,
      bodyCarrierPivot: Object.freeze({ ...pose.bodyCarrierPivot }),
      carrierPivot: Object.freeze({ ...pose.carrierPivot }),
      carrierOffset: pose.carrierOffset,
      sourcePivotMapped: Object.freeze({ ...pose.sourcePivotMapped }),
      pivotError: pose.pivotError,
      contact: Object.freeze({ ...pose.contact }),
      target: Object.freeze({ ...pose.target }),
      targetError: pose.targetError,
      toothIndex: pose.toothIndex,
      coverContactEdge: Object.freeze(pose.coverContactEdge.map((point) => Object.freeze({ ...point }))),
      coverContactEdgeCenter: Object.freeze({ ...pose.coverContactEdgeCenter }),
      actualContactRadius: pose.actualContactRadius,
      contactClearance: pose.contactClearance,
      toothContactEdge: Object.freeze({ ...pose.toothContactEdge }),
      toothTip: Object.freeze({ ...pose.toothTip }),
      contactError: pose.contactError,
      coverEdgeError: pose.coverEdgeError,
    });
  });
  return Object.freeze({
    at: date.toISOString(),
    timeZone: state.timeZone,
    displayHour24: state.displayHour24,
    displayMinute: state.displayMinute,
    displaySecond: state.displaySecond,
    hourIndex: state.hourIndex,
    minuteIndex: state.minuteIndex,
    secondIndex: state.secondIndex,
    clockTime: state.clockTime,
    label: state.label,
    phase: state.phase,
    mode: state.escapementMode,
    guidePallet: state.guidePallet,
    receivingPallet: state.receivingPallet,
    engagedPallets: Object.freeze(
      Object.entries(pallets).filter(([, pallet]) => pallet.contactBound).map(([side]) => side),
    ),
    dualContact: Object.values(pallets).filter((pallet) => pallet.contactBound).length === 2,
    springDriven:
      state.escapementMode === "spring" || state.escapementMode === "approach",
    wheelAngle: state.wheelAngle,
    wheelAngleNormalized: positiveModulo(state.wheelAngle, 360),
    wheelRelativeAngle: state.wheelRelativeAngle,
    body: Object.freeze({
      pivot: Object.freeze({ ...CORPUS_BODY_PIVOT }),
      rotation: state.bodyAngle,
      translateY: state.bodyLift,
    }),
    pallets: Object.freeze(pallets),
  });
}

if (typeof window !== "undefined") {
  Object.defineProperty(window, "__corpusClockTwinSnapshot", {
    value: corpusClockTwinSnapshot,
    writable: false,
    configurable: false,
  });
  document.documentElement.dataset.corpusClockTwinSnapshot = "available";
}

function polarPoint(radius, angle) {
  return {
    x: CORPUS_CLOCK_CENTER.x + Math.cos(angle) * radius,
    y: CORPUS_CLOCK_CENTER.y + Math.sin(angle) * radius,
  };
}

function transformCorpusBodyPoint(point, bodyAngle, bodyLift) {
  const angle = (bodyAngle * Math.PI) / 180;
  const dx = point.x - CORPUS_BODY_PIVOT.x;
  const dy = point.y - CORPUS_BODY_PIVOT.y;
  return {
    x: CORPUS_BODY_PIVOT.x + dx * Math.cos(angle) - dy * Math.sin(angle),
    y: CORPUS_BODY_PIVOT.y + dx * Math.sin(angle) + dy * Math.cos(angle) + bodyLift,
  };
}

function corpusPivotMatrix(sourcePivot, targetPivot, scale, rotation) {
  const cosine = Math.cos(rotation) * scale;
  const sine = Math.sin(rotation) * scale;
  return {
    a: cosine,
    b: sine,
    c: -sine,
    d: cosine,
    e: targetPivot.x - cosine * sourcePivot.x + sine * sourcePivot.y,
    f: targetPivot.y - sine * sourcePivot.x - cosine * sourcePivot.y,
    scale,
    rotation,
  };
}

function transformCorpusMatrixPoint(matrix, point) {
  return {
    x: matrix.a * point.x + matrix.c * point.y + matrix.e,
    y: matrix.b * point.x + matrix.d * point.y + matrix.f,
  };
}

function corpusPointRadius(point) {
  return Math.hypot(
    point.x - CORPUS_CLOCK_CENTER.x,
    point.y - CORPUS_CLOCK_CENTER.y,
  );
}

function corpusPalletContactRadius(side, state) {
  if (state.guidePallet === side) return CORPUS_PALLET_CONTACT_RADIUS;
  if (state.phase < CORPUS_ESCAPEMENT_TIMING.releaseEnd) {
    const progress = smootherstep(
      state.phase / CORPUS_ESCAPEMENT_TIMING.releaseEnd,
    );
    return mix(CORPUS_PALLET_CONTACT_RADIUS, CORPUS_PALLET_AIRBORNE_RADIUS, progress);
  }
  if (state.phase >= CORPUS_ESCAPEMENT_TIMING.approachStart) {
    const progress = smootherstep(
      (state.phase - CORPUS_ESCAPEMENT_TIMING.approachStart) /
        (CORPUS_ESCAPEMENT_TIMING.catchStart - CORPUS_ESCAPEMENT_TIMING.approachStart),
    );
    return mix(CORPUS_PALLET_AIRBORNE_RADIUS, CORPUS_PALLET_CONTACT_RADIUS, progress);
  }
  return CORPUS_PALLET_AIRBORNE_RADIUS;
}

function corpusRigidCircleContact(carrierPivot, linkLength, contactRadius, preferredAngle) {
  const dx = carrierPivot.x - CORPUS_CLOCK_CENTER.x;
  const dy = carrierPivot.y - CORPUS_CLOCK_CENTER.y;
  const centerDistance = Math.max(0.001, Math.hypot(dx, dy));
  const along =
    (contactRadius * contactRadius - linkLength * linkLength + centerDistance * centerDistance) /
    (2 * centerDistance);
  const across = Math.sqrt(Math.max(0, contactRadius * contactRadius - along * along));
  const unit = { x: dx / centerDistance, y: dy / centerDistance };
  const base = {
    x: CORPUS_CLOCK_CENTER.x + unit.x * along,
    y: CORPUS_CLOCK_CENTER.y + unit.y * along,
  };
  const candidates = [
    { x: base.x - unit.y * across, y: base.y + unit.x * across },
    { x: base.x + unit.y * across, y: base.y - unit.x * across },
  ];
  const angularDistance = (point) => {
    const angle = Math.atan2(
      point.y - CORPUS_CLOCK_CENTER.y,
      point.x - CORPUS_CLOCK_CENTER.x,
    );
    return Math.abs(Math.atan2(Math.sin(angle - preferredAngle), Math.cos(angle - preferredAngle)));
  };
  return angularDistance(candidates[0]) <= angularDistance(candidates[1])
    ? candidates[0]
    : candidates[1];
}

function corpusRigidPalletPose(side, state) {
  const rig = CORPUS_PALLET_RIG[side];
  const bodyCarrierPivot = transformCorpusBodyPoint(
    rig.carrierPivot,
    state.bodyAngle,
    state.bodyLift,
  );
  const sourceVector = {
    x: rig.sourceContact.x - rig.sourcePivot.x,
    y: rig.sourceContact.y - rig.sourcePivot.y,
  };
  const linkLength = Math.hypot(sourceVector.x, sourceVector.y) * CORPUS_RIG_UNIFORM_SCALE;
  const contactRadius = corpusPalletContactRadius(side, state);
  const preferredAngle = (CORPUS_PALLET_CONTACT_ANGLES[side] * Math.PI) / 180;
  const contact = corpusRigidCircleContact(
    bodyCarrierPivot,
    linkLength,
    contactRadius,
    preferredAngle,
  );
  // The photographic member is pinned to the body at the real carrier joint.
  // A tooth sweeps across the pallet face while the wheel advances; translating
  // this root to chase one mathematical tip makes the long rear arch look
  // dislocated and creates a false loop seam during catch.
  const carrierPivot = bodyCarrierPivot;
  const sourceAngle = Math.atan2(sourceVector.y, sourceVector.x);
  const contactAngleFromPivot = Math.atan2(
    contact.y - carrierPivot.y,
    contact.x - carrierPivot.x,
  );
  const rotation = Math.atan2(
    Math.sin(contactAngleFromPivot - sourceAngle),
    Math.cos(contactAngleFromPivot - sourceAngle),
  );
  const matrix = corpusPivotMatrix(
    rig.sourcePivot,
    carrierPivot,
    CORPUS_RIG_UNIFORM_SCALE,
    rotation,
  );
  const sourcePivotMapped = transformCorpusMatrixPoint(matrix, rig.sourcePivot);
  const sourceContactMapped = transformCorpusMatrixPoint(matrix, rig.sourceContact);
  const coverContactEdge = rig.sourceContactEdge.map((point) =>
    transformCorpusMatrixPoint(matrix, point));
  const coverContactEdgeCenter = {
    x: (coverContactEdge[0].x + coverContactEdge[1].x) / 2,
    y: (coverContactEdge[0].y + coverContactEdge[1].y) / 2,
  };
  const actualContactRadius = corpusPointRadius(coverContactEdgeCenter);
  const targetRadius = Math.max(0.001, corpusPointRadius(sourceContactMapped));
  const normal = {
    x: (sourceContactMapped.x - CORPUS_CLOCK_CENTER.x) / targetRadius,
    y: (sourceContactMapped.y - CORPUS_CLOCK_CENTER.y) / targetRadius,
  };
  const toothContactEdge = polarPoint(
    CORPUS_ESCAPE_TIP_RADIUS,
    Math.atan2(normal.y, normal.x),
  );
  const toothIndex = corpusPalletToothIndex(sourceContactMapped, state.wheelAngle);
  const toothTip = corpusEscapeToothTip(toothIndex, state.wheelAngle);
  const contactPhase = state.guidePallet === side
    ? "latched"
    : state.phase < CORPUS_ESCAPEMENT_TIMING.releaseEnd
      ? "releasing"
      : state.escapementMode === "catch"
        ? "catching"
        : "airborne";
  const contactClearance = actualContactRadius - CORPUS_ESCAPE_TIP_RADIUS;
  // "Engaged" is a geometric fact, not merely an intent phase.  The incoming
  // pallet stays visually airborne until its photographed contact edge reaches
  // the escape-wheel tip, while the old pallet remains engaged until that same
  // edge has physically cleared it.  This gives the real short hand-over overlap
  // without popping the local tooth lip at an integer-second boundary.
  const contactBound = contactPhase === "latched" ||
    ((contactPhase === "catching" || contactPhase === "releasing") &&
      contactClearance <= 0.02);
  return {
    matrix,
    contactBound,
    contactPhase,
    scale: CORPUS_RIG_UNIFORM_SCALE,
    rotation: (matrix.rotation * 180) / Math.PI,
    linkLength,
    bodyCarrierPivot,
    carrierPivot,
    carrierOffset: Math.hypot(
      carrierPivot.x - bodyCarrierPivot.x,
      carrierPivot.y - bodyCarrierPivot.y,
    ),
    sourcePivotMapped,
    pivotError: Math.hypot(
      sourcePivotMapped.x - carrierPivot.x,
      sourcePivotMapped.y - carrierPivot.y,
    ),
    contact: sourceContactMapped,
    target: contact,
    targetError: Math.hypot(
      sourceContactMapped.x - contact.x,
      sourceContactMapped.y - contact.y,
    ),
    linkError: Math.abs(
      Math.hypot(
        sourceContactMapped.x - carrierPivot.x,
        sourceContactMapped.y - carrierPivot.y,
      ) - linkLength,
    ),
    coverContactEdge,
    coverContactEdgeCenter,
    actualContactRadius,
    contactClearance,
    toothContactEdge,
    toothIndex,
    toothTip,
    contactError: Math.hypot(toothContactEdge.x - toothTip.x, toothContactEdge.y - toothTip.y),
    coverEdgeError: Math.hypot(
      coverContactEdgeCenter.x - toothTip.x,
      coverContactEdgeCenter.y - toothTip.y,
    ),
  };
}

function setCorpusTextureTransform(element, matrix) {
  if (!element) return;
  element.setAttribute(
    "transform",
    `matrix(${matrix.a.toFixed(6)} ${matrix.b.toFixed(6)} ${matrix.c.toFixed(6)} ${matrix.d.toFixed(6)} ${matrix.e.toFixed(6)} ${matrix.f.toFixed(6)})`,
  );
}

function renderCorpusPallet(side, state, suppliedPose = null) {
  const elements = corpusPalletElements[side];
  if (!elements?.root || !elements.photoCover) return;
  const pose = suppliedPose || corpusRigidPalletPose(side, state);
  setCorpusTextureTransform(elements.photoCover, pose.matrix);
  elements.root.classList.toggle("is-engaged", pose.contactBound);
  elements.root.classList.toggle(
    "is-releasing",
    state.escapementMode === "release" && state.receivingPallet === side,
  );
  elements.root.classList.toggle(
    "is-incoming",
    state.receivingPallet === side &&
      (state.escapementMode === "approach" || state.escapementMode === "catch"),
  );
  elements.root.classList.toggle(
    "is-colliding",
    state.receivingPallet === side &&
      (state.escapementMode === "catch" || state.escapementMode === "handoff") &&
      pose.contactBound &&
      state.collisionPulse > 0.08,
  );
  elements.root.dataset.rigVersion = "4";
  elements.root.dataset.rigidity = "fixed-scale-rigid-matrix";
  elements.root.dataset.targetX = pose.target.x.toFixed(3);
  elements.root.dataset.targetY = pose.target.y.toFixed(3);
  elements.root.dataset.targetRadius = Math.hypot(
    pose.target.x - CORPUS_CLOCK_CENTER.x,
    pose.target.y - CORPUS_CLOCK_CENTER.y,
  ).toFixed(3);
  elements.root.dataset.targetAngle = (
    (Math.atan2(
      pose.target.y - CORPUS_CLOCK_CENTER.y,
      pose.target.x - CORPUS_CLOCK_CENTER.x,
    ) * 180) /
    Math.PI
  ).toFixed(3);
  elements.root.dataset.coverContactX = pose.contact.x.toFixed(3);
  elements.root.dataset.coverContactY = pose.contact.y.toFixed(3);
  elements.root.dataset.coverContactRadius = Math.hypot(
    pose.contact.x - CORPUS_CLOCK_CENTER.x,
    pose.contact.y - CORPUS_CLOCK_CENTER.y,
  ).toFixed(3);
  elements.root.dataset.actualContactRadius = pose.actualContactRadius.toFixed(3);
  elements.root.dataset.contactClearance = pose.contactClearance.toFixed(3);
  elements.root.dataset.contactPhase = pose.contactPhase;
  elements.root.dataset.toothIndex = String(pose.toothIndex);
  elements.root.dataset.contactError = pose.contactError.toFixed(3);
  elements.root.dataset.coverEdgeError = pose.coverEdgeError.toFixed(3);
  elements.root.dataset.rigPivotError = pose.pivotError.toFixed(6);
  elements.root.dataset.rigContactError = pose.targetError.toFixed(6);
  elements.root.dataset.rigLinkLength = pose.linkLength.toFixed(6);
  elements.root.dataset.rigLinkError = pose.linkError.toFixed(6);
  elements.root.dataset.carrierOffset = pose.carrierOffset.toFixed(3);
  elements.root.dataset.rigScale = pose.scale.toFixed(6);
  elements.root.dataset.rigRotation = pose.rotation.toFixed(6);
  elements.root.dataset.contactBound = String(pose.contactBound);
  elements.root.dataset.engaged = String(pose.contactBound);
}

function renderCorpusContactLips(state, suppliedPoses = null) {
  if (!corpusContactToothLips) return;
  corpusContactToothLips.dataset.angle = state.wheelAngle.toFixed(3);
  ["front", "rear"].forEach((side) => {
    const group = corpusContactLipElements[side];
    if (!group) return;
    const pose = suppliedPoses?.[side] || corpusRigidPalletPose(side, state);
    group.classList.toggle("is-engaged", pose.contactBound);
    const radius = Math.max(0.001, pose.actualContactRadius);
    const unit = {
      x: (pose.coverContactEdgeCenter.x - CORPUS_CLOCK_CENTER.x) / radius,
      y: (pose.coverContactEdgeCenter.y - CORPUS_CLOCK_CENTER.y) / radius,
    };
    const tangent = { x: -unit.y, y: unit.x };
    const tip = {
      x: CORPUS_CLOCK_CENTER.x + unit.x * CORPUS_ESCAPE_TIP_RADIUS,
      y: CORPUS_CLOCK_CENTER.y + unit.y * CORPUS_ESCAPE_TIP_RADIUS,
    };
    const crown = {
      x: CORPUS_CLOCK_CENTER.x + unit.x * (CORPUS_ESCAPE_TIP_RADIUS + 2.2),
      y: CORPUS_CLOCK_CENTER.y + unit.y * (CORPUS_ESCAPE_TIP_RADIUS + 2.2),
    };
    const capLeft = { x: tip.x - tangent.x * 3.2, y: tip.y - tangent.y * 3.2 };
    const capRight = { x: tip.x + tangent.x * 3.2, y: tip.y + tangent.y * 3.2 };
    const lip = group.firstElementChild;
    lip?.setAttribute(
      "d",
      `M${pose.coverContactEdgeCenter.x.toFixed(2)} ${pose.coverContactEdgeCenter.y.toFixed(2)}L${tip.x.toFixed(2)} ${tip.y.toFixed(2)}M${capLeft.x.toFixed(2)} ${capLeft.y.toFixed(2)}Q${crown.x.toFixed(2)} ${crown.y.toFixed(2)} ${capRight.x.toFixed(2)} ${capRight.y.toFixed(2)}`,
    );
    if (lip) lip.dataset.index = String(pose.toothIndex);
    group.dataset.contactIndex = String(pose.toothIndex);
    group.dataset.actualContactRadius = pose.actualContactRadius.toFixed(3);
    group.dataset.contactClearance = pose.contactClearance.toFixed(3);
  });
}

function createClockSlit(index, total, radius, length) {
  const angle = (index / total) * Math.PI * 2 - Math.PI / 2;
  const innerRadius = radius - length;
  const outerRadius = radius + length;
  const pitch = (Math.PI * 2) / total;
  const innerHalfAngle = pitch * 0.055;
  const outerHalfAngle = pitch * 0.135;
  const points = [
    polarPoint(innerRadius, angle - innerHalfAngle),
    polarPoint(outerRadius, angle - outerHalfAngle),
    polarPoint(outerRadius, angle + outerHalfAngle),
    polarPoint(innerRadius, angle + innerHalfAngle),
  ];
  const path = document.createElementNS(CORPUS_CLOCK_NS, "path");
  path.setAttribute(
    "d",
    `M${points.map((point) => `${point.x.toFixed(2)} ${point.y.toFixed(2)}`).join("L")}Z`,
  );
  path.dataset.index = String(index);
  if (total === 48 && index % 4 === 0) path.classList.add("is-hour-major");
  if (total === 60 && index % 5 === 0) path.classList.add("is-scale-major");
  return path;
}

function createEscapeTooth(index, total = CORPUS_ESCAPE_TOOTH_COUNT) {
  const centerAngle = (index / total) * Math.PI * 2 - Math.PI / 2;
  const halfAngle = ((Math.PI * 2) / total) * 0.35;
  const tipOffset = (CORPUS_ESCAPE_TIP_PHASE * Math.PI) / 180;
  const innerLeft = polarPoint(359, centerAngle - halfAngle);
  const outerLeft = polarPoint(375, centerAngle - halfAngle * 0.44);
  const tip = polarPoint(389, centerAngle + tipOffset);
  const outerRight = polarPoint(374, centerAngle + halfAngle * 0.66);
  const innerRight = polarPoint(359, centerAngle + halfAngle);
  const path = document.createElementNS(CORPUS_CLOCK_NS, "path");
  path.setAttribute(
    "d",
    `M${innerLeft.x.toFixed(2)} ${innerLeft.y.toFixed(2)}L${outerLeft.x.toFixed(2)} ${outerLeft.y.toFixed(2)}Q${tip.x.toFixed(2)} ${tip.y.toFixed(2)} ${outerRight.x.toFixed(2)} ${outerRight.y.toFixed(2)}L${innerRight.x.toFixed(2)} ${innerRight.y.toFixed(2)}Z`,
  );
  path.dataset.index = String(index);
  if ([2, 11, 23, 37, 52].includes(index)) path.classList.add("is-patina-dark");
  if ([7, 31, 46].includes(index)) path.classList.add("is-patina-warm");
  return path;
}

function createRipplePath(index, total = 14) {
  const path = document.createElementNS(CORPUS_CLOCK_NS, "path");
  const baseRadius = 34 + index * (298 / Math.max(1, total - 1));
  const phase = index * 0.73;
  const points = [];
  for (let step = 0; step <= 144; step += 1) {
    const angle = (step / 144) * Math.PI * 2;
    const wobble =
      Math.sin(angle * 3 + phase) * (7 + index * 0.58) +
      Math.sin(angle * 7 - phase * 0.55) * 3.6;
    const point = polarPoint(baseRadius + wobble, angle);
    points.push(`${step === 0 ? "M" : "L"}${point.x.toFixed(1)} ${point.y.toFixed(1)}`);
  }
  path.setAttribute("d", `${points.join("")}Z`);
  return path;
}

function populateCorpusClockRing(group, spec, key) {
  if (!group || group.childElementCount) return;
  const fragment = document.createDocumentFragment();
  for (let index = 0; index < spec.total; index += 1) {
    const length = key === "hour" ? (index % 4 === 0 ? 21 : 11) : key === "minute" ? 14 : 16;
    fragment.append(createClockSlit(index, spec.total, spec.radius, length));
  }
  group.append(fragment);
}

function populateCorpusClockDecoration() {
  if (corpusEscapeTeeth && !corpusEscapeTeeth.childElementCount) {
    const teeth = document.createDocumentFragment();
    for (let index = 0; index < CORPUS_ESCAPE_TOOTH_COUNT; index += 1) teeth.append(createEscapeTooth(index));
    corpusEscapeTeeth.append(teeth);
  }
  if (!corpusRipples || corpusRipples.childElementCount) return;
  const fragment = document.createDocumentFragment();
  for (let index = 0; index < 14; index += 1) fragment.append(createRipplePath(index));
  corpusRipples.append(fragment);
}

function renderCorpusRing(group, activeIndex, spec, now) {
  if (!group) return;
  const active = positiveModulo(activeIndex, spec.total);
  let current = Number(group.dataset.currentIndex);
  if (!Number.isFinite(current)) {
    current = active;
    group.dataset.currentIndex = String(active);
    group.dataset.previousIndex = String(active);
    group.dataset.transitionStart = String(now - spec.transitionMs);
    group.dataset.direction = "1";
  } else if (current !== active) {
    const forwardDistance = positiveModulo(active - current, spec.total);
    const direction = forwardDistance <= spec.total / 2 ? 1 : -1;
    group.dataset.previousIndex = String(current);
    group.dataset.currentIndex = String(active);
    group.dataset.transitionStart = String(now);
    group.dataset.direction = String(direction);
    current = active;
  }

  const previous = Number(group.dataset.previousIndex);
  const transitionStart = Number(group.dataset.transitionStart);
  const direction = Number(group.dataset.direction) || 1;
  const transitionProgress = clamp((now - transitionStart) / spec.transitionMs);
  let runner = active;
  if (transitionProgress < 1) {
    const forwardDistance = positiveModulo(active - previous, spec.total);
    const signedDelta = direction > 0 ? forwardDistance : -positiveModulo(previous - active, spec.total);
    const fullLap = direction * spec.total + signedDelta;
    runner = positiveModulo(Math.round(previous + fullLap * smoothstep(transitionProgress)), spec.total);
  }

  const renderKey = `${runner}:${direction}:${transitionProgress < 1}`;
  if (group.dataset.renderKey === renderKey) return;
  group.dataset.renderKey = renderKey;
  [...group.children].forEach((marker) => {
    const index = Number(marker.dataset.index);
    const distance =
      direction > 0
        ? positiveModulo(runner - index, spec.total)
        : positiveModulo(index - runner, spec.total);
    marker.classList.toggle("is-active", index === runner);
    for (let trail = 1; trail <= 5; trail += 1) {
      marker.classList.toggle(`is-trail-${trail}`, trail <= spec.trail && distance === trail);
    }
  });
}

function initializeCorpusClock() {
  populateCorpusClockDecoration();
  populateCorpusClockRing(corpusHourRing, CORPUS_CLOCK_RING_SPECS.hour, "hour");
  populateCorpusClockRing(corpusMinuteRing, CORPUS_CLOCK_RING_SPECS.minute, "minute");
  populateCorpusClockRing(corpusSecondRing, CORPUS_CLOCK_RING_SPECS.second, "second");
  if (corpusChronophage) {
    corpusChronophage.style.transformOrigin = `${CORPUS_BODY_PIVOT.x}px ${CORPUS_BODY_PIVOT.y}px`;
  }
  const qaClockScale = Number(new URLSearchParams(window.location.search).get("clockScale"));
  if (Number.isFinite(qaClockScale) && qaClockScale >= 1 && qaClockScale <= 4) {
    corpusClock?.style.setProperty("--clock-size", `${160 * qaClockScale}px`);
  }
  if (Number.isFinite(corpusClockQaSeconds)) {
    corpusClock.dataset.qaFixedSecond = String(corpusClockQaSeconds);
  }
  if (Number.isFinite(headerClockQaDateMs)) {
    corpusClock.dataset.qaFixedDate = new Date(headerClockQaDateMs).toISOString();
  }
  updateCorpusClock(performance.now());
}

function corpusClockRenderDate() {
  if (Number.isFinite(headerClockQaDateMs)) return new Date(headerClockQaDateMs);
  if (!Number.isFinite(corpusClockQaSeconds)) return new Date();
  const display = displayTimeParts(new Date());
  const displayMidnight =
    Date.UTC(display.year, display.month, display.day) - DISPLAY_UTC_OFFSET_MS;
  return new Date(displayMidnight + corpusClockQaSeconds * 1000);
}

function updateCorpusClock(now = performance.now()) {
  if (!corpusClock) return;
  const state = corpusClockState(corpusClockRenderDate());
  const palletPoses = {
    front: corpusRigidPalletPose("front", state),
    rear: corpusRigidPalletPose("rear", state),
  };
  const actualEngagedPallets = ["front", "rear"].filter(
    (side) => palletPoses[side].contactBound,
  );
  renderCorpusRing(corpusHourRing, state.hourIndex, CORPUS_CLOCK_RING_SPECS.hour, now);
  renderCorpusRing(corpusMinuteRing, state.minuteIndex, CORPUS_CLOCK_RING_SPECS.minute, now);
  renderCorpusRing(corpusSecondRing, state.secondIndex, CORPUS_CLOCK_RING_SPECS.second, now);
  corpusClock.classList.toggle("is-blinking", state.blinking);
  corpusClock.classList.toggle("is-wheel-stepping", state.wheelStepping);
  corpusClock.classList.toggle("is-wheel-rebounding", state.wheelRebounding);
  corpusClock.classList.toggle("is-front-pallet-engaged", palletPoses.front.contactBound);
  corpusClock.classList.toggle("is-rear-pallet-engaged", palletPoses.rear.contactBound);
  corpusClock.dataset.escapementState = state.escapementMode;
  corpusClock.dataset.guidePallet = state.guidePallet;
  corpusClock.dataset.receivingPallet = state.receivingPallet;
  corpusClock.dataset.engagedPallets = actualEngagedPallets.join(",");
  corpusClock.dataset.dualContact = String(actualEngagedPallets.length === 2);
  corpusClock.dataset.reducedMotion = String(shouldReduceMotion());
  corpusClock.style.setProperty("--cc-body-angle", `${state.bodyAngle.toFixed(3)}deg`);
  corpusClock.style.setProperty("--cc-body-lift", `${state.bodyLift.toFixed(3)}px`);
  corpusClock.style.setProperty("--cc-wheel-angle", `${state.wheelAngle.toFixed(3)}deg`);
  const normalizedWheelAngle = positiveModulo(state.wheelAngle, 360);
  const wholeWheelStep = Math.floor(state.wheelAngle / CORPUS_ESCAPE_TOOTH_ANGLE);
  if (corpusEscapeWheel) {
    corpusEscapeWheel.dataset.angle = state.wheelAngle.toFixed(3);
    corpusEscapeWheel.dataset.angleNormalized = normalizedWheelAngle.toFixed(3);
    corpusEscapeWheel.dataset.step = String(wholeWheelStep);
  }
  corpusClock.style.setProperty("--cc-jaw-angle", `${state.jawAngle.toFixed(3)}deg`);
  corpusClock.style.setProperty("--cc-tail-angle", `${state.tailAngle.toFixed(3)}deg`);
  corpusClock.style.setProperty("--cc-pendulum-angle", `${state.pendulumAngle.toFixed(3)}deg`);
  renderCorpusPallet("front", state, palletPoses.front);
  renderCorpusPallet("rear", state, palletPoses.rear);
  renderCorpusContactLips(state, palletPoses);
  if (corpusEscapeTeeth) {
    const previousContactIndices = (corpusEscapeTeeth.dataset.contactIndices || "")
      .split(",")
      .filter(Boolean)
      .map(Number);
    previousContactIndices.forEach((index) => {
      corpusEscapeTeeth.children[index]?.classList.remove("is-contact");
    });
    const contactIndices = [...new Set(actualEngagedPallets.map(
      (side) => palletPoses[side].toothIndex,
    ))];
    contactIndices.forEach((index) => {
      corpusEscapeTeeth.children[index]?.classList.add("is-contact");
    });
    corpusEscapeTeeth.dataset.contactIndices = contactIndices.join(",");
    delete corpusEscapeTeeth.dataset.contactIndex;
  }
  if (corpusClockTime) {
    corpusClockTime.textContent = state.label;
    corpusClockTime.dateTime = state.clockTime;
  }
  corpusClock.dataset.timeZone = state.timeZone;
  if (corpusClock.dataset.label !== state.label) {
    corpusClock.dataset.label = state.label;
    if (activeHeaderClockId === "corpus") refreshHeaderClockTitle();
  }
}

const HEADER_CLOCK_RUNTIMES = {
  corpus: {
    initialize: initializeCorpusClock,
    activate: ({ now }) => updateCorpusClock(now),
    frame: ({ now }) => updateCorpusClock(now),
    resume: ({ now }) => updateCorpusClock(now),
  },
  "big-ben": {
    initialize: initializeBigBenClock,
    activate: ({ date, switching }) => {
      if (switching) syncActiveBigBenClock(date);
      else updateBigBenClock(date, true);
    },
    frame: ({ date }) => updateBigBenClock(date),
    resume: ({ date }) => syncActiveBigBenClock(date),
  },
  "prague-orloj": {
    initialize: initializePragueOrlojClock,
    activate: ({ date, switching }) => {
      if (switching) syncActivePragueOrlojClock(date);
      else updatePragueOrlojClock(date, true);
    },
    frame: ({ date }) => updatePragueOrlojClock(date),
    resume: ({ date }) => syncActivePragueOrlojClock(date),
  },
  "bern-zytglogge": {
    initialize: initializeBernZytgloggeClock,
    activate: ({ date, switching }) => {
      if (switching) syncActiveBernZytgloggeClock(date);
      else updateBernZytgloggeClock(date, true);
    },
    frame: ({ date }) => updateBernZytgloggeClock(date),
    resume: ({ date }) => syncActiveBernZytgloggeClock(date),
  },
};

function runCorpusClockFrame(now) {
  HEADER_CLOCK_RUNTIMES[activeHeaderClockId]?.frame({
    now,
    date: corpusClockRenderDate(),
  });
  corpusClockAnimationFrame = requestAnimationFrame(runCorpusClockFrame);
}

function startCorpusClockAnimation() {
  if (!corpusClock || corpusClockAnimationFrame !== null || document.visibilityState === "hidden") return;
  corpusClockAnimationFrame = requestAnimationFrame(runCorpusClockFrame);
}

function stopCorpusClockAnimation() {
  if (corpusClockAnimationFrame === null) return;
  cancelAnimationFrame(corpusClockAnimationFrame);
  corpusClockAnimationFrame = null;
}

function feishuTimeLabel(timestamp = Date.now()) {
  const parts = displayTimeParts(new Date(timestamp));
  return `${parts.year}-${pad2(parts.month + 1)}-${pad2(parts.day)} ${pad2(parts.hour)}:${pad2(parts.minute)} 北京时间`;
}

async function feishuRequest(path, payload) {
  const response = await fetch(path, {
    method: "POST",
    cache: "no-store",
    headers: {
      "Content-Type": "application/json",
      "X-Lumen-Request": "1",
    },
    body: JSON.stringify(payload),
  });
  let data = {};
  try {
    data = await response.json();
  } catch {
    // Preserve the HTTP error below when a proxy returns a non-JSON body.
  }
  if (!response.ok || data.available === false) {
    throw new Error(data.error || `请求失败（${response.status}）`);
  }
  return data;
}

function feishuEventsFromForm() {
  return Object.fromEntries(
    [...feishuForm.querySelectorAll('input[name="feishuEvent"]')]
      .map((input) => [input.value, input.checked]),
  );
}

function applyFeishuStatus(status, { updateForm = true } = {}) {
  feishuStatusState = status;
  const enabled = status?.enabled === true;
  const configured = status?.configured === true;
  const hasError = Boolean(status?.lastError);
  const pending = Number(status?.pending || 0);
  const active = enabled && configured && !hasError;
  feishuQuickControl?.classList.toggle("is-active", active);
  feishuQuickControl?.classList.toggle("has-error", hasError);
  if (feishuQuickEnabled) {
    feishuQuickEnabled.checked = enabled;
    const quickLabel = !configured ? "配置飞书提醒" : enabled ? "关闭飞书提醒" : "开启飞书提醒";
    feishuQuickEnabled.setAttribute("aria-label", quickLabel);
    feishuQuickEnabled.closest("label")?.setAttribute("title", quickLabel);
  }
  feishuSettingsButton?.setAttribute(
    "title",
    hasError ? `飞书发送异常：${status.lastError}` : active ? "飞书提醒已开启，点击查看设置" : "打开飞书提醒设置",
  );
  if (!feishuDialog) return;
  feishuConnection?.classList.toggle("is-connected", enabled && configured && !hasError);
  feishuConnection?.classList.toggle("has-error", hasError);
  if (hasError) {
    feishuConnectionTitle.textContent = "最近一次发送失败";
    feishuConnectionDetail.textContent = status.lastError;
  } else if (enabled && configured) {
    feishuConnectionTitle.textContent = "飞书提醒正在运行";
    feishuConnectionDetail.textContent = pending ? `${pending} 条消息正在等待发送` : "队列正常，没有待发送消息";
  } else if (configured) {
    feishuConnectionTitle.textContent = "机器人已配置";
    feishuConnectionDetail.textContent = "打开启用开关并保存后开始通知";
  } else {
    feishuConnectionTitle.textContent = "尚未连接飞书机器人";
    feishuConnectionDetail.textContent = "填写 Webhook 和签名密钥后先发送测试消息";
  }
  if (!updateForm) return;
  feishuEnabled.checked = enabled;
  Object.entries(status?.events || {}).forEach(([eventType, checked]) => {
    const input = feishuForm.querySelector(`input[name="feishuEvent"][value="${eventType}"]`);
    if (input) input.checked = checked === true;
  });
  feishuWebhook.value = "";
  feishuSecret.value = "";
  feishuWebhook.placeholder = configured ? "Webhook 已安全保存，留空不修改" : "https://open.feishu.cn/open-apis/bot/v2/hook/…";
  feishuSecret.placeholder = status?.hasSecret ? "签名密钥已安全保存，留空不修改" : "机器人安全设置中的签名密钥";
}

async function loadFeishuStatus({ updateForm = true } = {}) {
  try {
    const response = await fetch("/api/feishu/status", { cache: "no-store" });
    const data = await response.json();
    if (!response.ok || data.available === false) throw new Error(data.error || "无法读取飞书配置");
    applyFeishuStatus(data, { updateForm });
    return data;
  } catch (error) {
    feishuQuickControl?.classList.add("has-error");
    if (feishuDialog?.open) {
      feishuConnectionTitle.textContent = "本地通知服务不可用";
      feishuConnectionDetail.textContent = error.message;
    }
    return null;
  }
}

async function openFeishuDialog() {
  if (!feishuDialog) return;
  feishuFormStatus.textContent = "";
  feishuFormStatus.className = "feishu-form-status";
  if (!feishuDialog.open) feishuDialog.showModal();
  await loadFeishuStatus();
  feishuWebhook.focus();
}

function closeFeishuDialog() {
  if (feishuSettingsBusy || !feishuDialog?.open) return;
  feishuDialog.close();
  feishuSettingsButton?.focus();
}

function setFeishuBusy(busy) {
  feishuSettingsBusy = busy;
  testFeishuButton.disabled = busy;
  saveFeishuButton.disabled = busy;
  feishuEnabled.disabled = busy;
  if (feishuQuickEnabled) feishuQuickEnabled.disabled = busy;
  feishuQuickControl?.classList.toggle("is-switching", busy);
}

async function toggleFeishuQuickNotifications(event) {
  if (feishuSettingsBusy) return;
  const desiredEnabled = event.currentTarget.checked;
  if (!feishuStatusState?.configured) {
    event.currentTarget.checked = false;
    openFeishuDialog();
    return;
  }
  setFeishuBusy(true);
  try {
    const status = await feishuRequest("/api/feishu/settings", { enabled: desiredEnabled });
    applyFeishuStatus(status);
  } catch (error) {
    event.currentTarget.checked = feishuStatusState?.enabled === true;
    feishuQuickControl?.classList.add("has-error");
    feishuSettingsButton?.setAttribute("title", `切换飞书提醒失败：${error.message}`);
  } finally {
    setFeishuBusy(false);
  }
}

function feishuSettingsPayload(enabled = feishuEnabled.checked) {
  return {
    enabled,
    webhook: feishuWebhook.value.trim(),
    secret: feishuSecret.value.trim(),
    events: feishuEventsFromForm(),
  };
}

async function saveFeishuSettings(event) {
  event?.preventDefault();
  if (feishuSettingsBusy) return null;
  setFeishuBusy(true);
  feishuFormStatus.className = "feishu-form-status";
  feishuFormStatus.textContent = "正在保存到本机…";
  try {
    const status = await feishuRequest("/api/feishu/settings", feishuSettingsPayload());
    applyFeishuStatus(status);
    feishuFormStatus.classList.add("is-success");
    feishuFormStatus.textContent = status.enabled ? "已保存，飞书提醒正在运行" : "配置已保存，飞书提醒当前关闭";
    return status;
  } catch (error) {
    feishuFormStatus.classList.add("is-error");
    feishuFormStatus.textContent = error.message;
    return null;
  } finally {
    setFeishuBusy(false);
  }
}

async function testFeishuConnection() {
  if (feishuSettingsBusy) return;
  setFeishuBusy(true);
  feishuFormStatus.className = "feishu-form-status";
  feishuFormStatus.textContent = "正在保存连接信息并发送测试消息…";
  try {
    const status = await feishuRequest(
      "/api/feishu/settings",
      feishuSettingsPayload(feishuStatusState?.enabled === true),
    );
    applyFeishuStatus(status);
    const result = await feishuRequest("/api/feishu/test", {});
    feishuFormStatus.classList.add("is-success");
    feishuFormStatus.textContent = result.message || "测试消息已发送，请检查手机飞书";
  } catch (error) {
    feishuFormStatus.classList.add("is-error");
    feishuFormStatus.textContent = error.message;
  } finally {
    setFeishuBusy(false);
    loadFeishuStatus({ updateForm: false });
  }
}

function enqueueFeishuEvent(eventType, eventId, data = {}) {
  if (!eventId) return;
  feishuRequest("/api/feishu/events", {
    eventType,
    eventId,
    data: { ...data, occurredAtLabel: data.occurredAtLabel || feishuTimeLabel() },
  })
    .then(() => loadFeishuStatus({ updateForm: false }))
    .catch(() => loadFeishuStatus({ updateForm: false }));
}

function workCountForCard(card) {
  const count = workSession.countsByCardId[card.id];
  return Number.isFinite(count) ? count : 0;
}

function totalWorkCount() {
  return cards
    .filter((card) => card.codexThreadId)
    .reduce((total, card) => total + workCountForCard(card), 0);
}

function workSessionDurationMs(now = Date.now()) {
  if (!Number.isFinite(workSession.startedAt)) return 0;
  const stoppedAt = workSession.active
    ? now
    : Number.isFinite(workSession.endedAt)
      ? workSession.endedAt
      : workSession.startedAt;
  return Math.max(0, stoppedAt - workSession.startedAt);
}

function formatWorkDuration(durationMs) {
  const totalSeconds = Math.max(0, Math.floor(durationMs / 1000));
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor(totalSeconds / 60) % 60;
  const seconds = totalSeconds % 60;
  return [hours, minutes, seconds].map((part) => String(part).padStart(2, "0")).join(":");
}

function updateWorkDuration(now = Date.now()) {
  const duration = document.querySelector("#workDuration");
  if (!duration) return;
  const durationMs = workSessionDurationMs(now);
  const nextText = formatWorkDuration(durationMs);
  if (duration.textContent !== nextText) duration.textContent = nextText;
  duration.dateTime = `PT${Math.floor(durationMs / 1000)}S`;
  if (workReflectionDialog?.open) updateWorkReflectionSummary(now);
}

function workCompletionBreakdown() {
  return cards
    .filter((card) => card.codexThreadId && workCountForCard(card) > 0)
    .map((card) => ({
      cardId: card.id,
      title: card.title || card.codexThreadName || "Codex 对话",
      count: workCountForCard(card),
    }));
}

function workConversationChoices() {
  return workHistoryCore.groupConversationChoices(cards, workSession.countsByCardId);
}

function syncWorkReflectionThreadSelection() {
  const inputs = [...workReflectionThreads.querySelectorAll("[data-reflection-thread]")];
  const selected = inputs.filter((input) => input.checked).length;
  workReflectionThreadCount.textContent = `${selected} / ${inputs.length} 个对话`;
  toggleReflectionThreads.disabled = inputs.length === 0;
  toggleReflectionThreads.textContent = inputs.length && selected === inputs.length ? "清空" : "全选";
}

function renderWorkReflectionThreads() {
  workReflectionConversationOptions = workConversationChoices();
  if (!workReflectionConversationOptions.length) {
    workReflectionThreads.innerHTML = '<div class="reflection-thread-empty">暂无关联的 Codex 对话，本次仍可正常保存班次。</div>';
    syncWorkReflectionThreadSelection();
    return;
  }
  const hasCompleted = workReflectionConversationOptions.some((conversation) => conversation.count > 0);
  workReflectionThreads.innerHTML = workReflectionConversationOptions.map((conversation) => {
    const checked = !hasCompleted || conversation.count > 0 ? "checked" : "";
    return `
      <label class="reflection-thread-option">
        <input data-reflection-thread type="checkbox" value="${escapeHtml(conversationCodexThreadRef(conversation))}" ${checked} />
        <span class="reflection-thread-check" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="m6 12 4 4 8-9" /></svg></span>
        <span class="reflection-thread-copy">
          <strong>${escapeHtml(conversation.title)}</strong>
          <small>${escapeHtml(conversation.threadName)} · 本班 ${conversation.count} 次</small>
        </span>
      </label>`;
  }).join("");
  syncWorkReflectionThreadSelection();
}

function selectedWorkConversations() {
  const selectedIds = new Set(
    [...workReflectionThreads.querySelectorAll("[data-reflection-thread]:checked")].map((input) => input.value),
  );
  return workReflectionConversationOptions.filter((conversation) => selectedIds.has(conversationCodexThreadRef(conversation)));
}

function updateWorkReflectionSummary(now = Date.now()) {
  if (!workReflectionDialog) return;
  const previewStartedAt = Number(workReflectionDialog.dataset.previewStartedAt);
  const startedAt = workReflectionPreview && Number.isFinite(previewStartedAt)
    ? previewStartedAt
    : workSession.startedAt;
  const durationMs = Number.isFinite(startedAt) ? Math.max(0, now - startedAt) : 0;
  const startedParts = Number.isFinite(startedAt) ? displayTimeParts(new Date(startedAt)) : null;
  reflectionStartedAt.textContent = startedParts ? `${pad2(startedParts.hour)}:${pad2(startedParts.minute)}` : "--:--";
  reflectionDuration.textContent = formatWorkDuration(durationMs);
  reflectionCount.textContent = workReflectionPreview ? "12" : String(totalWorkCount());
}

function openWorkReflectionDialog({ preview = false } = {}) {
  reflectionStartedFor = workSession.startedAt;
  if (!workReflectionDialog || (!workSession.active && !preview)) return;
  workReflectionPreview = preview;
  workReflectionReturnFocus = document.activeElement;
  workReflectionForm.reset();
  workReflectionStatus.textContent = "";
  workReflectionDialog.dataset.preview = String(preview);
  if (preview) {
    workReflectionDialog.dataset.previewStartedAt = String(Date.now() - (7 * UNIT_MS.hour + 42 * UNIT_MS.minute));
  } else {
    delete workReflectionDialog.dataset.previewStartedAt;
  }
  renderWorkReflectionThreads();
  updateWorkReflectionSummary();
  workReflectionDialog.showModal();
  requestAnimationFrame(() => workReflectionNote.focus());
}

async function closeWorkReflectionDialog() {
  if (!workReflectionDialog?.open || workReflectionDialog.dataset.closing === "true") return;
  workReflectionDialog.dataset.closing = "true";
  if (!shouldReduceMotion() && typeof workReflectionDialog.animate === "function") {
    try {
      await workReflectionDialog.animate(
        [
          { opacity: 1, transform: "translateY(0) scale(1)" },
          { opacity: 0, transform: "translateY(8px) scale(0.99)" },
        ],
        { duration: 150, easing: "ease-in", fill: "forwards" },
      ).finished;
    } catch {
      // The dialog can be closed by the browser before the exit animation finishes.
    }
  }
  delete workReflectionDialog.dataset.closing;
  workReflectionDialog.close();
}

function renderWorkSession() {
  const total = totalWorkCount();
  const stateText = workSession.active ? "上班中" : workSession.startedAt ? "已下班" : "未上班";
  const durationMs = workSessionDurationMs();
  workSummary.innerHTML = `
    <span>${stateText}</span>
    <strong>${total}</strong>
    <small>次完成</small>
    <span class="work-duration-block">
      <small>时长</small>
      <time class="work-duration" id="workDuration" datetime="PT${Math.floor(durationMs / 1000)}S" aria-live="off">${formatWorkDuration(durationMs)}</time>
    </span>
  `;
  workToggleButton.textContent = workSession.active ? "下班" : "上班";
  workToggleButton.disabled = workSessionBusy;
  workToggleButton.classList.toggle("is-active", workSession.active);
  workToggleButton.setAttribute("aria-pressed", String(workSession.active));
  document.body.classList.toggle("is-work-active", workSession.active);
  document.body.classList.toggle("is-work-paused", !workSession.active);
}

function hasWorkBaseline(card) {
  return Object.prototype.hasOwnProperty.call(workSession.countedTurnIdsByCardId, card.id);
}

function baselineWorkCard(card, resetCount = false) {
  if (!card.codexThreadId) return;
  if (resetCount || !Object.prototype.hasOwnProperty.call(workSession.countsByCardId, card.id)) {
    workSession.countsByCardId[card.id] = 0;
  }
  workSession.countedTurnIdsByCardId[card.id] = card.codexLatestTurnId || card.codexLastSeenTurnId || null;
}

function ensureActiveWorkBaselines() {
  if (!workSession.active) return;
  let changed = false;
  cards.forEach((card) => {
    if (!card.codexThreadId || hasWorkBaseline(card)) return;
    baselineWorkCard(card);
    changed = true;
  });
  if (changed) saveWorkSession();
}

function recordWorkCompletion(card, turnId) {
  if (!workSession.active || !turnId || !card.codexThreadId) return false;
  if (!hasWorkBaseline(card)) {
    baselineWorkCard(card);
    return true;
  }
  if (workSession.countedTurnIdsByCardId[card.id] === turnId) return false;
  workSession.countedTurnIdsByCardId[card.id] = turnId;
  workSession.countsByCardId[card.id] = workCountForCard(card) + 1;
  return true;
}

function getCardState(card, now = Date.now()) {
  if (!workSession.active) return card.codexThreadId ? "codex-paused" : "paused";
  if (card.codexThreadId) return card.codexDue ? "due" : "codex";
  if (!card.started) return "idle";
  if (card.nextAt <= now) return "due";
  return "running";
}

function isCodexActiveStatus(status) {
  return new Set(["active", "inProgress", "running", "working"]).has(status);
}

function widgetSnapshotProjection(now = Date.now()) {
  const quoteCache = loadQuoteCache();
  const weatherCache = loadWeatherCache();
  const todayWeather = weatherCache?.days?.[0];
  const currentWeather = weatherCache?.current;
  const currentTemperature = Number(currentWeather?.temperature_2m);
  const reminders = cardOrderCore
    .sortCards(cards, { workActive: workSession.active, now })
    .slice(0, 4)
    .map((card) => ({
      title: card.title,
      tag: card.tag || (card.codexThreadId ? "Codex" : "提醒"),
      state: cardOrderCore.displayState(card, { workActive: workSession.active, now }),
      dueAt: Number.isFinite(card.nextAt) ? card.nextAt : null,
    }));
  return {
    sourceId: widgetSourceId(),
    claimSource: new URLSearchParams(window.location.search).get("widgetSource") === "claim",
    work: {
      active: workSession.active,
      startedAt: workSession.startedAt,
      endedAt: workSession.endedAt,
      durationMs: workSessionDurationMs(now),
      completionCount: totalWorkCount(),
    },
    reminders,
    quote: quoteCache.quote
      ? { text: quoteCache.quote.text, source: quoteCache.quote.source || "一言" }
      : null,
    weather: todayWeather
      ? {
          location: weatherCache.location?.label || "天气",
          type: weatherCodeText(Number(currentWeather?.weather_code ?? todayWeather.code)),
          current: Number.isFinite(currentTemperature)
            ? currentTemperature
            : (Number(todayWeather.min) + Number(todayWeather.max)) / 2,
          min: todayWeather.min,
          max: todayWeather.max,
          rain: todayWeather.rain,
        }
      : null,
  };
}

function queueWidgetSnapshotSync(delay = 180) {
  window.clearTimeout(widgetSnapshotTimer);
  widgetSnapshotTimer = window.setTimeout(syncWidgetSnapshot, delay);
}

async function syncWidgetSnapshot() {
  if (widgetSnapshotSyncing) {
    widgetSnapshotPending = true;
    return;
  }
  widgetSnapshotSyncing = true;
  widgetSnapshotPending = false;
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), 5000);
  try {
    await fetch("/api/widget/snapshot", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Lumen-Request": "1",
      },
      body: JSON.stringify(widgetSnapshotProjection()),
      cache: "no-store",
      signal: controller.signal,
    });
  } catch {
    // Static-file mode and a temporarily sleeping local service are both harmless.
  } finally {
    window.clearTimeout(timeout);
    widgetSnapshotSyncing = false;
    if (widgetSnapshotPending) queueWidgetSnapshotSync();
  }
}

function startTimer(card, now = Date.now()) {
  return {
    ...card,
    started: true,
    nextAt: now + card.intervalMs,
  };
}

const REASONING_EFFORT_COLORS = {
  low: "#5aa9ff",
  minimal: "#5aa9ff",
  medium: "#46d5d1",
  high: "#a6d957",
  xhigh: "#ff9a4d",
  max: "#ef5b5b",
  ultra: "#ef5b5b",
};

function graphState(card, now = Date.now()) {
  const state = getCardState(card, now);
  if (state === "due") return "due";
  if (card.codexThreadId && (isCodexActiveStatus(card.codexStatus) || (card.codexPhase && card.codexPhase !== "idle"))) return "processing";
  if (state === "running") return "countdown";
  if (card.codexThreadId) return "attention";
  if (state === "paused" || state === "codex-paused") return "paused";
  return "idle";
}

function isGraphThreadActive(card) {
  return Boolean(card.codexThreadId && (
    isCodexActiveStatus(card.codexStatus)
    || (card.codexStatus !== "unavailable" && card.codexPhase && card.codexPhase !== "idle")
  ));
}

function reasoningEffortColor(effort) {
  return REASONING_EFFORT_COLORS[String(effort || "").toLowerCase()] || "#89939c";
}

function reasoningEffortLabel(effort) {
  const normalized = String(effort || "").trim().toLowerCase();
  const labels = {
    minimal: "最低",
    low: "低",
    medium: "中",
    high: "高",
    xhigh: "很高",
    max: "最高",
    ultra: "极高",
  };
  return labels[normalized] || (normalized ? normalized.toUpperCase() : "");
}

function modelDisplayLabel(model) {
  if (!model) return "模型信息暂不可用";
  return model.replace(/^gpt-/i, "GPT-");
}

function graphPhaseLabel(card, state) {
  if (card.codexPhaseLabel) return card.codexPhaseLabel;
  if (state === "due") return "新回复";
  if (state === "processing") return "处理中";
  if (state === "countdown") return "倒计时";
  if (state === "paused") return "已暂停";
  return "保持关注";
}

function formatElapsedSince(timestamp, now = Date.now()) {
  const value = Number(timestamp);
  if (!Number.isFinite(value) || value <= 0) return "";
  const elapsed = Math.max(0, Math.floor((now - (value > 10_000_000_000 ? value : value * 1000)) / 1000));
  if (elapsed < 60) return `${elapsed}秒`;
  const minutes = Math.floor(elapsed / 60);
  if (minutes < 60) return `${minutes}分${elapsed % 60}秒`;
  return `${Math.floor(minutes / 60)}小时${String(minutes % 60).padStart(2, "0")}分`;
}

function shortCwd(cwd) {
  const value = String(cwd || "").replace(/\\/g, "/");
  return value ? value.split("/").filter(Boolean).slice(-2).join("/") : "";
}

function bubbleMarkup(card, now = Date.now(), modelKeys = new Map()) {
  const state = graphState(card, now);
  const linked = Boolean(card.codexThreadId);
  const due = state === "due";
  const modelKey = linked ? (card.codexModel || "unknown") : "local-reminder";
  const modelNodeKey = modelKeys.get(modelKey) || "model-unknown";
  const phase = graphPhaseLabel(card, state);
  const phaseStart = card.codexActivityStartedAt || (due ? card.codexLatestCompletedAt : null);
  const runtime = formatElapsedSince(phaseStart, now);
  const cardActionable = workSession.active && (due || state === "idle");
  const hostLabel = card.codexHost && card.codexHost !== "local" ? "SSH" : "本机";
  const effort = isGraphThreadActive(card) ? reasoningEffortLabel(card.codexReasoningEffort) : "";
  const statusText = linked
    ? due ? "有新回复" : state === "processing" ? "处理中" : "保持关注"
    : state === "paused" ? "提醒已暂停" : state === "countdown" ? formatCountdown(card.nextAt) : "未开始";
  return `
    <article class="thread-bubble is-${state}" data-card-id="${escapeHtml(card.id)}" data-graph-model="${escapeHtml(modelNodeKey)}" data-phase-label="${escapeHtml(phase)}" data-reasoning-effort="${escapeHtml(effort)}" tabindex="${cardActionable ? "0" : "-1"}" aria-label="${escapeHtml(card.title)}，${escapeHtml(statusText)}${effort ? `，推理${escapeHtml(effort)}` : ""}">
      <div class="thread-bubble-orbit" aria-hidden="true"></div>
      <div class="thread-bubble-head">
        <span class="bubble-source">${linked ? hostLabel : "提醒"}</span>
        <button class="edit-button" type="button" data-edit-card="${escapeHtml(card.id)}" aria-label="编辑 ${escapeHtml(card.title)}">
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 20h9"></path><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L8 18l-4 1 1-4Z"></path></svg>
        </button>
      </div>
      <h2>${escapeHtml(card.title)}</h2>
      <strong class="thread-bubble-status">${escapeHtml(statusText)}</strong>
      ${linked ? "" : `<div class="thread-bubble-meta"><span>${escapeHtml(card.tag || "提醒")}</span></div>`}
      <span class="thread-bubble-count">${linked ? `本班 ${workCountForCard(card)} 次` : state === "paused" ? "已暂停" : card.nextAt ? formatDateTime(card.nextAt) : "待开始"}</span>
      ${due ? `<span class="thread-bubble-action">点击标记已读</span>` : ""}
      <span class="thread-bubble-runtime" data-bubble-runtime="${escapeHtml(card.id)}" data-phase-start="${phaseStart || ""}">${runtime}</span>
    </article>`;
}

function graphMarkup(sorted, now) {
  const modelKeys = new Map();
  const models = [];
  const activeCodexCards = sorted.filter(isGraphThreadActive);
  activeCodexCards.forEach((card) => {
    const modelKey = card.codexModel || "unknown";
    if (modelKeys.has(modelKey)) return;
    const key = `model-${models.length}`;
    modelKeys.set(modelKey, key);
    models.push({ key, modelKey, label: modelDisplayLabel(card.codexModel) });
  });
  if (!sorted.length) return `<div class="graph-empty"><strong>还没有提醒</strong><span>新建一个提醒或关联 Codex 对话后，节点会出现在这里</span></div>`;
  const clusterMarkup = models.map((model) => {
    const modelCards = activeCodexCards.filter((card) => (card.codexModel || "unknown") === model.modelKey);
    const links = modelCards.map((card) => `<path data-graph-link="${escapeHtml(card.id)}" class="graph-link" pathLength="1" d="" />`).join("");
    const labels = modelCards.map((card) => `<text data-graph-link-label="${escapeHtml(card.id)}" class="graph-link-label"></text>`).join("");
    return `
      <section class="graph-cluster" data-graph-cluster="${model.key}">
        <svg class="graph-cluster-links" aria-hidden="true" preserveAspectRatio="none">${links}${labels}</svg>
        <div class="graph-cluster-model">
          <article class="model-bubble" data-graph-model-node="${model.key}">
            <span class="model-bubble-pulse" aria-hidden="true"></span>
            <small>正在使用</small>
            <strong>${escapeHtml(model.label)}</strong>
            <span>活跃模型</span>
            <em>${modelCards.length} 个对话</em>
          </article>
        </div>
        <div class="graph-cluster-threads">${modelCards.map((card) => bubbleMarkup(card, now, modelKeys)).join("")}</div>
      </section>`;
  }).join("");
  const unlinkedCards = sorted.filter((card) => !activeCodexCards.includes(card));
  return `
    <div class="graph-stage">
      ${clusterMarkup || `<div class="graph-idle-note">当前没有正在运行的模型</div>`}
      <section class="graph-unlinked">
        <div class="graph-lane-title">其他提醒与保持关注</div>
        <div class="graph-unlinked-bubbles">${unlinkedCards.map((card) => bubbleMarkup(card, now, modelKeys)).join("")}</div>
      </section>
    </div>`;
}

function graph3DNodes(sorted, now = Date.now()) {
  const activeModels = new Map();
  sorted.forEach((card) => {
    if (!isGraphThreadActive(card) || !card.codexModel) return;
    if (!activeModels.has(card.codexModel)) {
      activeModels.set(card.codexModel, {
        id: `model:${card.codexModel}`,
        kind: "model",
        label: modelDisplayLabel(card.codexModel),
        threadCount: 0,
      });
    }
    activeModels.get(card.codexModel).threadCount += 1;
  });
  const threadNodes = sorted.map((card) => {
    const state = graphState(card, now);
    const active = isGraphThreadActive(card);
    const activeModel = active && card.codexModel
      ? activeModels.get(card.codexModel)
      : null;
    return {
      id: String(card.id),
      kind: "thread",
      cardId: String(card.id),
      label: card.title,
      statusLabel: state === "due"
        ? "有新回复"
        : state === "processing"
          ? "处理中"
          : state === "countdown"
            ? "倒计时"
            : state === "paused"
              ? "已暂停"
              : "保持关注",
      state,
      modelId: activeModel?.id || null,
      effort: active ? card.codexReasoningEffort || "" : "",
      phaseLabel: graphPhaseLabel(card, state),
      phaseStartedAt: Number(card.codexActivityStartedAt) || null,
      runtimeLabel: formatElapsedSince(card.codexActivityStartedAt, now),
      sourceLabel: card.codexHost && card.codexHost !== "local" ? "SSH" : "本机",
    };
  });
  return [...activeModels.values(), ...threadNodes];
}

function graph3DMarkup(sorted, now) {
  return `
    <div class="graph-3d-shell" data-graph-3d-shell>
      <canvas class="graph-3d-canvas" aria-label="3D 提醒关系图；拖动旋转，滚轮缩放，点击节点查看"></canvas>
      <div class="graph-3d-hud" aria-hidden="true">
        <span>拖动旋转</span><span>滚轮缩放</span>
        <span class="graph-effort-scale"><i></i>低</span><span class="graph-effort-scale is-high"><i></i>高</span>
      </div>
      <div class="graph-3d-loading">正在建立 3D 关系图…</div>
      <aside class="graph-node-inspector" data-graph-inspector hidden>
        <button class="graph-inspector-close" type="button" data-graph-inspector-close aria-label="关闭节点详情" title="关闭节点详情">&times;</button>
        <small data-graph-inspector-kind>对话节点</small>
        <strong data-graph-inspector-title></strong>
        <span data-graph-inspector-status></span>
        <div class="graph-node-inspector-actions">
          <button type="button" data-graph-inspector-activate>处理</button>
          <button type="button" data-graph-inspector-edit>编辑</button>
        </div>
      </aside>
    </div>
    <div class="graph-fallback" aria-label="提醒关系图列表">${graphMarkup(sorted, now)}</div>`;
}

function showGraphNodeInspector(node) {
  const inspector = grid.querySelector("[data-graph-inspector]");
  if (!inspector) return;
  if (!node) {
    inspector.hidden = true;
    return;
  }
  inspector.hidden = false;
  inspector.querySelector("[data-graph-inspector-kind]").textContent = node.kind === "model" ? "模型节点" : "对话节点";
  inspector.querySelector("[data-graph-inspector-title]").textContent = node.label;
  inspector.querySelector("[data-graph-inspector-status]").textContent = node.kind === "model"
    ? `${node.threadCount || 0} 个活跃对话`
    : `${node.phaseLabel || node.statusLabel}${node.effort ? ` · 推理${reasoningEffortLabel(node.effort)}` : ""}${node.sourceLabel ? ` · ${node.sourceLabel}` : ""}`;
  const activate = inspector.querySelector("[data-graph-inspector-activate]");
  const edit = inspector.querySelector("[data-graph-inspector-edit]");
  const card = node.kind === "thread" ? cards.find((item) => String(item.id) === String(node.cardId)) : null;
  activate.hidden = !card || !workSession.active;
  edit.hidden = !card;
  if (card) {
    activate.dataset.cardId = card.id;
    activate.textContent = graphState(card) === "due" ? "标记已读" : "打开状态";
    edit.dataset.editCard = card.id;
  } else {
    delete activate.dataset.cardId;
    delete edit.dataset.editCard;
  }
}

async function mountConversationGraph(sorted, now = Date.now()) {
  if (conversationGraphDisposed || grid.classList.contains("is-3d-fallback")) return;
  const options = { nodes: graph3DNodes(sorted, now), reducedMotion: shouldReduceMotion() };
  conversationGraphPending = { sorted, now, ...options };
  if (conversationGraphController) {
    try {
      conversationGraphController.update(options);
    } catch (error) {
      conversationGraphController.dispose();
      conversationGraphController = null;
      grid.classList.remove("is-3d-ready");
      grid.classList.add("is-3d-fallback");
      console.warn("3D graph update failed; using accessible fallback", error);
    }
    return;
  }
  if (conversationGraphMountPromise) return conversationGraphMountPromise;
  const shell = grid.querySelector("[data-graph-3d-shell]");
  const canvas = shell?.querySelector("canvas");
  if (!shell || !canvas) return;
  const version = ++conversationGraphMountVersion;
  conversationGraphMountPromise = (async () => {
    try {
      const module = await import("./graph-3d.js");
      if (version !== conversationGraphMountVersion || conversationGraphDisposed || !shell.isConnected) return;
      conversationGraphController = module.createConversationGraph({
        container: shell, canvas,
        nodes: conversationGraphPending.nodes,
        reducedMotion: conversationGraphPending.reducedMotion,
        onNodeSelect: showGraphNodeInspector,
      });
      conversationGraphController.setActive(!document.hidden);
      shell.querySelector(".graph-3d-loading")?.remove();
      grid.classList.add("is-3d-ready");
    } catch (error) {
      conversationGraphController?.dispose?.();
      conversationGraphController = null;
      grid.classList.remove("is-3d-ready");
      console.warn("3D graph unavailable; using accessible fallback", error);
      grid.classList.add("is-3d-fallback");
    } finally {
      if (version === conversationGraphMountVersion) conversationGraphMountPromise = null;
    }
  })();
  return conversationGraphMountPromise;
}

function updateGraphRuntimeLabels(now = Date.now()) {
  document.querySelectorAll("[data-bubble-runtime]").forEach((element) => {
    element.textContent = formatElapsedSince(element.dataset.phaseStart, now);
  });
  document.querySelectorAll(".graph-link-label").forEach((element) => {
    const bubble = grid.querySelector(`[data-card-id="${CSS.escape(element.dataset.graphLinkLabel)}"]`);
    if (!bubble) return;
    const phase = bubble.dataset.phaseLabel || "处理中";
    const effort = bubble.dataset.reasoningEffort || "";
    const runtime = bubble.querySelector(".thread-bubble-runtime")?.textContent || "";
    element.textContent = [phase, effort ? `推理${effort}` : "", runtime].filter(Boolean).join(" · ");
  });
}

function updateGraphConnections() {
  if (!grid?.classList.contains("card-graph")) return;
  const graphRect = grid.getBoundingClientRect();
  grid.querySelectorAll(".graph-cluster").forEach((cluster) => {
    const linksSvg = cluster.querySelector(".graph-cluster-links");
    const model = cluster.querySelector("[data-graph-model-node]");
    if (!linksSvg || !model) return;
    const clusterRect = cluster.getBoundingClientRect();
    const width = Math.max(1, clusterRect.width);
    const height = Math.max(1, clusterRect.height);
    linksSvg.setAttribute("viewBox", `0 0 ${width} ${height}`);
    cluster.querySelectorAll(".graph-link").forEach((link) => {
      const bubble = cluster.querySelector(`[data-card-id="${CSS.escape(link.dataset.graphLink)}"]`);
      const label = cluster.querySelector(`[data-graph-link-label="${CSS.escape(link.dataset.graphLink)}"]`);
      if (!bubble) return;
      const modelRect = model.getBoundingClientRect();
      const bubbleRect = bubble.getBoundingClientRect();
      const startX = modelRect.right - clusterRect.left;
      const startY = modelRect.top + modelRect.height / 2 - clusterRect.top;
      const endX = bubbleRect.left - clusterRect.left;
      const endY = bubbleRect.top + bubbleRect.height / 2 - clusterRect.top;
      const bend = Math.max(34, (endX - startX) * 0.42);
      link.setAttribute("d", `M ${startX.toFixed(1)} ${startY.toFixed(1)} C ${(startX + bend).toFixed(1)} ${startY.toFixed(1)}, ${(endX - bend).toFixed(1)} ${endY.toFixed(1)}, ${endX.toFixed(1)} ${endY.toFixed(1)}`);
      const thread = cards.find((card) => String(card.id) === String(link.dataset.graphLink));
      link.style.setProperty("--link-color", reasoningEffortColor(thread?.codexReasoningEffort));
      if (label) {
        label.setAttribute("x", ((startX + endX) / 2).toFixed(1));
        label.setAttribute("y", ((startY + endY) / 2 - 7).toFixed(1));
      }
    });
  });
  updateGraphRuntimeLabels();
}

function shouldReduceMotion() {
  if (corpusClockQaReduceMotion) return true;
  return window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches === true;
}

function snapshotCardRects() {
  if (!grid || shouldReduceMotion() || grid.classList.contains("is-3d-ready")) return new Map();
  return new Map(
    [...grid.querySelectorAll("[data-card-id]")].map((element) => [
      element.dataset.cardId,
      element.getBoundingClientRect(),
    ])
  );
}

function animateCardLayout(previousRects) {
  if (!previousRects.size || shouldReduceMotion() || typeof Element.prototype.animate !== "function") return;
  requestAnimationFrame(() => {
    grid.querySelectorAll("[data-card-id]").forEach((element) => {
      const currentRect = element.getBoundingClientRect();
      const previousRect = previousRects.get(element.dataset.cardId);
      let startTransform = "translateY(10px) scale(0.985)";
      let startOpacity = 0;
      if (previousRect) {
        const deltaX = previousRect.left - currentRect.left;
        const deltaY = previousRect.top - currentRect.top;
        const scaleX = previousRect.width && currentRect.width ? previousRect.width / currentRect.width : 1;
        const scaleY = previousRect.height && currentRect.height ? previousRect.height / currentRect.height : 1;
        if (
          Math.abs(deltaX) < 0.5 &&
          Math.abs(deltaY) < 0.5 &&
          Math.abs(scaleX - 1) < 0.01 &&
          Math.abs(scaleY - 1) < 0.01
        ) {
          return;
        }
        startTransform = `translate(${deltaX}px, ${deltaY}px) scale(${scaleX}, ${scaleY})`;
        startOpacity = 0.82;
      }

      element.classList.add("is-layout-animating");
      element.style.transformOrigin = "top left";
      const animation = element.animate(
        [
          { opacity: startOpacity, transform: startTransform },
          { opacity: 1, transform: "translate(0, 0) scale(1)" },
        ],
        {
          duration: previousRect ? CARD_LAYOUT_ANIMATION_MS : 420,
          easing: previousRect ? "cubic-bezier(0.19, 1, 0.22, 1)" : "cubic-bezier(0.22, 0.9, 0.22, 1)",
          fill: "both",
        }
      );
      const cleanup = () => {
        element.classList.remove("is-layout-animating");
        element.style.transformOrigin = "";
      };
      animation.addEventListener("finish", cleanup, { once: true });
      animation.addEventListener("cancel", cleanup, { once: true });
    });
  });
}

function render(options = {}) {
  const previousRects = options.animate === false ? new Map() : snapshotCardRects();
  ensureActiveWorkBaselines();
  const now = Date.now();
  const sorted = cardOrderCore.sortCards(cards, {
    workActive: workSession.active,
    now,
  });

  const dueCards = sorted.filter((card) => getCardState(card, now) === "due");

  renderWorkSession();
  queueWidgetSnapshotSync();
  document.body.classList.toggle("has-due-reminders", dueCards.length > 0);
  grid.classList.toggle("has-due", dueCards.length > 0);
  grid.classList.toggle("has-secondary", sorted.length > dueCards.length);
  grid.classList.add("card-graph");
  grid.dataset.dueCount = String(dueCards.length);
  if (!grid.querySelector("[data-graph-3d-shell]")) grid.innerHTML = graph3DMarkup(sorted, now);
  conversationGraphPending = { sorted, now, nodes: graph3DNodes(sorted, now), reducedMotion: shouldReduceMotion() };
  if (conversationGraphRenderFrame) return;
  conversationGraphRenderFrame = requestAnimationFrame(() => {
    conversationGraphRenderFrame = 0;
    if (conversationGraphDisposed) return;
    const pending = conversationGraphPending;
    const fallback = grid.querySelector(".graph-fallback");
    const markup = graphMarkup(pending.sorted, pending.now);
    if (fallback && fallback.innerHTML !== markup) fallback.innerHTML = markup;
    if (grid.classList.contains("is-3d-fallback")) {
      animateCardLayout(previousRects);
      updateGraphConnections();
    }
    mountConversationGraph(pending.sorted, pending.now);
  });
}

function updateClocks() {
  ensureDailyHeaderClock();
  updateWallClock();
  updateDailyQuote();
  updateWorkDuration();
  updateGraphRuntimeLabels();
  if (!workSession.active) return;
  let needsRender = false;
  document.querySelectorAll("[data-countdown]").forEach((element) => {
    const card = cards.find((item) => item.id === element.dataset.countdown);
    if (!card || !card.started) return;
    if (card.nextAt <= Date.now() && !element.closest(".card").classList.contains("is-due")) {
      enqueueFeishuEvent("reminder_due", `reminder:${card.id}:${card.nextAt}`, {
        cardTitle: card.title,
      });
      needsRender = true;
      return;
    }
    element.textContent = formatCountdown(card.nextAt);
  });
  if (needsRender) render();
}

function openNewDialog() {
  editingCardsBase = businessState.getItem(STORAGE_KEY);
  form.reset();
  document.querySelector("#cardId").value = "";
  document.querySelector("#repeatValue").value = "30";
  document.querySelector("#repeatUnit").value = "minute";
  document.querySelector("#dialogTitle").textContent = "新建提醒";
  document.querySelector("#deleteCardButton").hidden = true;
  populateCodexSelect("", "local");
  updateReminderMode();
  dialog.showModal();
  loadCodexThreads();
  setTimeout(() => document.querySelector("#cardTitle").focus(), 20);
}

function openEditDialog(id) {
  editingCardsBase = businessState.getItem(STORAGE_KEY);
  const card = cards.find((item) => item.id === id);
  if (!card) return;
  document.querySelector("#cardId").value = card.id;
  document.querySelector("#cardTitle").value = card.title;
  document.querySelector("#cardTag").value = card.tag || "";
  document.querySelector("#repeatValue").value = card.intervalValue;
  document.querySelector("#repeatUnit").value = card.intervalUnit;
  populateCodexSelect(card.codexThreadId, card.codexHost);
  updateReminderMode();
  document.querySelector("#dialogTitle").textContent = "编辑提醒";
  document.querySelector("#deleteCardButton").hidden = false;
  dialog.showModal();
  loadCodexThreads();
}

function closeDialog() {
  dialog.close();
}

async function saveCard(event) {
  event.preventDefault();
  if (!form.reportValidity()) return;

  const id = document.querySelector("#cardId").value;
  const existing = cards.find((item) => item.id === id);
  if (id && !existing) {
    businessState.fail(new Error("该卡片已在另一个页面删除"));
    return;
  }
  const intervalValue = Number(document.querySelector("#repeatValue").value);
  const intervalUnit = document.querySelector("#repeatUnit").value;
  const selectedRef = document.querySelector("#codexThread").value;
  const selected = parseCodexThreadRef(selectedRef);
  const codexThreadId = selected.threadId;
  const codexHost = selected.hostId;
  const selectedThread = codexThreads.find((thread) => codexThreadRef(thread.hostId, thread.id) === selectedRef);
  const sameThread = Boolean(existing && existing.codexThreadId === codexThreadId && existing.codexHost === codexHost);
  const card = {
    id: existing?.id || makeId(),
    title: document.querySelector("#cardTitle").value.trim(),
    tag: document.querySelector("#cardTag").value.trim(),
    intervalValue,
    intervalUnit,
    intervalMs: intervalValue * UNIT_MS[intervalUnit],
    createdAt: existing?.createdAt || Date.now(),
    started: sameThread || (!existing?.codexThreadId && !codexThreadId) ? existing?.started || false : false,
    nextAt: sameThread || (!existing?.codexThreadId && !codexThreadId) ? existing?.nextAt ?? null : null,
    codexThreadId,
    codexHost,
    codexThreadName: codexThreadId ? selectedThread?.name || existing?.codexThreadName || "Codex 对话" : "",
    codexArmed: sameThread ? existing.codexArmed : false,
    codexDue: sameThread ? existing.codexDue : false,
    codexLastSeenTurnId: sameThread ? existing.codexLastSeenTurnId : null,
    codexLatestTurnId: sameThread ? existing.codexLatestTurnId : null,
    codexLatestCompletedAt: sameThread ? existing.codexLatestCompletedAt : null,
    codexModel: sameThread ? existing.codexModel : "",
    codexReasoningEffort: sameThread ? existing.codexReasoningEffort : "",
    codexPhase: sameThread ? existing.codexPhase : "idle",
    codexPhaseLabel: sameThread ? existing.codexPhaseLabel : "",
    codexActivityStartedAt: sameThread ? existing.codexActivityStartedAt : null,
    codexToolKind: sameThread ? existing.codexToolKind : "",
    codexCwd: sameThread ? existing.codexCwd : "",
    codexStatus: sameThread ? existing.codexStatus : "unknown",
  };

  if (existing) Object.assign(existing, card);
  else cards.push(card);

  if (!await saveCards(editingCardsBase)) return;
  closeDialog();
  render();
  refreshCodexEventStream();
  syncCodexCards();
}

async function deleteCard() {
  const id = document.querySelector("#cardId").value;
  const card = cards.find((item) => item.id === id);
  if (!card || !confirm(`删除“${card.title}”吗？`)) return;
  cards = cards.filter((item) => item.id !== id);
  if (!await saveCards()) return;
  closeDialog();
  render();
  refreshCodexEventStream();
}

async function acknowledgeCard(id) {
  const card = cards.find((item) => item.id === id);
  if (!card || getCardState(card) !== "due") return;
  const readSource = card.codexThreadId
    ? card.codexLatestTurnId || card.codexLastSeenTurnId || Date.now()
    : card.nextAt || Date.now();
  if (card.codexThreadId) {
    card.codexDue = false;
    card.codexLastSeenTurnId = card.codexLatestTurnId || card.codexLastSeenTurnId;
  } else {
    Object.assign(card, startTimer(card));
  }
  if (!await saveCards()) return;
  enqueueFeishuEvent("card_read", `read:${card.id}:${readSource}`, { cardTitle: card.title });
  render();
}

function populateCodexSelect(selectedId = "", selectedHost = "local") {
  const select = document.querySelector("#codexThread");
  const selectedRef = selectedId.includes("::") ? selectedId : codexThreadRef(selectedHost, selectedId);
  const selectedThreadRef = parseCodexThreadRef(selectedRef);
  const selectedCard = cards.find((card) => cardCodexThreadRef(card) === selectedRef);
  const knownThread = selectedThreadRef.threadId && !codexThreads.some((thread) => codexThreadRef(thread.hostId, thread.id) === selectedRef)
    ? [{ id: selectedThreadRef.threadId, hostId: selectedThreadRef.hostId, name: selectedCard?.codexThreadName || "已关联的对话" }]
    : [];
  const options = [...knownThread, ...codexThreads];
  select.innerHTML = `<option value="">不关联</option>${options
    .map((thread) => {
      const ref = codexThreadRef(thread.hostId, thread.id);
      const source = thread.hostId === "local" ? "本机" : thread.sourceLabel || thread.hostId;
      return `<option value="${escapeHtml(ref)}">[${escapeHtml(source)}] ${escapeHtml(thread.name)}</option>`;
    })
    .join("")}`;
  select.value = selectedRef || "";
  select.disabled = !codexAvailable && !selectedRef;
}

function updateReminderMode() {
  const linked = Boolean(document.querySelector("#codexThread").value);
  document.querySelector("#intervalField").hidden = linked;
  document.querySelector("#repeatValue").required = !linked;
}

async function applyCodexThreadNames(threads = []) {
  const names = new Map(threads.map((thread) => [codexThreadRef(thread.hostId, thread.id), thread.name]));
  let changed = false;
  cards.forEach((card) => {
    if (!card.codexThreadId) return;
    const name = names.get(cardCodexThreadRef(card));
    if (name && card.codexThreadName !== name) {
      card.codexThreadName = name;
      changed = true;
    }
  });
  if (changed) {
    if (!await saveCards()) return;
    render();
  }
}

async function loadCodexThreads() {
  const status = document.querySelector("#codexStatus");
  try {
    const response = await fetch("/api/codex/threads", { cache: "no-store" });
    const data = await response.json();
    if (!response.ok || !data.available) throw new Error(data.error || "无法读取 Codex 对话");
    codexThreads = data.threads || [];
    codexAvailable = true;
    await applyCodexThreadNames(codexThreads);
    status.textContent = codexThreads.length ? `最近 ${codexThreads.length} 个对话` : "没有找到对话";
  } catch {
    codexThreads = [];
    codexAvailable = false;
    status.textContent = "Codex 暂时不可用";
  }
  const selected = parseCodexThreadRef(document.querySelector("#codexThread").value);
  populateCodexSelect(selected.threadId, selected.hostId);
  refreshCodexEventStream();
  syncCodexCards();
}

async function applyCodexStatuses(threadStatuses = [], options = {}) {
  const countCompletions = options.countCompletions !== false;
  const markDue = options.markDue !== false && workSession.active;
  const renderAfter = options.renderAfter !== false;
  const linkedCards = cards.filter((card) => card.codexThreadId);
  if (!linkedCards.length) return;
  const statuses = new Map(threadStatuses.map((thread) => [codexThreadRef(thread.hostId, thread.id), thread]));
  let changed = false;
  let workChanged = false;
  const notifications = [];
  linkedCards.forEach((card) => {
    const thread = statuses.get(cardCodexThreadRef(card));
    if (!thread) return;
    if (thread.name && card.codexThreadName !== thread.name) {
      card.codexThreadName = thread.name;
      changed = true;
    }
    const nextStatus = thread.exists ? thread.status : "unavailable";
    if (card.codexStatus !== nextStatus) {
      card.codexStatus = nextStatus;
      changed = true;
    }
    const nextModel = typeof thread.model === "string" && thread.model ? thread.model : card.codexModel || "";
    const nextEffort = typeof thread.reasoningEffort === "string" && thread.reasoningEffort
      ? thread.reasoningEffort
      : card.codexReasoningEffort || "";
    const nextPhase = thread.exists && (isCodexActiveStatus(nextStatus) || (thread.phase && thread.phase !== "idle"))
      ? thread.phase || "reasoning"
      : "idle";
    const nextPhaseLabel = thread.phaseLabel || (nextPhase === "idle" ? "保持关注" : "处理中");
    const nextActivityStartedAt = Number.isFinite(thread.activityStartedAt)
      ? thread.activityStartedAt
      : null;
    const nextToolKind = typeof thread.toolKind === "string" ? thread.toolKind : "";
    const nextCwd = typeof thread.cwd === "string" && thread.cwd ? thread.cwd : card.codexCwd || "";
    if (
      card.codexModel !== nextModel
      || card.codexReasoningEffort !== nextEffort
      || card.codexPhase !== nextPhase
      || card.codexPhaseLabel !== nextPhaseLabel
      || card.codexActivityStartedAt !== nextActivityStartedAt
      || card.codexToolKind !== nextToolKind
      || card.codexCwd !== nextCwd
    ) {
      Object.assign(card, {
        codexModel: nextModel,
        codexReasoningEffort: nextEffort,
        codexPhase: nextPhase,
        codexPhaseLabel: nextPhaseLabel,
        codexActivityStartedAt: nextActivityStartedAt,
        codexToolKind: nextToolKind,
        codexCwd: nextCwd,
      });
      changed = true;
    }
    if (!thread.latestCompletedTurnId) return;
    const latestTurnId = thread.latestCompletedTurnId;
    if (card.codexLatestCompletedAt !== thread.latestCompletedAt) {
      card.codexLatestCompletedAt = Number.isFinite(thread.latestCompletedAt)
        ? thread.latestCompletedAt
        : null;
      changed = true;
    }
    if (workSession.active && !hasWorkBaseline(card)) {
      card.codexArmed = true;
      card.codexLastSeenTurnId = latestTurnId;
      card.codexLatestTurnId = latestTurnId;
      card.codexDue = false;
      baselineWorkCard(card);
      changed = true;
      workChanged = true;
      return;
    }
    if (!card.codexArmed || !markDue) {
      card.codexArmed = true;
      card.codexLastSeenTurnId = latestTurnId;
      card.codexLatestTurnId = latestTurnId;
      card.codexDue = false;
      changed = true;
    } else if (latestTurnId !== card.codexLastSeenTurnId) {
      if (countCompletions && recordWorkCompletion(card, latestTurnId)) {
        changed = true;
        workChanged = true;
        notifications.push(["codex_completed", `codex:${cardCodexThreadRef(card)}:${latestTurnId}`, {
          cardTitle: card.title,
          threadName: card.codexThreadName || thread.name || "Codex 对话",
          completionCount: totalWorkCount(),
        }]);
      }
      if (!card.codexDue || card.codexLatestTurnId !== latestTurnId) changed = true;
      card.codexDue = true;
      card.codexLatestTurnId = latestTurnId;
    }
  });
  if (changed || workChanged) {
    if (!await saveCards()) return;
    notifications.forEach((event) => enqueueFeishuEvent(...event));
    if (renderAfter) render();
  }
}

function linkedCodexThreadIds() {
  return [...new Set(cards.filter((card) => card.codexThreadId).map(cardCodexThreadRef))].sort();
}

function refreshCodexEventStream() {
  const threadIds = [...new Set(
    cards
      .filter((card) => card.codexThreadId && card.codexHost === "local")
      .map((card) => card.codexThreadId),
  )].sort();
  const nextKey = threadIds.join("|");
  if (!workSession.active) {
    codexEventSource?.close();
    codexEventSource = null;
    codexEventKey = "";
    return;
  }
  if (
    codexEventSource &&
    codexEventKey === nextKey &&
    codexEventSource.readyState !== EventSource.CLOSED
  ) {
    return;
  }
  codexEventSource?.close();
  codexEventSource = null;
  codexEventKey = nextKey;
  if (!threadIds.length || typeof EventSource === "undefined") return;

  const query = new URLSearchParams();
  threadIds.forEach((id) => query.append("id", id));
  const eventSource = new EventSource(`/api/codex/events?${query}`);
  codexEventSource = eventSource;
  eventSource.onmessage = async (event) => {
    try {
      const data = JSON.parse(event.data);
      if (data.available) await applyCodexStatuses(data.threads || []);
    } catch {
      // A malformed event is ignored; the fallback sync will reconcile state.
    }
  };
  eventSource.onerror = () => {
    if (eventSource.readyState === EventSource.CLOSED && codexEventSource === eventSource) {
      codexEventSource = null;
      setTimeout(refreshCodexEventStream, 1000);
    }
  };
}

async function fetchCodexStatusesForCards(linkedCards) {
  if (!linkedCards.length) return [];
  const query = new URLSearchParams();
  [...new Set(linkedCards.map(cardCodexThreadRef))].forEach((ref) => query.append("id", ref));
  const response = await fetch(`/api/codex/status?${query}`, { cache: "no-store" });
  const data = await response.json();
  if (!response.ok || !data.available) throw new Error(data.error || "Codex 同步失败");
  return data.threads || [];
}

async function syncCodexCards() {
  const linkedCards = cards.filter((card) => card.codexThreadId);
  if (!linkedCards.length || codexSyncing) return;
  codexSyncing = true;
  try {
    await applyCodexStatuses(await fetchCodexStatusesForCards(linkedCards), {
      countCompletions: workSession.active,
      markDue: workSession.active,
    });
  } catch {
    let changed = false;
    linkedCards.forEach((card) => {
      if (card.codexStatus !== "unavailable") {
        card.codexStatus = "unavailable";
        changed = true;
      }
    });
    if (changed) {
      await saveCards();
      render();
    }
  } finally {
    codexSyncing = false;
  }
}

async function startWorkSession() {
  if (workSessionBusy) return;
  workSessionBusy = true;
  renderWorkSession();

  const linkedCards = cards.filter((card) => card.codexThreadId);
  workSession = {
    ...emptyWorkSession(),
    active: true,
    startedAt: Date.now(),
  };
  if (!await saveWorkSession()) {
    workSessionBusy = false;
    renderWorkSession();
    return;
  }
  renderWorkSession();

  try {
    const statuses = await fetchCodexStatusesForCards(linkedCards);
    await applyCodexStatuses(statuses, {
      countCompletions: false,
      markDue: false,
      renderAfter: false,
    });
  } catch {
    // If Codex is temporarily unavailable, use the last local snapshot as the baseline.
  }

  cards.filter((card) => card.codexThreadId).forEach((card) => {
    card.codexDue = false;
    if (card.codexLatestTurnId) {
      card.codexArmed = true;
      card.codexLastSeenTurnId = card.codexLatestTurnId;
    }
    baselineWorkCard(card, true);
  });

  workSessionBusy = false;
  if (!await saveCards()) return;
  render();
  refreshCodexEventStream();
  syncCodexCards();
  enqueueFeishuEvent("work_started", `work-started:${workSession.startedAt}`, {});
}

function endWorkSession(endedAt = Date.now()) {
  codexEventSource?.close();
  codexEventSource = null;
  codexEventKey = "";
  workSessionBusy = false;
  render();
  return true;
}

function toggleWorkSession() {
  if (workSession.active) openWorkReflectionDialog();
  else startWorkSession();
}

async function saveWorkReflection(event) {
  event.preventDefault();
  if (workReflectionPreview) {
    await closeWorkReflectionDialog();
    return;
  }
  if (!workSession.active || workSessionBusy) return;
  if (workSession.startedAt !== reflectionStartedFor) {
    workReflectionStatus.textContent = "班次已在另一页面改变，请关闭此窗口后重新确认";
    return;
  }
  const endedAt = Date.now();
  const mood = workReflectionForm.elements.workMood.value || "";
  const entry = workHistoryCore.createEntry({
    id: `shift-${workSession.startedAt}-${endedAt}`,
    session: workSession,
    endedAt,
    completionCount: totalWorkCount(),
    completions: workCompletionBreakdown(),
    conversations: selectedWorkConversations(),
    mood,
    note: workReflectionNote.value,
  });
  confirmWorkReflection.disabled = true;
  workSessionBusy = true;
  workReflectionStatus.textContent = "";
  const finalSession = { ...workSession, active: false, endedAt };
  const finalCards = cards.map((card) => card.codexThreadId
    ? { ...card, codexDue: false, codexLastSeenTurnId: card.codexLatestTurnId || card.codexLastSeenTurnId }
    : card);
  if (!await persistWorkHistoryEntry(entry, finalSession, finalCards)) {
    workSessionBusy = false;
    workReflectionStatus.textContent = "保存失败，本班尚未下班，请重试";
    confirmWorkReflection.disabled = false;
    return;
  }
  endWorkSession(endedAt);
  enqueueFeishuEvent("work_ended", `work-ended:${entry.id}`, {
    duration: formatWorkDuration(entry.durationMs),
    completionCount: entry.completionCount,
    moodLabel: workHistoryCore.moodById(entry.mood)?.label || "",
    note: entry.note,
    occurredAtLabel: feishuTimeLabel(endedAt),
  });
  await closeWorkReflectionDialog();
  confirmWorkReflection.disabled = false;
}

async function startCard(id) {
  const card = cards.find((item) => item.id === id);
  if (!workSession.active || !card || getCardState(card) !== "idle") return;
  Object.assign(card, startTimer(card));
  if (!await saveCards()) return;
  render();
}

function activateCard(id) {
  if (!workSession.active) return;
  const card = cards.find((item) => item.id === id);
  if (!card) return;
  if (getCardState(card) === "idle") startCard(id);
  else acknowledgeCard(id);
}

document.querySelector("#newCardButton").addEventListener("click", openNewDialog);
workToggleButton.addEventListener("click", toggleWorkSession);
feishuSettingsButton?.addEventListener("click", openFeishuDialog);
feishuQuickEnabled?.addEventListener("change", toggleFeishuQuickNotifications);
document.querySelector("#closeFeishuDialog")?.addEventListener("click", closeFeishuDialog);
feishuForm?.addEventListener("submit", saveFeishuSettings);
testFeishuButton?.addEventListener("click", testFeishuConnection);
document.querySelector("#closeWorkReflection").addEventListener("click", closeWorkReflectionDialog);
document.querySelector("#cancelWorkReflection").addEventListener("click", closeWorkReflectionDialog);
workReflectionForm.addEventListener("submit", saveWorkReflection);
workReflectionThreads?.addEventListener("change", (event) => {
  if (event.target.matches("[data-reflection-thread]")) syncWorkReflectionThreadSelection();
});
toggleReflectionThreads?.addEventListener("click", () => {
  const inputs = [...workReflectionThreads.querySelectorAll("[data-reflection-thread]")];
  const shouldSelect = inputs.some((input) => !input.checked);
  inputs.forEach((input) => { input.checked = shouldSelect; });
  syncWorkReflectionThreadSelection();
});
clockSkinSwitch?.addEventListener("click", cycleHeaderClock);
document.querySelector("#closeDialogButton").addEventListener("click", closeDialog);
document.querySelector("#cancelDialogButton").addEventListener("click", closeDialog);
document.querySelector("#deleteCardButton").addEventListener("click", deleteCard);
document.querySelector("#codexThread").addEventListener("change", updateReminderMode);
form.addEventListener("submit", saveCard);

dialog.addEventListener("click", (event) => {
  if (event.target === dialog) closeDialog();
});

feishuDialog?.addEventListener("click", (event) => {
  if (event.target === feishuDialog) closeFeishuDialog();
});

workReflectionDialog.addEventListener("click", (event) => {
  if (event.target === workReflectionDialog) closeWorkReflectionDialog();
});
workReflectionDialog.addEventListener("close", () => {
  workReflectionPreview = false;
  workReflectionReturnFocus?.focus?.();
  workReflectionReturnFocus = null;
});

grid.addEventListener("click", (event) => {
  if (event.target.closest("[data-graph-inspector-close]")) {
    showGraphNodeInspector(null);
    conversationGraphController?.clearSelection?.();
    return;
  }
  const edit = event.target.closest("[data-edit-card]");
  if (edit) {
    event.stopPropagation();
    openEditDialog(edit.dataset.editCard);
    return;
  }
  const card = event.target.closest("[data-card-id]");
  if (card) activateCard(card.dataset.cardId);
});

grid.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    showGraphNodeInspector(null);
    conversationGraphController?.clearSelection?.();
    return;
  }
  const card = event.target.closest("[data-card-id]");
  if (card && (event.key === "Enter" || event.key === " ")) {
    event.preventDefault();
    activateCard(card.dataset.cardId);
  }
});

window.addEventListener("resize", updateGraphConnections);

window.addEventListener("storage", (event) => {
  if (event.key === HEADER_CLOCK_KEY) {
    headerClockDayKey = null;
    ensureDailyHeaderClock(true);
    return;
  }
});

businessState.subscribe(({ keys }) => {
  if (!keys.includes(STORAGE_KEY) && !keys.includes(WORK_SESSION_KEY) && !keys.includes(WORK_HISTORY_KEY)) return;
  if (keys.includes(STORAGE_KEY)) cards = loadCards();
  if (keys.includes(WORK_SESSION_KEY)) workSession = loadWorkSession();
  if (keys.includes(WORK_HISTORY_KEY)) workHistoryStore = loadWorkHistory();
  render();
  refreshCodexEventStream();
  syncCodexCards();
});

window.addEventListener("focus", () => {
  updateDailyQuote();
  updateWeatherForecast();
  syncCodexCards();
});
window.addEventListener("online", () => {
  dailyQuoteSlot = null;
  updateDailyQuote();
  updateWeatherForecast(true);
  refreshCodexEventStream();
  syncCodexCards();
  loadFeishuStatus({ updateForm: false });
  queueWidgetSnapshotSync(0);
});
document.addEventListener("visibilitychange", () => {
  conversationGraphController?.setActive?.(!document.hidden);
  if (document.visibilityState === "visible") {
    HEADER_CLOCK_RUNTIMES[activeHeaderClockId]?.resume({
      now: performance.now(),
      date: corpusClockRenderDate(),
    });
    startCorpusClockAnimation();
    refreshCodexEventStream();
    syncCodexCards();
  } else {
    stopCorpusClockAnimation();
  }
});
window.addEventListener("pagehide", () => {
  stopCorpusClockAnimation();
  conversationGraphDisposed = true;
  conversationGraphMountVersion += 1;
  conversationGraphMountPromise = null;
  cancelAnimationFrame(conversationGraphRenderFrame);
  conversationGraphRenderFrame = 0;
  conversationGraphController?.dispose?.();
  conversationGraphController = null;
  codexEventSource?.close();
  codexEventSource = null;
  codexEventKey = "";
});
window.addEventListener("pageshow", (event) => {
  if (!event.persisted) return;
  conversationGraphDisposed = false;
  grid.classList.remove("is-3d-ready", "is-3d-fallback");
  grid.innerHTML = graph3DMarkup(cards, Date.now());
  startCorpusClockAnimation();
  conversationGraphController?.setActive?.(!document.hidden);
  render({ animate: false });
  refreshCodexEventStream();
  syncCodexCards();
});

HEADER_CLOCKS.forEach((clock) => HEADER_CLOCK_RUNTIMES[clock.id]?.initialize());
ensureDailyHeaderClock(true);
revealHeaderClockAfterHydration();
startCorpusClockAnimation();
render({ animate: false });
if (new URLSearchParams(window.location.search).get("reflectionPreview") === "1") {
  openWorkReflectionDialog({ preview: true });
}
updateWallClock();
updateDailyQuote();
updateWeatherForecast();
loadFeishuStatus({ updateForm: false });
refreshCodexEventStream();
loadCodexThreads();
setInterval(updateClocks, 1000);
setInterval(updateWeatherForecast, 10 * 60 * 1000);
setInterval(syncCodexCards, CODEX_FALLBACK_SYNC_MS);
setInterval(syncWidgetSnapshot, WIDGET_SNAPSHOT_SYNC_MS);
})().catch(window.EntropyState.fail);
