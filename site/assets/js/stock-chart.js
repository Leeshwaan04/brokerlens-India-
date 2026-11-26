/* Price history Custom Charting Studio for stock pages, backed by
 * /data/equity-history/<slug>.json (real daily OHLCV from NSE's own
 * bhavcopy - see pipeline/sources/nse.py's equity_history()).
 *
 * Self-hosted TradingView Lightweight Charts v5.2.1 (Apache-2.0) with:
 * - Chart types: Candles, Line, Area, Baseline
 * - Technical indicators: SMA 20, EMA 20, EMA 50, Bollinger, RSI 14, Smart Zones, Volume
 * - Custom tools: Target Price Line (persisted), Log scale, Magnet crosshair, Expand, PNG Export
 */

const RANGES = [
  { label: '1W', bars: 5 },
  { label: '1M', bars: 22 },
  { label: '3M', bars: 65 },
  { label: '6M', bars: 120 },
  { label: 'All', bars: null },
];

const CHART_TYPES = [
  { id: 'candles', label: 'Candles' },
  { id: 'line', label: 'Line' },
  { id: 'area', label: 'Area' },
  { id: 'baseline', label: 'Baseline' },
];

const PREFS_KEY = 'bl_chart_prefs_v1';
const TARGETS_KEY = 'bl_chart_targets_v1';

function loadPrefs() {
  try {
    const raw = localStorage.getItem(PREFS_KEY);
    if (!raw) return null;
    const p = JSON.parse(raw);
    return p && typeof p === 'object' ? p : null;
  } catch {
    return null;
  }
}

function savePrefs(prefs) {
  try {
    localStorage.setItem(PREFS_KEY, JSON.stringify(prefs));
  } catch {
    /* ignore */
  }
}

function loadTarget(slug) {
  try {
    const raw = localStorage.getItem(TARGETS_KEY);
    if (!raw) return null;
    const map = JSON.parse(raw);
    const val = map && typeof map === 'object' ? Number(map[slug]) : NaN;
    return Number.isFinite(val) && val > 0 ? val : null;
  } catch {
    return null;
  }
}

function saveTarget(slug, price) {
  try {
    const raw = localStorage.getItem(TARGETS_KEY);
    const map = raw ? JSON.parse(raw) : {};
    if (price && Number.isFinite(price) && price > 0) {
      map[slug] = price;
    } else {
      delete map[slug];
    }
    localStorage.setItem(TARGETS_KEY, JSON.stringify(map));
  } catch {
    /* ignore */
  }
}

function themeColors() {
  const s = getComputedStyle(document.documentElement);
  const v = (name, fallback) => (s.getPropertyValue(name) || fallback).trim();
  return {
    bg: v('--bg-raised', '#ffffff'),
    text: v('--text-muted', '#6b7280'),
    border: v('--border', '#e5e7eb'),
    up: v('--up', '#0f7a4d'),
    down: v('--down', '#c0392b'),
    upSoft: 'rgba(15, 122, 77, 0.25)',
    downSoft: 'rgba(192, 57, 43, 0.25)',
    accent: v('--accent', '#2f4a8f'),
    accentSoft: 'rgba(47, 74, 143, 0.18)',
    sma: '#2563eb',
    ema20: '#0ea5e9',
    ema: '#d97706',
    bb: '#7c3aed',
    rsi: '#ec4899',
    resistance: '#dc2626',
    support: '#059669',
    target: '#f59e0b',
  };
}

function toCandleData(candles) {
  return candles
    .filter((c) => c.date != null && c.open != null && c.high != null && c.low != null && c.close != null)
    .map((c) => ({
      time: c.date,
      open: c.open,
      high: c.high,
      low: c.low,
      close: c.close,
      volume: c.volume || 0,
    }));
}

function toLineData(points) {
  return points.map((p) => ({ time: p.time, value: p.close }));
}

function toVolumeData(candles, colors) {
  return candles
    .filter((c) => c.date != null && c.volume != null)
    .map((c) => ({
      time: c.date,
      value: c.volume,
      color: c.close >= c.open ? colors.upSoft : colors.downSoft,
    }));
}

/* Technical Indicator Mathematics */
function calcSMA(points, period) {
  if (points.length < period) return [];
  const result = [];
  let sum = 0;
  for (let i = 0; i < points.length; i++) {
    sum += points[i].close;
    if (i >= period) {
      sum -= points[i - period].close;
    }
    if (i >= period - 1) {
      result.push({
        time: points[i].time,
        value: parseFloat((sum / period).toFixed(2)),
      });
    }
  }
  return result;
}

