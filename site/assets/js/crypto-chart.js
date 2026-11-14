/* Price history chart for a single coin page, backed by
 * /data/crypto-history/<symbol>.json (up to a year of real daily closing
 * prices - see pipeline/sources/crypto.py's coingecko_history() for why
 * this is a line/area series, not candlesticks: CoinGecko's free OHLC
 * endpoint coarsens past 30 days, so a daily-granularity year of data only
 * exists as a price series, not real OHLC bars).
 *
 * Self-hosted TradingView Lightweight Charts (Apache-2.0), not a CDN - the
 * same "nothing this site needs to work depends on a third party staying
 * up" rule as every other asset here. Loaded as a classic <script> before
 * this module so window.LightweightCharts exists by the time this runs.
 */
import { esc } from './store.js?v=b59cf0df04';

const RANGES = [
  { label: '1M', days: 30 },
  { label: '3M', days: 90 },
  { label: '6M', days: 180 },
  { label: '1Y', days: 365 },
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
    upSoft: v('--up-soft', 'rgba(15,122,77,0.18)'),
    sma: '#2563eb',
    ema: '#d97706',
    bb: '#7c3aed',
    resistance: '#dc2626',
    support: '#059669',
  };
}

function toSeriesData(candles) {
  // candles: [[date, price], ...] already sorted, one point per unique date.
  return candles.map(([time, value]) => ({ time, value }));
}

/* Technical Indicator Mathematics */
function calcSMA(seriesData, period) {
  if (seriesData.length < period) return [];
  const result = [];
  let sum = 0;
  for (let i = 0; i < seriesData.length; i++) {
    sum += seriesData[i].value;
    if (i >= period) {
      sum -= seriesData[i - period].value;
    }
    if (i >= period - 1) {
      result.push({
        time: seriesData[i].time,
        value: parseFloat((sum / period).toFixed(4)),
      });
    }
  }
  return result;
}

function calcEMA(seriesData, period) {
  if (seriesData.length < period) return [];
  const k = 2 / (period + 1);
  const result = [];
  let sum = 0;
  for (let i = 0; i < period; i++) {
    sum += seriesData[i].value;
  }
  let prevEma = sum / period;
  result.push({ time: seriesData[period - 1].time, value: parseFloat(prevEma.toFixed(4)) });

  for (let i = period; i < seriesData.length; i++) {
    const currentEma = seriesData[i].value * k + prevEma * (1 - k);
    result.push({
      time: seriesData[i].time,
      value: parseFloat(currentEma.toFixed(4)),
    });
    prevEma = currentEma;
  }
  return result;
}

function calcBollinger(seriesData, period = 20, multiplier = 2) {
  if (seriesData.length < period) return { upper: [], lower: [] };
  const upper = [];
  const lower = [];

  for (let i = period - 1; i < seriesData.length; i++) {
    let sum = 0;
    for (let j = i - period + 1; j <= i; j++) {
      sum += seriesData[j].value;
    }
    const mean = sum / period;

    let varianceSum = 0;
    for (let j = i - period + 1; j <= i; j++) {
      varianceSum += Math.pow(seriesData[j].value - mean, 2);
    }
    const stdDev = Math.sqrt(varianceSum / period);

    upper.push({
      time: seriesData[i].time,
      value: parseFloat((mean + multiplier * stdDev).toFixed(4)),
    });
    lower.push({
      time: seriesData[i].time,
      value: parseFloat((mean - multiplier * stdDev).toFixed(4)),
    });
  }
  return { upper, lower };
}

function calcSmartZones(seriesData, lookback = 10) {
  if (seriesData.length < lookback * 2) return null;
  const pivotHighs = [];
  const pivotLows = [];

  for (let i = lookback; i < seriesData.length - lookback; i++) {
    const current = seriesData[i].value;
    let isHigh = true;
    let isLow = true;

    for (let j = i - lookback; j <= i + lookback; j++) {
      if (j === i) continue;
      if (seriesData[j].value > current) isHigh = false;
      if (seriesData[j].value < current) isLow = false;
    }

    if (isHigh) pivotHighs.push(current);
    if (isLow) pivotLows.push(current);
  }

  const lastPrice = seriesData[seriesData.length - 1].value;
  const resistances = pivotHighs.filter((p) => p > lastPrice).sort((a, b) => a - b);
  const supports = pivotLows.filter((p) => p < lastPrice).sort((a, b) => b - a);

  return {
    resistance: resistances.length ? resistances[0] : null,
    support: supports.length ? supports[0] : null,
  };
}

function fmtUsd(n) {
  if (n == null) return '-';
  const d = n < 1 ? 6 : n < 100 ? 4 : 2;
  return `$${n.toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d })}`;
}

