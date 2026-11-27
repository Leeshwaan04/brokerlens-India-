// The chart studio: draws a chart with its toolbar into a host element.
// Shared by brokerlens.in and paper.brokerlens.in. The renderer is TradingView
// Lightweight Charts (Apache-2.0), loaded separately as window.LightweightCharts;
// everything else (data model, resampling, indicators, controls, persistence)
// is this package.
import { barsFromCandles, barsFromColumns, type CandleFile, type DailyColumns } from "./core/series";
import { resampleDaily } from "./core/resample";
import { heikinAshi } from "./core/transforms";
import { IST_OFFSET_SEC, istDate } from "./core/time";
import { Bar, isIntraday, TIMEFRAME_LABEL, Timeframe } from "./core/types";
import { bollinger, ema, rsi, sma, swingZones } from "./indicators";
import { injectStyles } from "./ui/styles";

// Lightweight Charts ships no types we depend on; its surface is used through `any`.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Lwc = any;

export interface DataAdapter {
  /** Shown in summaries and used to key saved settings such as the target line. */
  symbol: string;
  /** Daily bars, oldest first. Throw if there is no history. */
  loadDaily(): Promise<Bar[]>;
  /**
   * Intraday bars, when a licensed source exists. Absent means the intraday
   * timeframes are not offered at all; the studio never synthesises intraday
   * bars from daily ones.
   */
  intraday?: { timeframes: Timeframe[]; load(tf: Timeframe): Promise<Bar[]> };
}

export interface StudioOptions {
  adapter: DataAdapter;
  height?: number;
  /** Defaults to window.LightweightCharts. */
  lib?: Lwc;
  /** Prefix for saved settings (localStorage). */
  storagePrefix?: string;
}

export interface StudioHandle {
  destroy(): void;
  setTimeframe(tf: Timeframe): Promise<void>;
}

// ------------------------------------------------------------------ settings

type ChartType = "candles" | "hollow" | "heikin" | "bars" | "line" | "area" | "baseline";
const CHART_TYPES: { id: ChartType; label: string }[] = [
  { id: "candles", label: "Candles" },
  { id: "hollow", label: "Hollow" },
  { id: "heikin", label: "Heikin-Ashi" },
  { id: "bars", label: "Bars" },
  { id: "line", label: "Line" },
  { id: "area", label: "Area" },
  { id: "baseline", label: "Baseline" },
];

type IndicatorId = "sma" | "ema20" | "ema" | "bb" | "rsi" | "zones" | "vol";
const INDICATORS: { id: IndicatorId; label: string; minBars: number }[] = [
  { id: "sma", label: "SMA 20", minBars: 20 },
  { id: "ema20", label: "EMA 20", minBars: 20 },
  { id: "ema", label: "EMA 50", minBars: 50 },
  { id: "bb", label: "Bollinger", minBars: 20 },
  { id: "rsi", label: "RSI 14", minBars: 15 },
  { id: "zones", label: "Support/Resistance", minBars: 5 },
  { id: "vol", label: "Volume", minBars: 1 },
];

interface RangeDef { id: string; label: string; days: number | null; intradayOnly?: boolean }
const RANGES: RangeDef[] = [
  { id: "1D", label: "1D", days: 1, intradayOnly: true },
  { id: "5D", label: "5D", days: 5 },
  { id: "1M", label: "1M", days: 31 },
  { id: "3M", label: "3M", days: 92 },
  { id: "6M", label: "6M", days: 183 },
  { id: "1Y", label: "1Y", days: 366 },
  { id: "3Y", label: "3Y", days: 1096 },
  { id: "All", label: "All", days: null },
];
const DEFAULT_RANGE: Record<string, string> = { D: "6M", W: "3Y", M: "All" };

interface Prefs {
  chartType: ChartType;
  logScale: boolean;
  magnet: boolean;
  indicators: Record<IndicatorId, boolean>;
  timeframe: Timeframe;
}

const PREFS_VERSION = "v2";

function readJson(key: string): Record<string, unknown> | null {
  try {
    const raw = localStorage.getItem(key);
    const v = raw ? JSON.parse(raw) : null;
    return v && typeof v === "object" ? (v as Record<string, unknown>) : null;
  } catch {
    return null;
  }
}
function writeJson(key: string, value: unknown) {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    /* private mode or full: settings just do not persist */
  }
}