function calcEMA(points, period) {
  if (points.length < period) return [];
  const k = 2 / (period + 1);
  const result = [];
  let sum = 0;
  for (let i = 0; i < period; i++) {
    sum += points[i].close;
  }
  let prevEma = sum / period;
  result.push({ time: points[period - 1].time, value: parseFloat(prevEma.toFixed(2)) });

  for (let i = period; i < points.length; i++) {
    const currentEma = points[i].close * k + prevEma * (1 - k);
    result.push({
      time: points[i].time,
      value: parseFloat(currentEma.toFixed(2)),
    });
    prevEma = currentEma;
  }
  return result;
}

function calcBollinger(points, period = 20, multiplier = 2) {
  if (points.length < period) return { upper: [], lower: [] };
  const upper = [];
  const lower = [];

  for (let i = period - 1; i < points.length; i++) {
    let sum = 0;
    for (let j = i - period + 1; j <= i; j++) {
      sum += points[j].close;
    }
    const mean = sum / period;

    let varianceSum = 0;
    for (let j = i - period + 1; j <= i; j++) {
      varianceSum += Math.pow(points[j].close - mean, 2);
    }
    const stdDev = Math.sqrt(varianceSum / period);

    upper.push({
      time: points[i].time,
      value: parseFloat((mean + multiplier * stdDev).toFixed(2)),
    });
    lower.push({
      time: points[i].time,
      value: parseFloat((mean - multiplier * stdDev).toFixed(2)),
    });
  }
  return { upper, lower };
}

function calcRSI(points, period = 14) {
  if (points.length <= period) return [];
  const result = [];
  let gains = 0;
  let losses = 0;
  for (let i = 1; i <= period; i++) {
    const diff = points[i].close - points[i - 1].close;
    if (diff >= 0) gains += diff;
    else losses -= diff;
  }
  let avgGain = gains / period;
  let avgLoss = losses / period;
  const firstRs = avgLoss === 0 ? 100 : avgGain / avgLoss;
  const firstRsi = avgLoss === 0 ? 100 : 100 - 100 / (1 + firstRs);
  result.push({ time: points[period].time, value: parseFloat(firstRsi.toFixed(2)) });

  for (let i = period + 1; i < points.length; i++) {
    const diff = points[i].close - points[i - 1].close;
    const gain = diff > 0 ? diff : 0;
    const loss = diff < 0 ? -diff : 0;
    avgGain = (avgGain * (period - 1) + gain) / period;
    avgLoss = (avgLoss * (period - 1) + loss) / period;
    const rs = avgLoss === 0 ? 100 : avgGain / avgLoss;
    const rsi = avgLoss === 0 ? 100 : 100 - 100 / (1 + rs);
    result.push({ time: points[i].time, value: parseFloat(rsi.toFixed(2)) });
  }
  return result;
}

/* Automated Technical Analysis: Smart Zones (Support / Resistance) */
function calcSmartZones(points) {
  if (points.length < 5) return null;
  const lastClose = points[points.length - 1].close;

  let pivotHighs = [];
  let pivotLows = [];

  for (const lb of [8, 4, 2]) {
    pivotHighs = [];
    pivotLows = [];
    for (let i = lb; i < points.length - lb; i++) {
      let isHigh = true;
      let isLow = true;
      for (let j = i - lb; j <= i + lb; j++) {
        if (j === i) continue;
        if (points[j].high > points[i].high) isHigh = false;
        if (points[j].low < points[i].low) isLow = false;
      }
      if (isHigh) pivotHighs.push(points[i].high);
      if (isLow) pivotLows.push(points[i].low);
    }
    const res = pivotHighs.filter((p) => p > lastClose);
    const sup = pivotLows.filter((p) => p < lastClose);
    if (res.length > 0 && sup.length > 0) break;
  }

  const resistances = pivotHighs.filter((p) => p > lastClose).sort((a, b) => a - b);
  const supports = pivotLows.filter((p) => p < lastClose).sort((a, b) => b - a);

  const allHigh = Math.max(...points.map((p) => p.high));
  const allLow = Math.min(...points.map((p) => p.low));

  let resVal = resistances.length ? resistances[0] : (allHigh > lastClose ? allHigh : null);
  let resTitle = 'Resistance';
  if (!resVal && allHigh <= lastClose) {
    resVal = parseFloat((lastClose * 1.05).toFixed(2));
    resTitle = 'Breakout Zone (+5%)';
  }

  let supVal = supports.length ? supports[0] : (allLow < lastClose ? allLow : null);
  let supTitle = 'Support';
  if (!supVal && allLow >= lastClose) {
    supVal = parseFloat((lastClose * 0.95).toFixed(2));
    supTitle = 'Breakdown Floor (-5%)';
  }

  return {
    resistance: resVal,
    resistanceTitle: resTitle,
    support: supVal,
    supportTitle: supTitle,
  };
}

