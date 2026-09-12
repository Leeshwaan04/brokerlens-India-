/* Live-ish price for a single static crypto page or the /crypto/ hub list.
 * Same contract as the rest of the site: a static page carries stable facts
 * (market cap rank, supply, ATH/ATL) rebuilt on each publish; the fast-moving
 * number (price) is fetched client-side from a frequently-refreshed static
 * JSON snapshot, never a live call to Binance itself - the browser never
 * calls a third-party market API directly, same rule as store.js's ticker.
 */
import { esc, cls, pct } from './store.js?v=557d965307';

async function loadCryptoTicker() {
  const r = await fetch(`/data/crypto-ticker.json?t=${Date.now()}`, { cache: 'no-store' });
  if (!r.ok) throw new Error(`crypto-ticker.json -> ${r.status}`);
  return r.json();
}

function fmtUsd(n) {
  if (n == null) return '—';
  const d = n < 1 ? 6 : n < 100 ? 4 : 2;
  return `$${n.toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d })}`;
}

async function paintOne() {
  const el = document.getElementById('crypto-price');
  if (!el) return;
  const symbol = el.dataset.symbol;
  try {
    const t = await loadCryptoTicker();
    const c = (t.coins || []).find((x) => x.symbol === symbol);
    if (!c) {
      el.innerHTML = '<div class="small faint">Live price unavailable right now.</div>';
      return;
    }
    el.innerHTML = `<div class="stat-value">${fmtUsd(c.price_usd)}
        <span class="num ${cls(c.change_pct_24h)}" style="font-size:var(--fs-base);margin-left:8px">${pct(c.change_pct_24h)}</span></div>
      <div class="xs faint" style="margin-top:4px">24h range ${fmtUsd(c.low_24h)} to ${fmtUsd(c.high_24h)} &middot;
        as of ${esc(new Date(t.generated_at).toLocaleString('en-IN', { hour: '2-digit', minute: '2-digit', day: 'numeric', month: 'short' }))}</div>`;
  } catch {
    el.innerHTML = '<div class="small faint">Live price unavailable - run <code>python3 -m pipeline.run ticker</code>.</div>';
  }
}

async function paintList() {
  const rows = document.querySelectorAll('[data-crypto-row]');
  if (!rows.length) return;
  try {
    const t = await loadCryptoTicker();
    const bySym = {};
    (t.coins || []).forEach((c) => { bySym[c.symbol] = c; });
    rows.forEach((row) => {
      const c = bySym[row.dataset.cryptoRow];
      const priceEl = row.querySelector('[data-role="price"]');
      const chgEl = row.querySelector('[data-role="change"]');
      if (!c) {
        if (priceEl) priceEl.textContent = '—';
        return;
      }
      if (priceEl) priceEl.textContent = fmtUsd(c.price_usd);
      if (chgEl) { chgEl.textContent = pct(c.change_pct_24h); chgEl.className = `num ${cls(c.change_pct_24h)}`; }
    });
  } catch {
    /* leave the static "—" placeholders in place - never show a stale guess */
  }
}

paintOne();
paintList();