async function loadHistory(symbol) {
  const r = await fetch(`/data/crypto-history/${symbol.toLowerCase()}.json`);
  if (!r.ok) throw new Error(`crypto-history -> ${r.status}`);
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

  // Range chips
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

  // Indicators chips
  const indicatorGroup = document.createElement('div');
  indicatorGroup.className = 'chips';
  indicatorGroup.setAttribute('role', 'group');
  indicatorGroup.setAttribute('aria-label', 'Technical indicators');

  const indicators = [
    { id: 'sma', label: 'SMA 20' },
    { id: 'ema', label: 'EMA 50' },
    { id: 'bb', label: 'Bollinger' },
    { id: 'zones', label: 'Smart Zones' },
  ];

  indicators.forEach((ind) => {
    const btn = document.createElement('button');
    btn.className = 'chip';
    btn.type = 'button';
    btn.setAttribute('aria-pressed', 'false');
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
  const symbol = host.dataset.symbol;
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
    const data = await loadHistory(symbol);
    candles = data.candles || [];
  } catch {
    canvasWrap.innerHTML = `<div class="small faint" style="padding:24px 0;text-align:center">
      Price history isn't available for ${esc(symbol)} yet - it refreshes on the next site update.</div>`;
    return;
  }
  if (candles.length < 2) {
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

  const areaSeries = chart.addSeries(LWC.AreaSeries, {
    lineColor: colors.up,
    topColor: colors.upSoft,
    bottomColor: 'rgba(0,0,0,0)',
    lineWidth: 2,
    priceLineVisible: false,
  });
  const seriesData = toSeriesData(candles);
  areaSeries.setData(seriesData);

  // Technical Indicators
  const smaSeries = chart.addSeries(LWC.LineSeries, {
    color: colors.sma,
    lineWidth: 1,
    priceLineVisible: false,
    title: 'SMA 20',
  });
  smaSeries.setData(calcSMA(seriesData, 20));
  smaSeries.applyOptions({ visible: false });

  const emaSeries = chart.addSeries(LWC.LineSeries, {
    color: colors.ema,
    lineWidth: 1,
    priceLineVisible: false,
    title: 'EMA 50',
  });
  emaSeries.setData(calcEMA(seriesData, 50));
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
  const bbData = calcBollinger(seriesData, 20, 2);
  bbUpperSeries.setData(bbData.upper);
  bbLowerSeries.setData(bbData.lower);
  bbUpperSeries.applyOptions({ visible: false });
  bbLowerSeries.applyOptions({ visible: false });

  // Smart Zones (Support / Resistance)
  const zones = calcSmartZones(seriesData, 10);
  let resistanceLine = null;
  let supportLine = null;

  const updateSmartZones = (visible) => {
    if (!visible) {
      if (resistanceLine) {
        areaSeries.removePriceLine(resistanceLine);
        resistanceLine = null;
      }
      if (supportLine) {
        areaSeries.removePriceLine(supportLine);
        supportLine = null;
      }
      return;
    }
    if (zones && zones.resistance && !resistanceLine) {
      resistanceLine = areaSeries.createPriceLine({
        price: zones.resistance,
        color: colors.resistance,
        lineWidth: 1,
        lineStyle: 2,
        axisLabelVisible: true,
        title: 'Resistance',
      });
    }
    if (zones && zones.support && !supportLine) {
      supportLine = areaSeries.createPriceLine({
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
  const firstPoint = seriesData[0];
  const lastPoint = seriesData[seriesData.length - 1];
  const updateHud = (p) => {
    const point = p || lastPoint;
    const baseVal = firstPoint ? firstPoint.value : point.value;
    const chg = baseVal ? (((point.value - baseVal) / baseVal) * 100).toFixed(2) : '0.00';
    const sign = Number(chg) >= 0 ? '+' : '';
    const chgColor = Number(chg) >= 0 ? colors.up : colors.down;

    hud.innerHTML = `
      <span>Date: <strong>${point.time}</strong></span>
      <span>Price: <strong>${fmtUsd(point.value)}</strong></span>
      <span style="color:${chgColor}">Change: <strong>${sign}${chg}%</strong></span>
    `;
  };
  updateHud();

  chart.subscribeCrosshairMove((param) => {
    if (!param || !param.time || !param.seriesData) {
      updateHud();
      return;
    }
    const aData = param.seriesData.get(areaSeries);
    if (aData) {
      updateHud(aData);
    }
  });

  const lastDate = new Date(`${candles[candles.length - 1][0]}T00:00:00Z`);
  const setRange = (days) => {
    if (days == null) {
      chart.timeScale().fitContent();
      return;
    }
    const from = new Date(lastDate);
    from.setUTCDate(from.getUTCDate() - days);
    const fromStr = from.toISOString().slice(0, 10);
    const clampedFrom = candles.find((c) => c[0] >= fromStr)?.[0] || candles[0][0];
    chart.timeScale().setVisibleRange({ from: clampedFrom, to: candles[candles.length - 1][0] });
  };

  const handleIndicatorToggle = (id, active) => {
    if (id === 'sma') smaSeries.applyOptions({ visible: active });
    if (id === 'ema') emaSeries.applyOptions({ visible: active });
    if (id === 'bb') {
      bbUpperSeries.applyOptions({ visible: active });
      bbLowerSeries.applyOptions({ visible: active });
    }
    if (id === 'zones') updateSmartZones(active);
  };

  buildToolbar(host, setRange, handleIndicatorToggle);

  window.addEventListener('brokerlens:crypto-quote', (e) => {
    if (!e.detail || e.detail.symbol !== symbol) return;
    const livePrice = e.detail.price;
    if (livePrice == null || isNaN(livePrice)) return;
    const today = new Date().toISOString().slice(0, 10);
    areaSeries.update({ time: today, value: livePrice });
    updateHud({ time: today, value: livePrice });
  });

  const ro = new ResizeObserver(() => chart.applyOptions({ width: canvasWrap.clientWidth }));
  ro.observe(canvasWrap);

  // theme-init.js dispatches a real 'resize' event on toggle specifically so
  // canvas-based widgets can re-read CSS custom properties and repaint.
  window.addEventListener('resize', () => {
    const c = themeColors();
    chart.applyOptions({
      layout: { textColor: c.text },
      grid: { horzLines: { color: c.border } },
      rightPriceScale: { borderColor: c.border },
      timeScale: { borderColor: c.border },
    });
    areaSeries.applyOptions({ lineColor: c.up, topColor: c.upSoft });
  });
}

document.querySelectorAll('[data-crypto-chart]').forEach(initChart);