function fmtNum(n) {
  if (n == null) return '-';
  return Number(n).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function fmtVol(n) {
  if (n == null) return '-';
  if (n >= 1e7) return (n / 1e7).toFixed(2) + ' Cr';
  if (n >= 1e5) return (n / 1e5).toFixed(2) + ' L';
  if (n >= 1e3) return (n / 1e3).toFixed(1) + ' K';
  return String(n);
}

async function loadHistory(slug) {
  const r = await fetch(`/data/equity-history/${slug}.json`);
  if (!r.ok) throw new Error(`equity-history -> ${r.status}`);
  return r.json();
}

function buildToolbar(points, state, callbacks) {
  const wrap = document.createElement('div');
  wrap.className = 'chart-studio-bars';

  // Row 1: Timeframes + Chart Type
  const row1 = document.createElement('div');
  row1.className = 'chart-toolbar';

  const totalPoints = points ? points.length : 0;
  let defaultActiveIndex = RANGES.length - 1;
  if (totalPoints >= 22) {
    defaultActiveIndex = RANGES.findIndex((r) => r.label === '1M');
  } else if (totalPoints >= 5) {
    defaultActiveIndex = RANGES.findIndex((r) => r.label === '1W');
  }
  if (defaultActiveIndex < 0) defaultActiveIndex = RANGES.length - 1;

  const rangeGroup = document.createElement('div');
  rangeGroup.className = 'chips';
  rangeGroup.setAttribute('role', 'group');
  rangeGroup.setAttribute('aria-label', 'Chart time range');
  RANGES.forEach((r, i) => {
    const btn = document.createElement('button');
    btn.className = 'chip';
    btn.type = 'button';
    if (r.bars != null && totalPoints < r.bars) {
      btn.disabled = true;
      btn.title = `Requires at least ${r.bars} trading sessions (${totalPoints} on record)`;
      btn.style.opacity = '0.4';
      btn.style.cursor = 'not-allowed';
    }
    btn.setAttribute('aria-pressed', i === defaultActiveIndex ? 'true' : 'false');
    btn.textContent = r.label;
    btn.addEventListener('click', () => {
      if (btn.disabled) return;
      rangeGroup.querySelectorAll('.chip').forEach((c) => c.setAttribute('aria-pressed', 'false'));
      btn.setAttribute('aria-pressed', 'true');
      callbacks.onRangeSelect(r.bars);
    });
    rangeGroup.appendChild(btn);
  });

  // Chart Type selector
  const typeGroup = document.createElement('div');
  typeGroup.className = 'chips';
  typeGroup.setAttribute('role', 'group');
  typeGroup.setAttribute('aria-label', 'Chart type');
  CHART_TYPES.forEach((t) => {
    const btn = document.createElement('button');
    btn.className = 'chip';
    btn.type = 'button';
    btn.setAttribute('aria-pressed', state.chartType === t.id ? 'true' : 'false');
    btn.textContent = t.label;
    btn.addEventListener('click', () => {
      typeGroup.querySelectorAll('.chip').forEach((c) => c.setAttribute('aria-pressed', 'false'));
      btn.setAttribute('aria-pressed', 'true');
      callbacks.onTypeSelect(t.id);
    });
    typeGroup.appendChild(btn);
  });

  row1.appendChild(rangeGroup);
  row1.appendChild(typeGroup);

  // Row 2: Indicators + Custom Studio Tools
  const row2 = document.createElement('div');
  row2.className = 'chart-toolbar';

  const indicatorGroup = document.createElement('div');
  indicatorGroup.className = 'chips';
  indicatorGroup.setAttribute('role', 'group');
  indicatorGroup.setAttribute('aria-label', 'Technical indicators');

  const indicators = [
    { id: 'sma', label: 'SMA 20', minPoints: 20 },
    { id: 'ema20', label: 'EMA 20', minPoints: 20 },
    { id: 'ema', label: 'EMA 50', minPoints: 50 },
    { id: 'bb', label: 'Bollinger', minPoints: 20 },
    { id: 'rsi', label: 'RSI 14', minPoints: 15 },
    { id: 'zones', label: 'Smart Zones', minPoints: 5 },
    { id: 'vol', label: 'Volume', minPoints: 1 },
  ];

  indicators.forEach((ind) => {
    const btn = document.createElement('button');
    btn.className = 'chip';
    btn.type = 'button';
    const disabled = points && points.length < ind.minPoints;
    if (disabled) {
      btn.disabled = true;
      btn.title = `Requires ${ind.minPoints} trading sessions (holds ${points.length})`;
      btn.style.opacity = '0.4';
      btn.style.cursor = 'not-allowed';
    }
    const isActive = !disabled && Boolean(state.indicators[ind.id]);
    btn.setAttribute('aria-pressed', isActive ? 'true' : 'false');
    btn.textContent = ind.label;
    btn.addEventListener('click', () => {
      if (btn.disabled) return;
      const active = btn.getAttribute('aria-pressed') === 'true';
      btn.setAttribute('aria-pressed', active ? 'false' : 'true');
      callbacks.onIndicatorToggle(ind.id, !active);
    });
    indicatorGroup.appendChild(btn);
  });

  // Custom Controls Group (Target, Log, Magnet, Expand, PNG)
  const toolsGroup = document.createElement('div');
  toolsGroup.className = 'chips chart-tools-group';
  toolsGroup.setAttribute('role', 'group');
  toolsGroup.setAttribute('aria-label', 'Chart customization tools');

  // Target Price Inline Input
  const targetWrap = document.createElement('div');
  targetWrap.className = 'chart-target-wrap';
  const targetInput = document.createElement('input');
  targetInput.type = 'number';
  targetInput.step = '0.05';
  targetInput.min = '0.05';
  targetInput.className = 'chart-target-input';
  targetInput.placeholder = 'Target price';
  targetInput.setAttribute('aria-label', 'Custom target price line');
  if (state.targetPrice) {
    targetInput.value = String(state.targetPrice);
  }
  const targetSetBtn = document.createElement('button');
  targetSetBtn.type = 'button';
  targetSetBtn.className = 'chip';
  targetSetBtn.textContent = state.targetPrice ? 'Update' : '+ Target';
  const targetClearBtn = document.createElement('button');
  targetClearBtn.type = 'button';
  targetClearBtn.className = 'chip';
  targetClearBtn.textContent = '×';
  targetClearBtn.title = 'Remove custom target line';
  targetClearBtn.hidden = !state.targetPrice;

  const applyTarget = () => {
    const val = parseFloat(targetInput.value);
    if (Number.isFinite(val) && val > 0) {
      callbacks.onTargetSet(val);
      targetSetBtn.textContent = 'Update';
      targetClearBtn.hidden = false;
    }
  };
  targetSetBtn.addEventListener('click', applyTarget);
  targetInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      applyTarget();
    }
  });
  targetClearBtn.addEventListener('click', () => {
    targetInput.value = '';
    targetSetBtn.textContent = '+ Target';
    targetClearBtn.hidden = true;
    callbacks.onTargetSet(null);
  });

  targetWrap.appendChild(targetInput);
  targetWrap.appendChild(targetSetBtn);
  targetWrap.appendChild(targetClearBtn);

  // Log Scale toggle
  const logBtn = document.createElement('button');
  logBtn.type = 'button';
  logBtn.className = 'chip';
  logBtn.textContent = 'Log';
  logBtn.title = 'Toggle Logarithmic Price Scale';
  logBtn.setAttribute('aria-pressed', state.logScale ? 'true' : 'false');
  logBtn.addEventListener('click', () => {
    const next = logBtn.getAttribute('aria-pressed') !== 'true';
    logBtn.setAttribute('aria-pressed', next ? 'true' : 'false');
    callbacks.onLogToggle(next);
  });

  // Magnet Crosshair toggle
  const magBtn = document.createElement('button');
  magBtn.type = 'button';
  magBtn.className = 'chip';
  magBtn.textContent = 'Magnet';
  magBtn.title = 'Snap crosshair to OHLC values';
  magBtn.setAttribute('aria-pressed', state.magnet ? 'true' : 'false');
  magBtn.addEventListener('click', () => {
    const next = magBtn.getAttribute('aria-pressed') !== 'true';
    magBtn.setAttribute('aria-pressed', next ? 'true' : 'false');
    callbacks.onMagnetToggle(next);
  });

  // Expand toggle
  const expandBtn = document.createElement('button');
  expandBtn.type = 'button';
  expandBtn.className = 'chip';
  expandBtn.textContent = 'Expand';
  expandBtn.title = 'Toggle Theater Chart View';
  expandBtn.setAttribute('aria-pressed', 'false');
  expandBtn.addEventListener('click', () => {
    const next = expandBtn.getAttribute('aria-pressed') !== 'true';
    expandBtn.setAttribute('aria-pressed', next ? 'true' : 'false');
    expandBtn.textContent = next ? 'Compact' : 'Expand';
    callbacks.onExpandToggle(next);
  });

  // Export PNG button
  const pngBtn = document.createElement('button');
  pngBtn.type = 'button';
  pngBtn.className = 'chip';
  pngBtn.textContent = 'Save PNG';
  pngBtn.title = 'Download chart snapshot as PNG';
  pngBtn.addEventListener('click', () => callbacks.onSavePng());

  toolsGroup.appendChild(targetWrap);
  toolsGroup.appendChild(logBtn);
  toolsGroup.appendChild(magBtn);
  toolsGroup.appendChild(expandBtn);
  toolsGroup.appendChild(pngBtn);

  row2.appendChild(indicatorGroup);
  row2.appendChild(toolsGroup);

  wrap.appendChild(row1);
  wrap.appendChild(row2);
  return wrap;
}