function loadPrefs(prefix: string): Prefs {
  // v1 (the old stock chart) used the same field names; read it once as a fallback.
  const saved = readJson(`${prefix}_prefs_${PREFS_VERSION}`) ?? readJson(`${prefix}_prefs_v1`) ?? {};
  const ind = (saved.indicators ?? {}) as Record<string, unknown>;
  const type = CHART_TYPES.some((t) => t.id === saved.chartType) ? (saved.chartType as ChartType) : "candles";
  const tf = (["D", "W", "M"] as Timeframe[]).includes(saved.timeframe as Timeframe) ? (saved.timeframe as Timeframe) : "D";
  return {
    chartType: type,
    logScale: Boolean(saved.logScale),
    magnet: Boolean(saved.magnet),
    timeframe: tf,
    indicators: {
      sma: Boolean(ind.sma), ema20: Boolean(ind.ema20), ema: Boolean(ind.ema), bb: Boolean(ind.bb), rsi: Boolean(ind.rsi),
      zones: Boolean(ind.zones), vol: typeof ind.vol === "boolean" ? ind.vol : true,
    },
  };
}

const TARGETS_KEY = "bl_chart_targets_v1"; // unchanged, so existing target lines survive
function loadTarget(symbol: string): number | null {
  const v = Number((readJson(TARGETS_KEY) ?? {})[symbol]);
  return Number.isFinite(v) && v > 0 ? v : null;
}
function saveTarget(symbol: string, price: number | null) {
  const map = readJson(TARGETS_KEY) ?? {};
  if (price && Number.isFinite(price) && price > 0) map[symbol] = price;
  else delete map[symbol];
  writeJson(TARGETS_KEY, map);
}

// -------------------------------------------------------------------- helpers

