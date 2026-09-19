/* Price history chart for a single stock page, backed by
 * /data/equity-history/<slug>.json (real daily OHLCV from NSE's own
 * bhavcopy - see pipeline/sources/nse.py's equity_history()). Unlike
 * crypto-chart.js's area series (CoinGecko's free tier is close-price-only
 * past 30 days), NSE actually publishes real Open/High/Low/Close every
 * trading day, so this renders honest candlesticks.
 *
 * Self-hosted TradingView Lightweight Charts (Apache-2.0), the same vendor
 * file crypto pages already load - nothing here depends on a third party
 * staying up.
 */

// Only as deep as the data actually goes (see equity_history()'s
// days_back comment) - no "6M"/"1Y" button that would just silently clamp
// to the same range "All" already shows.
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
  };
}

function toCandleData(candles) {
  return candles
    .filter((c) => c.open != null && c.high != null && c.low != null && c.close != null)
    .map((c) => ({ time: c.date, open: c.open, high: c.high, low: c.low, close: c.close }));
}

async function loadHistory(slug) {
  const r = await fetch(`/data/equity-history/${slug}.json`);
  if (!r.ok) throw new Error(`equity-history -> ${r.status}`);
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
  const slug = host.dataset.symbol;
  const canvasWrap = document.createElement('div');
  canvasWrap.className = 'coin-chart-canvas';
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
    height: 280,
    layout: { background: { type: 'solid', color: 'transparent' }, textColor: colors.text },
    grid: { vertLines: { visible: false }, horzLines: { color: colors.border } },
    rightPriceScale: { borderColor: colors.border },
    timeScale: { borderColor: colors.border },
    crosshair: { mode: 0 },
  });
  const series = chart.addSeries(LWC.CandlestickSeries, {
    upColor: colors.up, downColor: colors.down, borderVisible: false,
    wickUpColor: colors.up, wickDownColor: colors.down,
  });
  series.setData(points);
  chart.timeScale().fitContent();

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
  buildRangeButtons(host, setRange);

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
    series.applyOptions({ upColor: c.up, downColor: c.down, wickUpColor: c.up, wickDownColor: c.down });
  });
}

document.querySelectorAll('[data-stock-chart]').forEach(initChart);
