/* Price history chart for a single stock page, backed by
 * /data/equity-history/<slug>.json (real daily OHLCV from NSE's own
 * bhavcopy - see pipeline/sources/nse.py's equity_history()). Unlike
 * crypto-chart.js's area series (CoinGecko's free tier is close-price-only
 * past 30 days), NSE actually publishes real Open/High/Low/Close every
 * trading day, so this renders honest candlesticks with technical indicators.
 *
 * Self-hosted TradingView Lightweight Charts (Apache-2.0), the same vendor
 * file crypto pages already load - nothing here depends on a third party
 * staying up.
 */

const RANGES = [
  { label: '1M', days: 30 },
  { label: '3M', days: 90 },
  { label: 'All', days: null },
];

function themeColors() {
  const s = getComputedStyle(document.documentElement);
  const v = (name, fallback) => (s.getPropertyValue(name) || fallback).trim();
  return {
    text: v('--text-muted', '#6b7280'),
    border: v('--border', '#e5e7eb'),
    up: v('--up', '#0f7a4d'),
    down: v('--down', '#c0392b'),
    upSoft: 'rgba(15, 122, 77, 0.25)',
    downSoft: 'rgba(192, 57, 43, 0.25)',
    sma: '#2563eb',
    ema: '#d97706',
    bb: '#7c3aed',
    resistance: '#dc2626',
    support: '#059669',
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

/* Automated Technical Analysis: Smart Zones (Support / Resistance) */
function calcSmartZones(points, lookback = 8) {
  if (points.length < lookback * 2) return null;
  const pivotHighs = [];
  const pivotLows = [];

  for (let i = lookback; i < points.length - lookback; i++) {
    const currentHigh = points[i].high;
    const currentLow = points[i].low;
    let isHigh = true;
    let isLow = true;

    for (let j = i - lookback; j <= i + lookback; j++) {
      if (j === i) continue;
      if (points[j].high > currentHigh) isHigh = false;
      if (points[j].low < currentLow) isLow = false;
    }

    if (isHigh) pivotHighs.push(currentHigh);
    if (isLow) pivotLows.push(currentLow);
  }

  const lastClose = points[points.length - 1].close;
  const resistances = pivotHighs.filter((p) => p > lastClose).sort((a, b) => a - b);
  const supports = pivotLows.filter((p) => p < lastClose).sort((a, b) => b - a);

  return {
    resistance: resistances.length ? resistances[0] : null,
    support: supports.length ? supports[0] : null,
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

function buildToolbar(container, onRangeSelect, onIndicatorToggle) {
  const bar = document.createElement('div');
  bar.className = 'chart-toolbar';
  bar.style.display = 'flex';
  bar.style.justifyContent = 'space-between';
  bar.style.alignItems = 'center';
  bar.style.flexWrap = 'wrap';
  bar.style.gap = '8px';
  bar.style.marginBottom = '8px';

  // Range group
  const rangeGroup = document.createElement('div');
  rangeGroup.className = 'chips';
  rangeGroup.setAttribute('role', 'group');
  rangeGroup.setAttribute('aria-label', 'Chart time range');
  RANGES.forEach((r, i) => {
    const btn = document.createElement('button');
    btn.className = 'chip';
    btn.type = 'button';
    btn.setAttribute('aria-pressed', i === RANGES.length - 1 ? 'true' : 'false');
    btn.textContent = r.label;
    btn.addEventListener('click', () => {
      rangeGroup.querySelectorAll('.chip').forEach((c) => c.setAttribute('aria-pressed', 'false'));
      btn.setAttribute('aria-pressed', 'true');
      onRangeSelect(r.days);
    });
    rangeGroup.appendChild(btn);
  });

  // Indicators group
  const indicatorGroup = document.createElement('div');
  indicatorGroup.className = 'chips';
  indicatorGroup.setAttribute('role', 'group');
  indicatorGroup.setAttribute('aria-label', 'Technical indicators');

  const indicators = [
    { id: 'sma', label: 'SMA 20' },
    { id: 'ema', label: 'EMA 50' },
    { id: 'bb', label: 'Bollinger' },
    { id: 'zones', label: 'Smart Zones' },
    { id: 'vol', label: 'Volume' },
  ];

  indicators.forEach((ind) => {
    const btn = document.createElement('button');
    btn.className = 'chip';
    btn.type = 'button';
    btn.setAttribute('aria-pressed', ind.id === 'vol' ? 'true' : 'false');
    btn.textContent = ind.label;
    btn.addEventListener('click', () => {
      const active = btn.getAttribute('aria-pressed') === 'true';
      btn.setAttribute('aria-pressed', active ? 'false' : 'true');
      onIndicatorToggle(ind.id, !active);
    });
    indicatorGroup.appendChild(btn);
  });

  bar.appendChild(rangeGroup);
  bar.appendChild(indicatorGroup);
  container.appendChild(bar);
  return bar;
}

async function initChart(host) {
  const slug = host.dataset.symbol;
  const canvasWrap = document.createElement('div');
  canvasWrap.className = 'coin-chart-canvas';

  const hud = document.createElement('div');
  hud.className = 'chart-hud xs faint';
  hud.style.display = 'flex';
  hud.style.gap = '14px';
  hud.style.flexWrap = 'wrap';
  hud.style.padding = '4px 0 8px 0';
  hud.style.fontFamily = 'monospace';

  host.appendChild(hud);
  host.appendChild(canvasWrap);

  let candles;
  try {
    const data = await loadHistory(slug);
    candles = data.candles || [];
  } catch {
    canvasWrap.innerHTML = `<div class="small faint" style="padding:24px 0;text-align:center">
      Price history isn't available for this stock yet - it refreshes on the next site update.</div>`;
    return;
  }
  const points = toCandleData(candles);
  if (points.length < 2) {
    canvasWrap.innerHTML = '<div class="small faint" style="padding:24px 0;text-align:center">Not enough price history yet.</div>';
    return;
  }

  const LWC = window.LightweightCharts;
  if (!LWC) {
    canvasWrap.innerHTML = '<div class="small faint" style="padding:24px 0;text-align:center">Chart library failed to load.</div>';
    return;
  }

  const colors = themeColors();
  const chart = LWC.createChart(canvasWrap, {
    height: 310,
    layout: { background: { type: 'solid', color: 'transparent' }, textColor: colors.text },
    grid: { vertLines: { visible: false }, horzLines: { color: colors.border } },
    rightPriceScale: { borderColor: colors.border },
    timeScale: { borderColor: colors.border },
    crosshair: { mode: 0 },
  });

  const candleSeries = chart.addSeries(LWC.CandlestickSeries, {
    upColor: colors.up,
    downColor: colors.down,
    borderVisible: false,
    wickUpColor: colors.up,
    wickDownColor: colors.down,
  });
  candleSeries.setData(points);

  // Volume series (occupies bottom 20%)
  const volumeSeries = chart.addSeries(LWC.HistogramSeries, {
    priceFormat: { type: 'volume' },
    priceScaleId: 'volume_scale',
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
  });
  const smaData = calcSMA(points, 20);
  smaSeries.setData(smaData);
  smaSeries.applyOptions({ visible: false });

  const emaSeries = chart.addSeries(LWC.LineSeries, {
    color: colors.ema,
    lineWidth: 1,
    lineStyle: 0,
    priceLineVisible: false,
    title: 'EMA 50',
  });
  const emaData = calcEMA(points, 50);
  emaSeries.setData(emaData);
  emaSeries.applyOptions({ visible: false });

  const bbUpperSeries = chart.addSeries(LWC.LineSeries, {
    color: colors.bb,
    lineWidth: 1,
    lineStyle: 2,
    priceLineVisible: false,
    title: 'BB Upper',
  });
  const bbLowerSeries = chart.addSeries(LWC.LineSeries, {
    color: colors.bb,
    lineWidth: 1,
    lineStyle: 2,
    priceLineVisible: false,
    title: 'BB Lower',
  });
  const bbData = calcBollinger(points, 20, 2);
  bbUpperSeries.setData(bbData.upper);
  bbLowerSeries.setData(bbData.lower);
  bbUpperSeries.applyOptions({ visible: false });
  bbLowerSeries.applyOptions({ visible: false });

  // Smart Zones (Support / Resistance Price Lines)
  const zones = calcSmartZones(points, 8);
  let resistanceLine = null;
  let supportLine = null;

  const updateSmartZones = (visible) => {
    if (!visible) {
      if (resistanceLine) {
        candleSeries.removePriceLine(resistanceLine);
        resistanceLine = null;
      }
      if (supportLine) {
        candleSeries.removePriceLine(supportLine);
        supportLine = null;
      }
      return;
    }
    if (zones && zones.resistance && !resistanceLine) {
      resistanceLine = candleSeries.createPriceLine({
        price: zones.resistance,
        color: colors.resistance,
        lineWidth: 1,
        lineStyle: 2,
        axisLabelVisible: true,
        title: 'Resistance',
      });
    }
    if (zones && zones.support && !supportLine) {
      supportLine = candleSeries.createPriceLine({
        price: zones.support,
        color: colors.support,
        lineWidth: 1,
        lineStyle: 2,
        axisLabelVisible: true,
        title: 'Support',
      });
    }
  };

  chart.timeScale().fitContent();

  // HUD Update Handler
  const lastPoint = points[points.length - 1];
  const updateHud = (p) => {
    const point = p || lastPoint;
    // Change versus the previous session's close: the same definition as the "Last close" card,
    // so the two figures on a page can never disagree (it used to be close vs open).
    const idx = points.findIndex((q) => q.time === point.time);
    const prevClose = idx > 0 ? points[idx - 1].close : null;
    const chg = prevClose ? (((point.close - prevClose) / prevClose) * 100).toFixed(2) : '0.00';
    const sign = Number(chg) >= 0 ? '+' : '';
    const chgColor = Number(chg) >= 0 ? colors.up : colors.down;

    hud.innerHTML = `
      <span>Date: <strong>${point.time}</strong></span>
      <span>O: <strong>${fmtNum(point.open)}</strong></span>
      <span>H: <strong>${fmtNum(point.high)}</strong></span>
      <span>L: <strong>${fmtNum(point.low)}</strong></span>
      <span>C: <strong>${fmtNum(point.close)}</strong></span>
      <span>Vol: <strong>${fmtVol(point.volume)}</strong></span>
      <span style="color:${chgColor}" title="Close versus previous close">Chg: <strong>${sign}${chg}%</strong></span>
    `;
  };
  updateHud();

  chart.subscribeCrosshairMove((param) => {
    if (!param || !param.time || !param.seriesData) {
      updateHud();
      return;
    }
    const cData = param.seriesData.get(candleSeries);
    if (cData) {
      updateHud(cData);
    }
  });

  const lastDate = new Date(`${points[points.length - 1].time}T00:00:00Z`);
  const setRange = (days) => {
    if (days == null) {
      chart.timeScale().fitContent();
      return;
    }
    const from = new Date(lastDate);
    from.setUTCDate(from.getUTCDate() - days);
    const fromStr = from.toISOString().slice(0, 10);
    const clampedFrom = points.find((p) => p.time >= fromStr)?.time || points[0].time;
    chart.timeScale().setVisibleRange({ from: clampedFrom, to: points[points.length - 1].time });
  };

  const handleIndicatorToggle = (id, active) => {
    if (id === 'sma') smaSeries.applyOptions({ visible: active });
    if (id === 'ema') emaSeries.applyOptions({ visible: active });
    if (id === 'bb') {
      bbUpperSeries.applyOptions({ visible: active });
      bbLowerSeries.applyOptions({ visible: active });
    }
    if (id === 'zones') updateSmartZones(active);
    if (id === 'vol') volumeSeries.applyOptions({ visible: active });
  };

  buildToolbar(host, setRange, handleIndicatorToggle);

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
