/* Data access + formatting.
 *
 * Everything is a static JSON fetch against the same origin, cached in memory
 * for the session. No live API calls, so the site keeps working when NSE, BSE or
 * SEBI are down or rate-limiting.
 */

/* The site collects no personal data: there is no lead capture, no form that
 * posts anywhere, and no third-party script. Everything is a static JSON read. */
export const CONFIG = {
  siteName: 'BrokerLens',
};

const cache = new Map();

async function get(path) {
  if (cache.has(path)) return cache.get(path);
  const p = fetch(path, { headers: { Accept: 'application/json' } })
    .then((r) => {
      if (!r.ok) throw new Error(`${path} -> ${r.status}`);
      return r.json();
    })
    .catch((err) => {
      cache.delete(path);
      throw err;
    });
  cache.set(path, p);
  return p;
}

export const loadOverview = () => get('/data/overview.json');

/* The ticker is polled, so it deliberately bypasses the session cache and
 * cache-busts the URL. Everything else is immutable for the session. */
export async function loadTicker() {
  const r = await fetch(`/data/ticker.json?t=${Date.now()}`, { cache: 'no-store' });
  if (!r.ok) throw new Error(`ticker.json -> ${r.status}`);
  return r.json();
}
export const loadBroker = (id) => get(`/data/brokers/${encodeURIComponent(id)}.json`);
export const loadRegistry = () => get('/data/registry.json');
export const loadAlgo = () => get('/data/algo.json');
export const loadTimings = () => get('/data/timings.json');
export const loadSources = () => get('/data/sources.json');
export const loadSearchIndex = () => get('/data/search.json');

/* --------------------------------------------------------------- formatting */

/* Indian numbering: lakh (1e5) and crore (1e7). Anything else misreads to the
 * audience this site is for. */
export function inr(n, opts = {}) {
  if (n == null || Number.isNaN(n)) return '—';
  const abs = Math.abs(n);
  const sign = n < 0 ? '-' : '';
  const d = opts.decimals;
  if (abs >= 1e7) return `${sign}₹${(abs / 1e7).toFixed(d ?? 2)} Cr`;
  if (abs >= 1e5) return `${sign}₹${(abs / 1e5).toFixed(d ?? 2)} L`;
  if (abs >= 1e3) return `${sign}₹${Math.round(abs).toLocaleString('en-IN')}`;
  return `${sign}₹${abs.toFixed(d ?? 0)}`;
}

export function count(n) {
  if (n == null || Number.isNaN(n)) return '—';
  const abs = Math.abs(n);
  if (abs >= 1e7) return `${(n / 1e7).toFixed(2)} Cr`;
  if (abs >= 1e5) return `${(n / 1e5).toFixed(2)} L`;
  return Math.round(n).toLocaleString('en-IN');
}

export const full = (n) => (n == null ? '—' : Math.round(n).toLocaleString('en-IN'));

export function pct(n, opts = {}) {
  if (n == null || Number.isNaN(n)) return '—';
  const s = n > 0 && opts.sign !== false ? '+' : '';
  return `${s}${n.toFixed(opts.decimals ?? 2)}%`;
}

export const cls = (n) => (n == null ? '' : n > 0 ? 'up' : n < 0 ? 'down' : '');

export function month(m) {
  if (!m) return '—';
  const [y, mm] = String(m).split('-');
  const names = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  return `${names[Number(mm) - 1] || mm} ${y}`;
}

export const esc = (s) =>
  String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

/* Escaping alone does NOT make a URL safe to put in href.
 *
 * esc() stops attribute-breakout, but `javascript:alert(1)` survives it intact
 * and fires on click. Several URLs here come from third parties — circular PDF
 * links from NSE's feed, broker websites — so the scheme has to be validated,
 * not just the characters escaped.
 *
 * Allowlist http/https (plus mailto for contact links). Anything else, including
 * javascript:, data:, vbscript: and protocol-relative //evil.example, is refused.
 */
export function safeUrl(url, { allowMailto = false } = {}) {
  const raw = String(url ?? '').trim();
  if (!raw) return '';
  // Strip control characters — "java\tscript:" is a real bypass.
  const cleaned = raw.replace(/[\x00-\x1f\x7f]/g, '');
  if (cleaned.startsWith('//')) return '';            // protocol-relative
  if (cleaned.startsWith('/') || cleaned.startsWith('#')) return esc(cleaned);  // same-origin
  let parsed;
  try {
    parsed = new URL(cleaned, location.origin);
  } catch {
    return '';
  }
  const ok = ['http:', 'https:'].concat(allowMailto ? ['mailto:'] : []);
  return ok.includes(parsed.protocol) ? esc(parsed.href) : '';
}

export const TYPE_LABEL = {
  discount: 'Discount',
  full_service: 'Full service',
  bank_backed: 'Bank-backed',
};

export const SEGMENT_LABEL = {
  equity_cash: 'Equity delivery',
  equity_fno: 'Equity F&O',
  currency: 'Currency',
  commodity: 'Commodity',
};

/* Consistent brand mark colour per broker, derived from the id so it is stable
 * across builds without storing a colour per broker. */
export function markColor(id) {
  let h = 0;
  for (let i = 0; i < String(id).length; i++) h = (h * 31 + String(id).charCodeAt(i)) % 360;
  return `hsl(${h} 42% 42%)`;
}

export const initials = (name) =>
  String(name || '?')
    .split(/[\s.]+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0].toUpperCase())
    .join('');

/* Provenance dot: how much a given number can be trusted. */
export function provDot(kind) {
  const k = kind === 'nse' || kind === 'sebi_registry' || kind === 'sebi_annexure_b' || kind === 'primary'
    ? 'primary'
    : kind === 'sample'
      ? 'sample'
      : kind == null
        ? 'none'
        : 'curated';
  const title = {
    primary: 'Sourced from a primary exchange or regulator feed',
    sample: 'SAMPLE data — not a real figure, pending first ingest',
    curated: 'Hand-curated or broker-supplied, not regulator-verified',
    none: 'Not available',
  }[k];
  return `<span class="dot-src ${k}" title="${title}"></span>`;
}
