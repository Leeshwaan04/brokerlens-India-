/* Price history chart for stock pages. The chart itself is the shared charting
 * engine (charting/ in the repo, built to /assets/js/charting/engine.js, the same
 * code paper.brokerlens.in uses) on self-hosted TradingView Lightweight Charts
 * v5.2.1 (Apache-2.0). This file only mounts it, on the real daily history in
 * /data/equity-history/<slug>.json (NSE bhavcopy, see pipeline/sources/nse.py).
 *
 * Saved settings keep their old keys (bl_chart_prefs_v1 is read once as a
 * fallback; the target line stays in bl_chart_targets_v1), so nobody loses
 * their choices in the move.
 */
const lib = window.BrokerLensCharting;

async function initChart(host) {
  const slug = host.dataset.symbol;
  if (!lib || !window.LightweightCharts) {
    host.textContent = 'Chart library failed to load.';
    host.className = 'small faint';
    return;
  }
  const adapter = lib.candleFileAdapter(slug, `/data/equity-history/${slug}.json`);
  let sessions = 0;
  const load = adapter.loadDaily.bind(adapter);
  adapter.loadDaily = async () => {
    const bars = await load();
    sessions = bars.length;
    return bars;
  };
  await lib.mountStudio(host, { adapter, height: 330, storagePrefix: 'bl_chart' });
  if (sessions >= 2 && sessions < 22) {
    const notice = document.createElement('div');
    notice.className = 'xs muted';
    notice.style.margin = '6px 0 2px 0';
    notice.textContent = `Showing all ${sessions} trading sessions on record. Longer timeframes unlock as additional exchange sessions accumulate.`;
    host.appendChild(notice);
  }
}

document.querySelectorAll('[data-stock-chart]').forEach(initChart);