async function initChart(host) {
  const slug = host.dataset.symbol;
  const canvasWrap = document.createElement('div');
  canvasWrap.className = 'coin-chart-canvas';

  let candles;
  try {
    const data = await loadHistory(slug);
    candles = data.candles || [];
  } catch {
    canvasWrap.textContent = "Price history isn't available for this stock yet - it refreshes on the next site update.";
    canvasWrap.className = 'small faint';
    canvasWrap.style.padding = '24px 0';
    canvasWrap.style.textAlign = 'center';
    host.appendChild(canvasWrap);
    return;
  }
  const points = toCandleData(candles);
  if (points.length < 2) {
    canvasWrap.textContent = 'Not enough price history yet.';
    canvasWrap.className = 'small faint';
    canvasWrap.style.padding = '24px 0';
    canvasWrap.style.textAlign = 'center';
    host.appendChild(canvasWrap);
    return;
  }

  const LWC = window.LightweightCharts;
  if (!LWC) {
    canvasWrap.textContent = 'Chart library failed to load.';
    canvasWrap.className = 'small faint';
    canvasWrap.style.padding = '24px 0';
    canvasWrap.style.textAlign = 'center';
    host.appendChild(canvasWrap);
    return;
  }

  const saved = loadPrefs();
  const state = {
    chartType: saved && CHART_TYPES.some((t) => t.id === saved.chartType) ? saved.chartType : 'candles',
    logScale: Boolean(saved && saved.logScale),
    magnet: Boolean(saved && saved.magnet),
    targetPrice: loadTarget(slug),
    indicators: {
      sma: Boolean(saved && saved.indicators && saved.indicators.sma),
      ema20: Boolean(saved && saved.indicators && saved.indicators.ema20),
      ema: Boolean(saved && saved.indicators && saved.indicators.ema),
      bb: Boolean(saved && saved.indicators && saved.indicators.bb),
      rsi: Boolean(saved && saved.indicators && saved.indicators.rsi),
      zones: Boolean(saved && saved.indicators && saved.indicators.zones),
      vol: saved && saved.indicators && typeof saved.indicators.vol === 'boolean' ? saved.indicators.vol : true,
    },
  };

  const persistPrefs = () => {
    savePrefs({
      chartType: state.chartType,
      logScale: state.logScale,
      magnet: state.magnet,
      indicators: state.indicators,
    });
  };

  const hud = document.createElement('div');
  hud.className = 'chart-hud xs faint';
  hud.style.display = 'flex';
  hud.style.gap = '14px';
  hud.style.flexWrap = 'wrap';
  hud.style.padding = '4px 0 8px 0';
  hud.style.fontFamily = 'monospace';

  const colors = themeColors();
  const chart = LWC.createChart(canvasWrap, {
    width: host.clientWidth || undefined,
    height: 330,
    layout: { background: { type: 'solid', color: 'transparent' }, textColor: colors.text },
    grid: { vertLines: { visible: false }, horzLines: { color: colors.border } },
    rightPriceScale: {
      borderColor: colors.border,
      mode: state.logScale ? LWC.PriceScaleMode.Logarithmic : LWC.PriceScaleMode.Normal,
    },
    timeScale: { borderColor: colors.border },
    crosshair: { mode: state.magnet ? LWC.CrosshairMode.Magnet : LWC.CrosshairMode.Normal },
  });

  // Main Price Series (Candles, Line, Area, Baseline)
  const linePoints = toLineData(points);
  const candleSeries = chart.addSeries(LWC.CandlestickSeries, {
    upColor: colors.up,
    downColor: colors.down,
    borderVisible: false,
    wickUpColor: colors.up,
    wickDownColor: colors.down,
    visible: state.chartType === 'candles',
  });
  candleSeries.setData(points);

  const lineSeries = chart.addSeries(LWC.LineSeries, {
    color: colors.accent,
    lineWidth: 2,
    visible: state.chartType === 'line',
  });
  lineSeries.setData(linePoints);

  const areaSeries = chart.addSeries(LWC.AreaSeries, {
    lineColor: colors.accent,
    topColor: colors.accentSoft,
    bottomColor: 'rgba(47, 74, 143, 0.0)',
    lineWidth: 2,
    visible: state.chartType === 'area',
  });
  areaSeries.setData(linePoints);

  const baseIdx = Math.max(0, points.length - 22);
  const baselineSeries = chart.addSeries(LWC.BaselineSeries, {
    baseValue: { type: 'price', price: points[baseIdx].close },
    topLineColor: colors.up,
    topFillColor1: 'rgba(15, 122, 77, 0.25)',
    topFillColor2: 'rgba(15, 122, 77, 0.0)',
    bottomLineColor: colors.down,
    bottomFillColor1: 'rgba(192, 57, 43, 0.0)',
    bottomFillColor2: 'rgba(192, 57, 43, 0.25)',
    lineWidth: 2,
    visible: state.chartType === 'baseline',
  });
  baselineSeries.setData(linePoints);

  const activeMainSeries = () => {
    if (state.chartType === 'line') return lineSeries;
    if (state.chartType === 'area') return areaSeries;
    if (state.chartType === 'baseline') return baselineSeries;
    return candleSeries;
  };

  // Volume series
  const volumeSeries = chart.addSeries(LWC.HistogramSeries, {
    priceFormat: { type: 'volume' },
    priceScaleId: 'volume_scale',
    visible: state.indicators.vol,
  });
  chart.priceScale('volume_scale').applyOptions({
    scaleMargins: { top: 0.8, bottom: 0 },
  });
  volumeSeries.setData(toVolumeData(candles, colors));

  // Technical Indicator Series
  const smaSeries = chart.addSeries(LWC.LineSeries, {
    color: colors.sma,
    lineWidth: 1,
    lineStyle: 0,
    priceLineVisible: false,
    title: 'SMA 20',
    visible: state.indicators.sma && points.length >= 20,
  });
  smaSeries.setData(calcSMA(points, 20));

  const ema20Series = chart.addSeries(LWC.LineSeries, {
    color: colors.ema20,
    lineWidth: 1,
    lineStyle: 0,
    priceLineVisible: false,
    title: 'EMA 20',
    visible: state.indicators.ema20 && points.length >= 20,
  });
  ema20Series.setData(calcEMA(points, 20));

  const emaSeries = chart.addSeries(LWC.LineSeries, {
    color: colors.ema,
    lineWidth: 1,
    lineStyle: 0,
    priceLineVisible: false,
    title: 'EMA 50',
    visible: state.indicators.ema && points.length >= 50,
  });
  emaSeries.setData(calcEMA(points, 50));

  const bbUpperSeries = chart.addSeries(LWC.LineSeries, {
    color: colors.bb,
    lineWidth: 1,
    lineStyle: 2,
    priceLineVisible: false,
    title: 'BB Upper',
    visible: state.indicators.bb && points.length >= 20,
  });
  const bbLowerSeries = chart.addSeries(LWC.LineSeries, {
    color: colors.bb,
    lineWidth: 1,
    lineStyle: 2,
    priceLineVisible: false,
    title: 'BB Lower',
    visible: state.indicators.bb && points.length >= 20,
  });
  const bbData = calcBollinger(points, 20, 2);
  bbUpperSeries.setData(bbData.upper);
  bbLowerSeries.setData(bbData.lower);

  // RSI (14) Series in lower oscillator band
  const rsiData = calcRSI(points, 14);
  const rsiMap = new Map(rsiData.map((r) => [r.time, r.value]));
  const rsiSeries = chart.addSeries(LWC.LineSeries, {
    color: colors.rsi,
    lineWidth: 1.5,
    priceScaleId: 'rsi_scale',
    priceLineVisible: false,
    title: 'RSI 14',
    visible: state.indicators.rsi && points.length >= 15,
  });
  rsiSeries.setData(rsiData);

  const syncScaleMargins = () => {
    const showRsi = state.indicators.rsi && points.length >= 15;
    chart.priceScale('right').applyOptions({
      scaleMargins: showRsi ? { top: 0.06, bottom: 0.28 } : { top: 0.08, bottom: 0.14 },
    });
    chart.priceScale('volume_scale').applyOptions({
      scaleMargins: showRsi ? { top: 0.56, bottom: 0.26 } : { top: 0.8, bottom: 0 },
    });
    chart.priceScale('rsi_scale').applyOptions({
      scaleMargins: { top: 0.77, bottom: 0.02 },
    });
  };
  syncScaleMargins();

  // Smart Zones & Custom Target Price Lines
  const zones = calcSmartZones(points);
  let resistanceLine = null;
  let supportLine = null;
  let customTargetLine = null;

  const attachPriceLinesToSeries = (targetSeries) => {
    if (resistanceLine) {
      try { candleSeries.removePriceLine(resistanceLine); } catch {}
      try { lineSeries.removePriceLine(resistanceLine); } catch {}
      try { areaSeries.removePriceLine(resistanceLine); } catch {}
      try { baselineSeries.removePriceLine(resistanceLine); } catch {}
      resistanceLine = null;
    }
    if (supportLine) {
      try { candleSeries.removePriceLine(supportLine); } catch {}
      try { lineSeries.removePriceLine(supportLine); } catch {}
      try { areaSeries.removePriceLine(supportLine); } catch {}
      try { baselineSeries.removePriceLine(supportLine); } catch {}
      supportLine = null;
    }
    if (customTargetLine) {
      try { candleSeries.removePriceLine(customTargetLine); } catch {}
      try { lineSeries.removePriceLine(customTargetLine); } catch {}
      try { areaSeries.removePriceLine(customTargetLine); } catch {}
      try { baselineSeries.removePriceLine(customTargetLine); } catch {}
      customTargetLine = null;
    }

    if (state.indicators.zones && zones && points.length >= 5) {
      if (zones.resistance) {
        resistanceLine = targetSeries.createPriceLine({
          price: zones.resistance,
          color: colors.resistance,
          lineWidth: 1,
          lineStyle: 2,
          axisLabelVisible: true,
          title: zones.resistanceTitle || 'Resistance',
        });
      }
      if (zones.support) {
        supportLine = targetSeries.createPriceLine({
          price: zones.support,
          color: colors.support,
          lineWidth: 1,
          lineStyle: 2,
          axisLabelVisible: true,
          title: zones.supportTitle || 'Support',
        });
      }
    }

    if (state.targetPrice && Number.isFinite(state.targetPrice)) {
      customTargetLine = targetSeries.createPriceLine({
        price: state.targetPrice,
        color: colors.target,
        lineWidth: 2,
        lineStyle: 1,
        axisLabelVisible: true,
        title: 'My Target',
      });
    }
  };

  attachPriceLinesToSeries(activeMainSeries());

  // HUD Update Handler
  const lastPoint = points[points.length - 1];
  const updateHud = (p) => {
    const point = p || lastPoint;
    const idx = points.findIndex((q) => q.time === point.time);
    const fullPoint = idx >= 0 ? points[idx] : point;
    const prevClose = idx > 0 ? points[idx - 1].close : null;
    const chg = prevClose ? (((fullPoint.close - prevClose) / prevClose) * 100).toFixed(2) : '0.00';
    const sign = Number(chg) >= 0 ? '+' : '';
    const chgColor = Number(chg) >= 0 ? colors.up : colors.down;
    const rsiVal = rsiMap.get(fullPoint.time);

    hud.replaceChildren();
    const items = [
      ['Date:', String(fullPoint.time), ''],
      ['O:', fmtNum(fullPoint.open), ''],
      ['H:', fmtNum(fullPoint.high), ''],
      ['L:', fmtNum(fullPoint.low), ''],
      ['C:', fmtNum(fullPoint.close), ''],
      ['Vol:', fmtVol(fullPoint.volume), ''],
      ['Chg:', `${sign}${chg}%`, chgColor],
    ];
    if (state.indicators.rsi && rsiVal != null) {
      const rsiCol = rsiVal >= 70 ? colors.down : rsiVal <= 30 ? colors.up : '';
      items.push(['RSI(14):', String(rsiVal), rsiCol]);
    }

    items.forEach(([label, val, col]) => {
      const span = document.createElement('span');
      span.textContent = `${label} `;
      const strong = document.createElement('strong');
      strong.textContent = val;
      if (col) strong.style.color = col;
      span.appendChild(strong);
      hud.appendChild(span);
    });
  };
  updateHud(lastPoint);

  chart.subscribeCrosshairMove((param) => {
    if (!param || !param.time || !param.seriesData) {
      updateHud(lastPoint);
      return;
    }
    const cData = param.seriesData.get(candleSeries) || param.seriesData.get(activeMainSeries());
    if (cData) {
      updateHud(cData);
    }
  });

  const totalPoints = points ? points.length : 0;
  let defaultActiveIndex = RANGES.length - 1;
  if (totalPoints >= 22) {
    defaultActiveIndex = RANGES.findIndex((r) => r.label === '1M');
  } else if (totalPoints >= 5) {
    defaultActiveIndex = RANGES.findIndex((r) => r.label === '1W');
  }
  if (defaultActiveIndex < 0) defaultActiveIndex = RANGES.length - 1;

  const setRange = (bars) => {
    if (bars == null || bars >= points.length) {
      chart.timeScale().fitContent();
      return;
    }
    const fromIndex = Math.max(0, points.length - bars);
    try {
      chart.timeScale().setVisibleLogicalRange({
        from: fromIndex,
        to: Math.max(0, points.length - 1),
      });
    } catch {
      chart.timeScale().fitContent();
    }
  };

  const initialBars = RANGES[defaultActiveIndex]?.bars ?? null;
  setRange(initialBars);

  const callbacks = {
    onRangeSelect: setRange,
    onTypeSelect: (typeId) => {
      state.chartType = typeId;
      candleSeries.applyOptions({ visible: typeId === 'candles' });
      lineSeries.applyOptions({ visible: typeId === 'line' });
      areaSeries.applyOptions({ visible: typeId === 'area' });
      baselineSeries.applyOptions({ visible: typeId === 'baseline' });
      attachPriceLinesToSeries(activeMainSeries());
      persistPrefs();
    },
    onIndicatorToggle: (id, active) => {
      state.indicators[id] = active;
      if (id === 'sma') smaSeries.applyOptions({ visible: active });
      if (id === 'ema20') ema20Series.applyOptions({ visible: active });
      if (id === 'ema') emaSeries.applyOptions({ visible: active });
      if (id === 'bb') {
        bbUpperSeries.applyOptions({ visible: active });
        bbLowerSeries.applyOptions({ visible: active });
      }
      if (id === 'rsi') {
        rsiSeries.applyOptions({ visible: active });
        syncScaleMargins();
        updateHud(lastPoint);
      }
      if (id === 'zones') attachPriceLinesToSeries(activeMainSeries());
      if (id === 'vol') volumeSeries.applyOptions({ visible: active });
      persistPrefs();
    },
    onTargetSet: (price) => {
      state.targetPrice = price;
      saveTarget(slug, price);
      attachPriceLinesToSeries(activeMainSeries());
    },
    onLogToggle: (log) => {
      state.logScale = log;
      chart.priceScale('right').applyOptions({
        mode: log ? LWC.PriceScaleMode.Logarithmic : LWC.PriceScaleMode.Normal,
      });
      persistPrefs();
    },
    onMagnetToggle: (mag) => {
      state.magnet = mag;
      chart.applyOptions({
        crosshair: { mode: mag ? LWC.CrosshairMode.Magnet : LWC.CrosshairMode.Normal },
      });
      persistPrefs();
    },
    onExpandToggle: (expanded) => {
      const card = host.closest('.card') || host;
      card.classList.toggle('chart-card-expanded', expanded);
      chart.applyOptions({
        height: expanded ? Math.min(560, Math.max(380, window.innerHeight - 240)) : 330,
        width: canvasWrap.clientWidth || host.clientWidth,
      });
      setTimeout(() => chart.timeScale().fitContent(), 50);
    },
    onSavePng: () => {
      try {
        const canvas = chart.takeScreenshot();
        if (!canvas) return;
        const link = document.createElement('a');
        link.download = `${slug}-chart.png`;
        link.href = canvas.toDataURL('image/png');
        link.click();
      } catch {
        /* ignore */
      }
    },
  };

  host.appendChild(hud);
  const toolbar = buildToolbar(points, state, callbacks);
  host.appendChild(toolbar);
  host.appendChild(canvasWrap);

  if (points.length < 22) {
    const notice = document.createElement('div');
    notice.className = 'xs muted';
    notice.style.margin = '6px 0 2px 0';
    notice.textContent = `Showing all ${points.length} trading sessions on record (since ${points[0].time}). Longer timeframes unlock as additional exchange sessions accumulate.`;
    host.appendChild(notice);
  }

  const ro = new ResizeObserver(() => chart.applyOptions({ width: canvasWrap.clientWidth }));
  ro.observe(canvasWrap);

  window.addEventListener('resize', () => {
    const c = themeColors();
    chart.applyOptions({
      layout: { textColor: c.text },
      grid: { horzLines: { color: c.border } },
      rightPriceScale: { borderColor: c.border },
      timeScale: { borderColor: c.border },
    });
    candleSeries.applyOptions({
      upColor: c.up,
      downColor: c.down,
      wickUpColor: c.up,
      wickDownColor: c.down,
    });
    volumeSeries.setData(toVolumeData(candles, c));
  });
}

document.querySelectorAll('[data-stock-chart]').forEach(initChart);
