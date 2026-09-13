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
import { esc } from './store.js?v=557d965307';

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
    upSoft: v('--up-soft', 'rgba(15,122,77,0.18)'),
  };
}

function toSeriesData(candles) {
  // candles: [[date, price], ...] already sorted, one point per unique date.
  return candles.map(([time, value]) => ({ time, value }));
}

async function loadHistory(symbol) {
  const r = await fetch(`/data/crypto-history/${symbol.toLowerCase()}.json`);
  if (!r.ok) throw new Error(`crypto-history -> ${r.status}`);
  return r.json();
}

function buildRangeButtons(container, onSelect) {
  const bar = document.createElement('div');
  bar.className = 'chips';
  bar.setAttribute('role', 'group');
  bar.setAttribute('aria-label', 'Chart time range');
  RANGES.forEach((r, i) => {
    const btn = document.createElement('button');
    btn.className = 'chip';
    btn.type = 'button';
    btn.setAttribute('aria-pressed', i === RANGES.length - 1 ? 'true' : 'false');
    btn.textContent = r.label;
    btn.addEventListener('click', () => {
      bar.querySelectorAll('.chip').forEach((c) => c.setAttribute('aria-pressed', 'false'));
      btn.setAttribute('aria-pressed', 'true');
      onSelect(r.days);
    });
    bar.appendChild(btn);
  });
  container.appendChild(bar);
  return bar;
}

async function initChart(host) {
  const symbol = host.dataset.symbol;
  const canvasWrap = document.createElement('div');
  canvasWrap.className = 'coin-chart-canvas';
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
    height: 280,
    layout: { background: { type: 'solid', color: 'transparent' }, textColor: colors.text },
    grid: { vertLines: { visible: false }, horzLines: { color: colors.border } },
    rightPriceScale: { borderColor: colors.border },
    timeScale: { borderColor: colors.border },
    crosshair: { mode: 0 },
  });
  const series = chart.addSeries(LWC.AreaSeries, {
    lineColor: colors.up,
    topColor: colors.upSoft,
    bottomColor: 'rgba(0,0,0,0)',
    lineWidth: 2,
    priceLineVisible: false,
  });
  const seriesData = toSeriesData(candles);
  series.setData(seriesData);
  chart.timeScale().fitContent();

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
  buildRangeButtons(host, setRange);

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
    series.applyOptions({ lineColor: c.up, topColor: c.upSoft });
  });
}

document.querySelectorAll('[data-crypto-chart]').forEach(initChart);