function themeColors() {
  const s = getComputedStyle(document.documentElement);
  const v = (name: string, fallback: string) => (s.getPropertyValue(name) || fallback).trim();
  return {
    text: v("--text-muted", "#6b7280"),
    border: v("--border", "#e5e7eb"),
    up: v("--up", "#0f7a4d"),
    down: v("--down", "#c0392b"),
    accent: v("--accent", "#2f4a8f"),
    sma: "#2563eb", ema20: "#0ea5e9", ema: "#d97706", bb: "#7c3aed", rsi: "#ec4899",
    resistance: "#dc2626", support: "#059669", target: "#f59e0b",
  };
}
const alpha = (hex: string, a: number) => {
  const m = /^#([0-9a-f]{6})$/i.exec(hex.trim());
  if (!m) return hex;
  const n = parseInt(m[1], 16);
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${a})`;
};
const fmtNum = (n: number | null | undefined) => (n == null ? "-" : Number(n).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 }));
const fmtVol = (n: number | null | undefined) => {
  if (n == null) return "-";
  if (n >= 1e7) return `${(n / 1e7).toFixed(2)} Cr`;
  if (n >= 1e5) return `${(n / 1e5).toFixed(2)} L`;
  if (n >= 1e3) return `${(n / 1e3).toFixed(1)} K`;
  return String(Math.round(n));
};
const el = <K extends keyof HTMLElementTagNameMap>(tag: K, cls?: string, text?: string) => {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined) e.textContent = text;
  return e;
};

/** Lightweight Charts time for a bar: a business-day string for daily and up, a (shifted) timestamp for intraday. */
const lwcTime = (b: Bar, intraday: boolean) => (intraday ? b.t + IST_OFFSET_SEC : istDate(b.t));

// ---------------------------------------------------------------------- mount

export async function mountStudio(host: HTMLElement, opts: StudioOptions): Promise<StudioHandle> {
  injectStyles();
  const { adapter } = opts;
  const prefix = opts.storagePrefix ?? "bl_chart";
  const LWC: Lwc = opts.lib ?? (window as unknown as { LightweightCharts?: Lwc }).LightweightCharts;
  host.classList.add("blc");
  const message = (text: string) => {
    host.replaceChildren(el("p", "blc-note", text));
  };

  if (!LWC) {
    message("The chart library failed to load.");
    return { destroy() {}, setTimeframe: async () => {} };
  }
  let daily: Bar[];
  try {
    daily = await adapter.loadDaily();
  } catch {
    message("Price history is not available for this instrument yet.");
    return { destroy() {}, setTimeframe: async () => {} };
  }
  if (daily.length < 2) {
    message("Not enough price history yet.");
    return { destroy() {}, setTimeframe: async () => {} };
  }

  const prefs = loadPrefs(prefix);
  const intradayCache = new Map<Timeframe, Bar[]>();
  let tf: Timeframe = prefs.timeframe;
  let rangeId = DEFAULT_RANGE[tf] ?? "6M";
  let bars: Bar[] = resampleDaily(daily, tf as "D" | "W" | "M");
  let target = loadTarget(adapter.symbol);
  let colors = themeColors();
  let timeIndex = new Map<string | number, number>();
  const disposers: (() => void)[] = [];

  const savePrefsNow = () =>
    writeJson(`${prefix}_prefs_${PREFS_VERSION}`, {
      chartType: prefs.chartType, logScale: prefs.logScale, magnet: prefs.magnet, indicators: prefs.indicators,
      timeframe: isIntraday(tf) ? "D" : tf,
    });

  // ---- chart
  const canvasWrap = el("div", "blc-canvas");
  canvasWrap.setAttribute("role", "img");
  const chart: Lwc = LWC.createChart(canvasWrap, {
    width: host.clientWidth || undefined,
    height: opts.height ?? 360,
    layout: { background: { type: "solid", color: "transparent" }, textColor: colors.text },
    grid: { vertLines: { visible: false }, horzLines: { color: colors.border } },
    rightPriceScale: { borderColor: colors.border, mode: prefs.logScale ? LWC.PriceScaleMode.Logarithmic : LWC.PriceScaleMode.Normal },
    timeScale: { borderColor: colors.border, timeVisible: false },
    crosshair: { mode: prefs.magnet ? LWC.CrosshairMode.Magnet : LWC.CrosshairMode.Normal },
  });

  const candleSeries: Lwc = chart.addSeries(LWC.CandlestickSeries, { upColor: colors.up, downColor: colors.down, wickUpColor: colors.up, wickDownColor: colors.down, borderVisible: false });
  const barSeries: Lwc = chart.addSeries(LWC.BarSeries, { upColor: colors.up, downColor: colors.down });
  const lineSeries: Lwc = chart.addSeries(LWC.LineSeries, { color: colors.accent, lineWidth: 2 });
  const areaSeries: Lwc = chart.addSeries(LWC.AreaSeries, { lineColor: colors.accent, topColor: alpha(colors.accent, 0.22), bottomColor: alpha(colors.accent, 0), lineWidth: 2 });
  const baselineSeries: Lwc = chart.addSeries(LWC.BaselineSeries, {
    baseValue: { type: "price", price: bars[0].c }, lineWidth: 2,
    topLineColor: colors.up, topFillColor1: alpha(colors.up, 0.25), topFillColor2: alpha(colors.up, 0),
    bottomLineColor: colors.down, bottomFillColor1: alpha(colors.down, 0), bottomFillColor2: alpha(colors.down, 0.25),
  });
  const mainSeries: Record<ChartType, Lwc> = { candles: candleSeries, hollow: candleSeries, heikin: candleSeries, bars: barSeries, line: lineSeries, area: areaSeries, baseline: baselineSeries };
  const allMain = [candleSeries, barSeries, lineSeries, areaSeries, baselineSeries];

  const volumeSeries: Lwc = chart.addSeries(LWC.HistogramSeries, { priceFormat: { type: "volume" }, priceScaleId: "volume_scale" });
  const overlay = (color: string, title: string, dashed = false): Lwc =>
    chart.addSeries(LWC.LineSeries, { color, lineWidth: 1, lineStyle: dashed ? 2 : 0, priceLineVisible: false, lastValueVisible: false, title });
  const smaSeries = overlay(colors.sma, "SMA 20");
  const ema20Series = overlay(colors.ema20, "EMA 20");
  const emaSeries = overlay(colors.ema, "EMA 50");
  const bbUpper = overlay(colors.bb, "BB 20,2", true);
  const bbLower = overlay(colors.bb, "", true);
  const rsiSeries: Lwc = chart.addSeries(LWC.LineSeries, { color: colors.rsi, lineWidth: 1.5, priceScaleId: "rsi_scale", priceLineVisible: false, title: "RSI 14" });

  // ---- data -> series
  const points = (values: (number | null)[]) => {
    const intra = isIntraday(tf);
    const out: { time: string | number; value: number }[] = [];
    values.forEach((v, i) => {
      if (v !== null) out.push({ time: lwcTime(bars[i], intra), value: v });
    });
    return out;
  };

  const mainData = (type: ChartType) => {
    const intra = isIntraday(tf);
    if (type === "line" || type === "area" || type === "baseline") return bars.map((b) => ({ time: lwcTime(b, intra), value: b.c }));
    if (type === "bars") return bars.map((b) => ({ time: lwcTime(b, intra), open: b.o, high: b.h, low: b.l, close: b.c }));
    const src = type === "heikin" ? heikinAshi(bars) : bars;
    return src.map((b, i) => {
      const base = { time: lwcTime(b, intra), open: b.o, high: b.h, low: b.l, close: b.c };
      if (type !== "hollow") return base;
      // Hollow: colour follows the move against the previous close; the body is empty when the bar closed up.
      const prevClose = i > 0 ? src[i - 1].c : b.o;
      const col = b.c >= prevClose ? colors.up : colors.down;
      return { ...base, color: b.c >= b.o ? "rgba(0,0,0,0)" : col, borderColor: col, wickColor: col };
    });
  };

  const closes = () => bars.map((b) => b.c);
  let zonesLines: Lwc[] = [];
  let zonesOwner: Lwc | null = null;
  let targetLine: Lwc = null;
  let targetOwner: Lwc | null = null;

  const clearLines = () => {
    zonesLines.forEach((l) => { try { zonesOwner?.removePriceLine(l); } catch { /* gone */ } });
    zonesLines = [];
    if (targetLine) { try { targetOwner?.removePriceLine(targetLine); } catch { /* gone */ } targetLine = null; }
  };
  const drawLines = () => {
    clearLines();
    const owner = mainSeries[prefs.chartType];
    zonesOwner = owner;
    targetOwner = owner;
    if (prefs.indicators.zones) {
      const z = swingZones(bars);
      if (z.resistance !== null) zonesLines.push(owner.createPriceLine({ price: z.resistance, color: colors.resistance, lineWidth: 1, lineStyle: 2, axisLabelVisible: true, title: "Resistance" }));
      if (z.support !== null) zonesLines.push(owner.createPriceLine({ price: z.support, color: colors.support, lineWidth: 1, lineStyle: 2, axisLabelVisible: true, title: "Support" }));
    }
    if (target) targetLine = owner.createPriceLine({ price: target, color: colors.target, lineWidth: 2, lineStyle: 1, axisLabelVisible: true, title: "My target" });
  };

  const syncMargins = () => {
    const showRsi = prefs.indicators.rsi && bars.length >= 15;
    chart.priceScale("right").applyOptions({ scaleMargins: showRsi ? { top: 0.06, bottom: 0.28 } : { top: 0.08, bottom: 0.14 } });
    chart.priceScale("volume_scale").applyOptions({ scaleMargins: showRsi ? { top: 0.56, bottom: 0.26 } : { top: 0.8, bottom: 0 } });
    chart.priceScale("rsi_scale").applyOptions({ scaleMargins: { top: 0.77, bottom: 0.02 } });
  };

  const applyVisibility = () => {
    const enough = (id: IndicatorId) => bars.length >= (INDICATORS.find((i) => i.id === id)?.minBars ?? 1);
    allMain.forEach((s) => s.applyOptions({ visible: s === mainSeries[prefs.chartType] }));
    candleSeries.applyOptions({ borderVisible: prefs.chartType === "hollow" });
    volumeSeries.applyOptions({ visible: prefs.indicators.vol });
    smaSeries.applyOptions({ visible: prefs.indicators.sma && enough("sma") });
    ema20Series.applyOptions({ visible: prefs.indicators.ema20 && enough("ema20") });
    emaSeries.applyOptions({ visible: prefs.indicators.ema && enough("ema") });
    bbUpper.applyOptions({ visible: prefs.indicators.bb && enough("bb") });
    bbLower.applyOptions({ visible: prefs.indicators.bb && enough("bb") });
    rsiSeries.applyOptions({ visible: prefs.indicators.rsi && enough("rsi") });
    syncMargins();
  };

  let rsiValues: (number | null)[] = [];
  const setAllData = () => {
    const intra = isIntraday(tf);
    timeIndex = new Map(bars.map((b, i) => [lwcTime(b, intra), i]));
    chart.applyOptions({ timeScale: { timeVisible: intra, secondsVisible: false } });
    // Only the visible price series needs its data; the others are filled when chosen.
    allMain.forEach((s) => s.setData([]));
    mainSeries[prefs.chartType].setData(mainData(prefs.chartType));
    volumeSeries.setData(bars.map((b) => ({ time: lwcTime(b, intra), value: b.v, color: alpha(b.c >= b.o ? colors.up : colors.down, 0.25) })));
    smaSeries.setData(points(sma(closes(), 20)));
    ema20Series.setData(points(ema(closes(), 20)));
    emaSeries.setData(points(ema(closes(), 50)));
    const bb = bollinger(closes(), 20, 2);
    bbUpper.setData(points(bb.upper));
    bbLower.setData(points(bb.lower));
    rsiValues = rsi(closes(), 14);
    rsiSeries.setData(points(rsiValues));
    applyVisibility();
    drawLines();
  };

  // ---- range
  const rangeStartIndex = (id: string): number => {
    const def = RANGES.find((r) => r.id === id);
    const last = bars[bars.length - 1];
    if (!def || def.days === null) return 0;
    const from = def.id === "1D" ? last.t - (last.t % 86400) - IST_OFFSET_SEC + IST_OFFSET_SEC : last.t - def.days * 86400;
    const idx = def.id === "1D" ? bars.findIndex((b) => istDate(b.t) === istDate(last.t)) : bars.findIndex((b) => b.t >= from);
    return idx < 0 ? 0 : idx;
  };
  const setRange = (id: string) => {
    rangeId = id;
    const from = rangeStartIndex(id);
    try {
      if (from <= 0) chart.timeScale().fitContent();
      else chart.timeScale().setVisibleLogicalRange({ from: from - 0.5, to: bars.length - 1 + 2 });
    } catch {
      chart.timeScale().fitContent();
    }
    baselineSeries.applyOptions({ baseValue: { type: "price", price: bars[Math.min(from, bars.length - 1)].c } });
    refreshSummary();
  };

  // ---- text summary (for screen readers) and data table
  const summary = el("p", "blc-sr");
  summary.setAttribute("aria-live", "polite");
  const tableDetails = el("details", "blc-table");
  tableDetails.append(el("summary", undefined, "Show recent prices as a table"));
  tableDetails.addEventListener("toggle", () => {
    if (!tableDetails.open) return;
    const table = el("table");
    const head = el("tr");
    ["Date", "Open", "High", "Low", "Close", "Volume"].forEach((h) => head.append(el("th", undefined, h)));
    table.append(head);
    bars.slice(-20).reverse().forEach((b) => {
      const tr = el("tr");
      [istDate(b.t), fmtNum(b.o), fmtNum(b.h), fmtNum(b.l), fmtNum(b.c), fmtVol(b.v)].forEach((c) => tr.append(el("td", undefined, c)));
      table.append(tr);
    });
    tableDetails.querySelector("table")?.remove();
    tableDetails.append(table);
  });
  function refreshSummary() {
    const from = rangeStartIndex(rangeId);
    const view = bars.slice(from);
    const last = view[view.length - 1];
    const first = view[0];
    const hi = Math.max(...view.map((b) => b.h));
    const lo = Math.min(...view.map((b) => b.l));
    const chg = first.o ? ((last.c / first.o - 1) * 100).toFixed(2) : "0.00";
    const text = `${adapter.symbol} ${TIMEFRAME_LABEL[tf]} chart, ${view.length} bars from ${istDate(first.t)} to ${istDate(last.t)}. Last close ${fmtNum(last.c)}, ${chg}% over the range, high ${fmtNum(hi)}, low ${fmtNum(lo)}.`;
    summary.textContent = text;
    canvasWrap.setAttribute("aria-label", text);
  }

  // ---- HUD
  const hud = el("div", "blc-hud");
  const updateHud = (idx: number | null) => {
    const i = idx ?? bars.length - 1;
    const b = bars[i];
    const prev = i > 0 ? bars[i - 1].c : null;
    const chg = prev ? (b.c / prev - 1) * 100 : 0;
    const items: [string, string, string?][] = [
      [isIntraday(tf) ? "Time:" : "Date:", isIntraday(tf) ? `${istDate(b.t)} ${new Date((b.t + IST_OFFSET_SEC) * 1000).toISOString().slice(11, 16)}` : istDate(b.t)],
      ["O:", fmtNum(b.o)], ["H:", fmtNum(b.h)], ["L:", fmtNum(b.l)], ["C:", fmtNum(b.c)], ["Vol:", fmtVol(b.v)],
      ["Chg:", `${chg >= 0 ? "+" : ""}${chg.toFixed(2)}%`, chg >= 0 ? colors.up : colors.down],
    ];
    const r = rsiValues[i];
    if (prefs.indicators.rsi && r != null) items.push(["RSI(14):", r.toFixed(2), r >= 70 ? colors.down : r <= 30 ? colors.up : undefined]);
    hud.replaceChildren(
      ...items.map(([label, val, col]) => {
        const span = el("span", undefined, `${label} `);
        const strong = el("strong", undefined, val);
        if (col) strong.style.color = col;
        span.append(strong);
        return span;
      }),
    );
  };
  chart.subscribeCrosshairMove((param: { time?: string | number; seriesData?: Map<unknown, unknown> }) => {
    if (!param?.time || !param.seriesData) return updateHud(null);
    updateHud(timeIndex.get(param.time) ?? null);
  });

  // ---- toolbar
  const chipGroup = (label: string) => {
    const g = el("div", "blc-chips");
    g.setAttribute("role", "group");
    g.setAttribute("aria-label", label);
    return g;
  };
  const chip = (label: string, pressed: boolean, onClick: () => void, title?: string) => {
    const b = el("button", "blc-chip", label);
    b.type = "button";
    b.setAttribute("aria-pressed", String(pressed));
    if (title) b.title = title;
    b.addEventListener("click", onClick);
    return b;
  };
  const exclusive = (group: HTMLElement, btn: HTMLElement) => {
    group.querySelectorAll(".blc-chip").forEach((c) => c.setAttribute("aria-pressed", "false"));
    btn.setAttribute("aria-pressed", "true");
  };

  const toolbar = el("div", "blc-bars");
  const row1 = el("div", "blc-row");
  const row2 = el("div", "blc-row");

  const tfGroup = chipGroup("Timeframe");
  const rangeGroup = chipGroup("Time range");
  const typeGroup = chipGroup("Chart type");

  const tfList: Timeframe[] = [...(adapter.intraday?.timeframes ?? []), "D", "W", "M"];
  const rebuildRanges = () => {
    rangeGroup.replaceChildren();
    const span = bars[bars.length - 1].t - bars[0].t;
    RANGES.filter((r) => !r.intradayOnly || isIntraday(tf)).forEach((r) => {
      const b = chip(r.label, r.id === rangeId, () => { exclusive(rangeGroup, b); setRange(r.id); });
      if (r.days !== null && span < r.days * 86400 * 0.9) {
        b.disabled = true;
        b.title = `Needs about ${r.label} of history (${Math.round(span / 86400)} days on record)`;
      }
      rangeGroup.append(b);
    });
  };
  const switchTimeframe = async (next: Timeframe) => {
    let nextBars: Bar[];
    if (isIntraday(next)) {
      const cached = intradayCache.get(next);
      nextBars = cached ?? (await adapter.intraday!.load(next));
      intradayCache.set(next, nextBars);
    } else {
      nextBars = resampleDaily(daily, next as "D" | "W" | "M");
    }
    if (nextBars.length < 2) return;
    tf = next;
    bars = nextBars;
    rangeId = isIntraday(tf) ? "5D" : DEFAULT_RANGE[tf] ?? "6M";
    setAllData();
    rebuildRanges();
    refreshIndicatorChips();
    setRange(rangeId);
    updateHud(null);
    tfGroup.querySelectorAll(".blc-chip").forEach((c) => c.setAttribute("aria-pressed", String(c.textContent === TIMEFRAME_LABEL[tf])));
    savePrefsNow();
  };
  tfList.forEach((t) => {
    const b = chip(TIMEFRAME_LABEL[t], t === tf, () => { void switchTimeframe(t); }, t === "W" || t === "M" || t === "D" ? "Bars computed from daily closes" : undefined);
    if (!isIntraday(t) && resampleDaily(daily, t as "D" | "W" | "M").length < 2) b.disabled = true;
    tfGroup.append(b);
  });

  CHART_TYPES.forEach((t) => {
    const b = chip(t.label, prefs.chartType === t.id, () => {
      exclusive(typeGroup, b);
      prefs.chartType = t.id;
      allMain.forEach((s) => s.setData([]));
      mainSeries[t.id].setData(mainData(t.id));
      applyVisibility();
      drawLines();
      savePrefsNow();
    }, t.id === "heikin" ? "Heikin-Ashi smooths the candles; indicators still use real prices" : undefined);
    typeGroup.append(b);
  });

  const indicatorGroup = chipGroup("Indicators");
  const indicatorChips = new Map<IndicatorId, HTMLButtonElement>();
  // Pressed follows the saved choice; disabled follows whether the current timeframe has enough bars.
  const refreshIndicatorChips = () => {
    INDICATORS.forEach((ind) => {
      const b = indicatorChips.get(ind.id);
      if (!b) return;
      const short = bars.length < ind.minBars;
      b.disabled = short;
      b.title = short ? `Needs ${ind.minBars} bars (${bars.length} on this timeframe)` : "";
      b.setAttribute("aria-pressed", String(prefs.indicators[ind.id]));
    });
  };
  INDICATORS.forEach((ind) => {
    const b = chip(ind.label, prefs.indicators[ind.id], () => {
      const on = b.getAttribute("aria-pressed") !== "true";
      b.setAttribute("aria-pressed", String(on));
      prefs.indicators[ind.id] = on;
      applyVisibility();
      if (ind.id === "zones") drawLines();
      if (ind.id === "rsi") updateHud(null);
      savePrefsNow();
    });
    indicatorChips.set(ind.id, b);
    indicatorGroup.append(b);
  });
  refreshIndicatorChips();

  const tools = chipGroup("Chart tools");
  const targetWrap = el("div", "blc-target");
  const targetInput = el("input", "blc-input");
  targetInput.type = "number"; targetInput.step = "0.05"; targetInput.min = "0.05";
  targetInput.placeholder = "Target price";
  targetInput.setAttribute("aria-label", "Your own target price line");
  if (target) targetInput.value = String(target);
  const targetSet = chip(target ? "Update" : "+ Target", false, () => {
    const val = parseFloat(targetInput.value);
    if (!Number.isFinite(val) || val <= 0) return;
    target = val; saveTarget(adapter.symbol, val); targetSet.textContent = "Update"; targetClear.hidden = false; drawLines();
  });
  const targetClear = chip("×", false, () => {
    target = null; saveTarget(adapter.symbol, null); targetInput.value = ""; targetSet.textContent = "+ Target"; targetClear.hidden = true; drawLines();
  }, "Remove your target line");
  targetClear.hidden = !target;
  targetInput.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); targetSet.click(); } });
  targetWrap.append(targetInput, targetSet, targetClear);

  const logBtn = chip("Log", prefs.logScale, () => {
    prefs.logScale = logBtn.getAttribute("aria-pressed") !== "true";
    logBtn.setAttribute("aria-pressed", String(prefs.logScale));
    chart.priceScale("right").applyOptions({ mode: prefs.logScale ? LWC.PriceScaleMode.Logarithmic : LWC.PriceScaleMode.Normal });
    savePrefsNow();
  }, "Logarithmic price scale");
  const magBtn = chip("Magnet", prefs.magnet, () => {
    prefs.magnet = magBtn.getAttribute("aria-pressed") !== "true";
    magBtn.setAttribute("aria-pressed", String(prefs.magnet));
    chart.applyOptions({ crosshair: { mode: prefs.magnet ? LWC.CrosshairMode.Magnet : LWC.CrosshairMode.Normal } });
    savePrefsNow();
  }, "Snap the crosshair to open, high, low and close");
  const expandBtn = chip("Expand", false, () => {
    const on = !host.classList.contains("blc-expanded");
    host.classList.toggle("blc-expanded", on);
    expandBtn.setAttribute("aria-pressed", String(on));
    expandBtn.textContent = on ? "Close" : "Expand";
    chart.applyOptions({ height: on ? Math.max(380, window.innerHeight - 230) : opts.height ?? 360, width: canvasWrap.clientWidth || host.clientWidth });
    setTimeout(() => chart.timeScale().fitContent(), 40);
  }, "Larger view");
  const pngBtn = chip("Save PNG", false, () => {
    try {
      const canvas = chart.takeScreenshot();
      if (!canvas) return;
      const a = document.createElement("a");
      a.download = `${adapter.symbol}-chart.png`;
      a.href = canvas.toDataURL("image/png");
      a.click();
    } catch { /* not supported here */ }
  }, "Download a picture of the chart");
  tools.append(targetWrap, logBtn, magBtn, expandBtn, pngBtn);

  row1.append(tfGroup, rangeGroup, typeGroup);
  row2.append(indicatorGroup, tools);
  toolbar.append(row1, row2);

  host.replaceChildren(hud, toolbar, canvasWrap, summary, tableDetails);

  // ---- first paint
  rebuildRanges();
  setAllData();
  setRange(rangeId);
  updateHud(null);

  // ---- lifecycle
  const ro = new ResizeObserver(() => chart.applyOptions({ width: canvasWrap.clientWidth }));
  ro.observe(canvasWrap);
  disposers.push(() => ro.disconnect());

  const retheme = () => {
    colors = themeColors();
    chart.applyOptions({ layout: { textColor: colors.text }, grid: { horzLines: { color: colors.border } }, rightPriceScale: { borderColor: colors.border }, timeScale: { borderColor: colors.border } });
    candleSeries.applyOptions({ upColor: colors.up, downColor: colors.down, wickUpColor: colors.up, wickDownColor: colors.down });
    barSeries.applyOptions({ upColor: colors.up, downColor: colors.down });
    lineSeries.applyOptions({ color: colors.accent });
    setAllData();
  };
  const mo = new MutationObserver(retheme);
  mo.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme", "class"] });
  const mq = window.matchMedia("(prefers-color-scheme: dark)");
  mq.addEventListener("change", retheme);
  disposers.push(() => { mo.disconnect(); mq.removeEventListener("change", retheme); });

  const onKey = (e: KeyboardEvent) => { if (e.key === "Escape" && host.classList.contains("blc-expanded")) expandBtn.click(); };
  document.addEventListener("keydown", onKey);
  disposers.push(() => document.removeEventListener("keydown", onKey));

  return {
    destroy() {
      disposers.forEach((d) => d());
      try { chart.remove(); } catch { /* already gone */ }
      host.replaceChildren();
      host.classList.remove("blc", "blc-expanded");
    },
    setTimeframe: switchTimeframe,
  };
}

// ------------------------------------------------------------- adapters

/** The paper app's /api/history/<symbol>: columnar, adjusted, capped at the practice date. */
export function columnsAdapter(symbol: string, url: string): DataAdapter {
  return {
    symbol,
    async loadDaily() {
      const res = await fetch(url, { credentials: "same-origin" });
      if (!res.ok) throw new Error(`history ${res.status}`);
      return barsFromColumns((await res.json()) as DailyColumns);
    },
  };
}

/** The main site's static /data/equity-history/<slug>.json. */
export function candleFileAdapter(symbol: string, url: string): DataAdapter {
  return {
    symbol,
    async loadDaily() {
      const res = await fetch(url);
      if (!res.ok) throw new Error(`history ${res.status}`);
      return barsFromCandles((await res.json()) as CandleFile);
    },
  };
}
