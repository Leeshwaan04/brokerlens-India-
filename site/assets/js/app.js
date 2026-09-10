/* Shell: routing, the live market ticker, theme, and SEO head updates.
 *
 * Client-side routed with history.pushState, exactly like mtf.trading, so a
 * static host serves one HTML file and the router handles the rest. The dev
 * server (and any production host) must rewrite unknown paths to /index.html.
 */

import { cls, esc, loadOverview, loadTicker, pct } from './store.js';
import * as pages from './pages.js';
import { clearRedraws } from './chart.js';
import './nav-widgets.js';

const app = document.getElementById('app');

const ROUTES = [
  [/^\/$/, () => pages.home()],
  [/^\/brokers\/?$/, (_m, q) => pages.brokers(q)],
  [/^\/broker\/([a-z0-9-]+)\/?$/i, (m) => pages.broker(m[1])],
  [/^\/compare\/?$/, (_m, q) => pages.compare(q)],
  [/^\/leaderboards\/?$/, () => pages.leaderboards()],
  [/^\/rankings\/?$/, () => pages.leaderboards()],
  [/^\/calculator\/?$/, (_m, q) => pages.calculator(q)],
  [/^\/registry\/?$/, () => pages.registry()],
  [/^\/algo\/?$/, (_m, q) => pages.algo(q)],
  [/^\/algo-platforms\/?$/, (_m, q) => pages.algo(q)],
  [/^\/methodology\/?$/, () => pages.methodology()],
  [/^\/sources\/?$/, () => pages.sources()],
];

const TITLES = {
  '/': 'BrokerLens India: Indian stock broker statistics from NSE, BSE and SEBI',
  '/brokers': 'All Indian stock brokers, compared: BrokerLens India',
  '/compare': 'Compare Indian stock brokers side by side: BrokerLens India',
  '/leaderboards': 'Broker rankings by clients, complaints and cost: BrokerLens India',
  '/calculator': 'Brokerage cost calculator: BrokerLens India',
  '/registry': 'SEBI-registered brokers and intermediaries: BrokerLens India',
  '/algo': 'Algo trading platforms in India (APIs, no-code builders and vendors) | BrokerLens India',
  '/methodology': 'Methodology: BrokerLens India',
  '/sources': 'Data sources and lineage: BrokerLens India',
};

/* Per-route descriptions. Without these every page inherited the homepage copy,
 * and a broker description leaked onto whatever page was visited next. */
const DESCRIPTIONS = {
  '/': 'Compare every SEBI-registered Indian stock broker on active clients, market share, complaint records and cost. Built from primary NSE, BSE and SEBI disclosures.',
  '/brokers': 'Every Indian stock broker we track, side by side: active clients, growth, complaint rate, reliability and monthly cost, from primary regulator and exchange sources.',
  '/compare': 'Put Indian stock brokers head to head on clients, complaints, regulatory standing and real cost, using regulator-sourced figures.',
  '/leaderboards': 'Indian broker rankings by active clients, growth, complaint rate, resolution rate and cost. Every board states the metric it sorts on.',
  '/calculator': 'Work out what a month of your actual trading costs at each Indian broker, using their published charges.',
  '/registry': 'Search every SEBI-registered broking and depository-participant entity: legal name, registration number, city, exchange memberships and validity.',
  '/algo': 'Algo trading platforms in India: official broker APIs, no-code strategy builders, backtesting tools and institutional vendors, with SEBI framework context.',
  '/methodology': 'How every figure on BrokerLens is calculated: the cost basket, the reliability weights, and what each provenance marker means.',
  '/sources': 'Every data source behind BrokerLens, when it last ran, and exactly which fields it feeds.',
};

/* Alias routes must not compete with their primary in search. */
const ALIAS_OF = {
  '/rankings': '/leaderboards',
  '/algo-platforms': '/algo',
};

async function render() {
  const path = location.pathname.replace(/\/{2,}/g, '/');
  const query = new URLSearchParams(location.search);
  clearRedraws();

  const hit = ROUTES.find(([re]) => re.test(path));
  app.innerHTML = `<div class="grid g3"><div class="card skeleton" style="height:96px"></div>
    <div class="card skeleton" style="height:96px"></div><div class="card skeleton" style="height:96px"></div></div>`;

  try {
    const html = hit ? await hit[1](path.match(hit[0]), query) : pages.notFound();
    app.innerHTML = html;
    pages.runAfter();
  } catch (err) {
    console.error(err);
    app.innerHTML = `<div class="empty"><h2>Could not load this page</h2>
      <p class="muted small">${esc(err.message)}</p>
      <p class="xs faint">If the data files are missing, run <code>python3 -m pipeline.run all</code> first.</p></div>`;
  }

  // Per-broker titles come from the rendered heading so they stay in step with
  // the data rather than needing a second lookup.
  const h1 = app.querySelector('h1');
  const isBroker = path.startsWith('/broker/');
  if (TITLES[path]) {
    document.title = TITLES[path];
  } else if (isBroker && h1) {
    document.title = `${h1.textContent.trim()}: active clients, complaints and charges | BrokerLens India`;
  } else {
    // Anything else (a 404, an alias) must not inherit the broker template.
    document.title = h1 ? `${h1.textContent.trim()}: BrokerLens India` : 'BrokerLens India';
  }

  // Description must be RESET on every route, not only set on broker pages:
  // it used to leak, so /algo could still describe the last broker viewed.
  const desc = document.querySelector('meta[name="description"]');
  if (desc) {
    desc.setAttribute('content',
      isBroker && h1
        ? `${h1.textContent.trim()}: active client count, market share, SEBI complaint record, regulatory registrations and cost, from primary NSE, BSE and SEBI disclosures.`
        : DESCRIPTIONS[ALIAS_OF[path] || path] || DESCRIPTIONS['/']);
  }

  // Canonical was hardcoded to "/" on every page, telling search engines all 56
  // URLs were duplicates of the homepage. Point it at the real path, and send
  // aliases to their primary so the duplicates consolidate correctly.
  const canonical = document.querySelector('link[rel="canonical"]');
  if (canonical) {
    const primary = ALIAS_OF[path] || path;
    canonical.setAttribute('href', location.origin + primary);
  }
  const ogUrl = document.querySelector('meta[property="og:url"]');
  if (ogUrl) ogUrl.setAttribute('content', location.origin + (ALIAS_OF[path] || path));
  const ogTitle = document.querySelector('meta[property="og:title"]');
  if (ogTitle) ogTitle.setAttribute('content', document.title);
  const ogDesc = document.querySelector('meta[property="og:description"]');
  if (ogDesc && desc) ogDesc.setAttribute('content', desc.getAttribute('content'));
  const seg = path.split('/')[1] || '';
  document.querySelectorAll('#navlinks a').forEach((a) =>
    a.classList.toggle('active', a.getAttribute('href').split('/')[1] === seg));

  if (location.hash) {
    const el = document.querySelector(location.hash);
    if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
  } else {
    window.scrollTo({ top: 0 });
  }
}

/* ---------------------------------------------------------------- links */

document.addEventListener('click', (e) => {
  const a = e.target.closest('a[data-link]');
  if (!a) return;
  const url = new URL(a.href, location.origin);
  if (url.origin !== location.origin) return;
  e.preventDefault();
  if (url.pathname + url.search + url.hash === location.pathname + location.search + location.hash) return;
  history.pushState({}, '', url);
  render();
});

window.addEventListener('popstate', render);

/* Theme init/toggle now lives in theme-init.js, loaded in <head> on every
 * page including this shell - having it here too would attach a second
 * click handler to the same #theme-toggle button, and two handlers firing
 * on one click flip the theme twice (net: nothing visibly changes). */

/* ---------------------------------------------------------------- ticker
 *
 * The browser never calls NSE/BSE/MCX directly: they refuse cross-origin
 * requests, gate on session cookies, sit behind bot walls, and our own CSP is
 * default-src 'self'. Everything comes from our origin, in two tiers:
 *
 *   1. First paint from /data/ticker.json — a static ~7KB file the pipeline
 *      writes. Always available, CDN-cacheable, survives an exchange outage.
 *   2. Then an upgrade to /api/stream (Server-Sent Events) if a stream server is
 *      running. Pushed frames patch individual prices in place at 1-3s.
 *
 * If the stream is absent (a static-only deploy) or drops, we fall back to
 * polling tier 1. The strip therefore works on a plain CDN and gets sharper when
 * a live backend exists — no feature detection needed beyond the EventSource.
 */

const EXCH_KEY = 'bl-exchange';
const POLL_MS = 45000;

const track = document.getElementById('ticker-track');
const dot = document.getElementById('exch-dot');
const statusEl = document.getElementById('exch-status');
const select = document.getElementById('exch-select');

let tickerData = null;
let pollTimer = null;

const currentExchange = () => select?.value || localStorage.getItem(EXCH_KEY) || 'NSE';
const currentFeed = currentExchange;   // feeds are no longer only exchanges

function tickItem(label, value, changePct, change, q = {}) {
  const chg = changePct != null
    ? `<span class="num ${cls(changePct)}">${pct(changePct)}</span>`
    : change != null ? `<span class="num ${cls(change)}">${change > 0 ? '+' : ''}${change}</span>` : '';
  // A broker stock links straight to that broker's profile — the one thing this
  // ticker can do that a generic market ticker cannot.
  const sym = q.broker_id
    ? `<a class="tick-sym" href="/broker/${esc(q.broker_id)}" data-link title="${esc(q.name || label)}${
        q.relation === 'parent' ? ' — parent company' : ''}">${esc(label)}${
        q.relation === 'parent' ? '<sup>P</sup>' : ''}</a>`
    : `<span class="tick-sym"${q.name ? ` title="${esc(q.name)}"` : ''}>${esc(label)}</span>`;
  // data-sym lets a pushed update patch this item in place. Rebuilding the whole
  // track would restart the CSS scroll animation and visibly jump.
  return `<span class="tick" data-sym="${esc(String(label).toUpperCase())}">
    ${sym}<span class="num" data-role="last">${value}</span>${chg}</span>`;
}

/* Instruments only — every row is a tradable thing with a price. Market breadth,
 * delivery percentage and the site's own aggregates belong on the pages that
 * explain them, not in a price strip. */
function buildItems(feed) {
  const items = [];
  const seen = new Set();
  for (const q of feed.instruments || []) {
    const label = q.symbol || q.name;
    const key = String(label || '').toUpperCase();
    if (!key || seen.has(key) || q.last == null) continue;
    seen.add(key);
    items.push(tickItem(label, q.last.toLocaleString('en-IN'), q.change_pct, q.change, q));
  }
  return items;
}

/* Populate the dropdown from the payload, so adding a feed server-side needs no
 * front-end change. */
function syncFeedOptions() {
  if (!select || !tickerData) return;
  const order = tickerData.order || Object.keys(tickerData.feeds || {});
  const sig = order.join(',');
  if (select.dataset.sig === sig) return;
  select.dataset.sig = sig;
  const saved = localStorage.getItem(EXCH_KEY);
  select.innerHTML = order.map((id) => {
    const f = tickerData.feeds[id] || {};
    return `<option value="${esc(id)}">${esc(f.label || id)}</option>`;
  }).join('');
  if (saved && order.includes(saved)) select.value = saved;
}

function paint() {
  if (!track || !tickerData) return;
  syncFeedOptions();
  const name = currentExchange();
  const ex = (tickerData.feeds || {})[name] || {};

  // NSE's marketStatus API says "Close"; readers expect "Closed". Normalise for
  // display only, keeping the raw value in the data payloads.
  const statusLabel = (s) => {
    const t = String(s || '').toLowerCase();
    if (t === 'open') return 'Open';
    if (t === 'close' || t === 'closed') return 'Closed';
    return s;
  };
  const open = String(ex.status || '').toLowerCase() === 'open';
  dot?.classList.toggle('open', open);
  dot?.classList.toggle('closed', !open);
  if (statusEl) {
    statusEl.textContent = statusLabel(ex.status) || '';
    statusEl.classList.toggle('open', open);
  }
  const items = buildItems(ex);
  if (!items.length) {
    track.style.animation = 'none';
    track.innerHTML = `<span class="tick faint xs">No live instruments in ${esc(ex.label || name)} right now.
      ${esc(ex.note || 'Run `python3 -m pipeline.run ticker` to refresh.')}</span>`;
    return;
  }

  // The strip is duplicated so translateX(-50%) loops seamlessly.
  track.style.animation = '';
  track.innerHTML = items.join('') + items.join('');
  // Roughly constant scroll speed regardless of how many symbols are showing.
  track.style.setProperty('--roll-dur', `${Math.max(30, items.length * 3.2)}s`);
}

async function refreshTicker() {
  try {
    tickerData = await loadTicker();
    paint();
  } catch {
    if (track && !tickerData) {
      track.style.animation = 'none';
      track.innerHTML = `<span class="tick faint xs">Market data unavailable — run
        <code>python3 -m pipeline.run all</code> to populate site/data.</span>`;
    }
  }
}

/* -------------------------------------------------------- pushed updates
 *
 * Patch the two duplicated copies of each instrument in place and flash the
 * price. Only touches the DOM for instruments that actually moved, so the strip
 * keeps scrolling smoothly at a 1-3s update rate.
 */
function patchInstruments(feedId, instruments) {
  if (feedId !== currentExchange() || !track) return;

  instruments.forEach((q) => {
    const sym = String(q.symbol || q.name || '').toUpperCase();
    if (!sym || q.last == null) return;

    // keep the in-memory snapshot in step so an exchange switch shows fresh data
    const feed = tickerData?.feeds?.[feedId];
    if (feed) {
      const list = (feed.instruments ||= []);
      const at = list.findIndex((x) => String(x.symbol || x.name || '').toUpperCase() === sym);
      if (at >= 0) list[at] = { ...list[at], ...q };
      else list.push(q);
    }

    const nodes = track.querySelectorAll(`[data-sym="${CSS.escape(sym)}"]`);
    nodes.forEach((node) => {
      const cell = node.querySelector('[data-role="last"]');
      if (!cell) return;
      const next = q.last.toLocaleString('en-IN');
      if (cell.textContent === next) return;
      const rose = q.change_pct != null ? q.change_pct >= 0 : true;
      cell.textContent = next;
      node.classList.remove('flash-up', 'flash-down');
      // reflow so the animation restarts even on consecutive ticks
      void node.offsetWidth;
      node.classList.add(rose ? 'flash-up' : 'flash-down');
    });
  });

}

function openStream() {
  if (!('EventSource' in window)) return null;
  let es;
  try {
    es = new EventSource('/api/stream');
  } catch {
    return null;
  }

  es.addEventListener('snapshot', (ev) => {
    try {
      tickerData = JSON.parse(ev.data);
      paint();
      clearInterval(pollTimer);      // the stream supersedes polling
      pollTimer = null;
    } catch { /* keep whatever we had */ }
  });

  es.addEventListener('quotes', (ev) => {
    try {
      const d = JSON.parse(ev.data);
      const feed = tickerData?.feeds?.[d.feed || d.exchange];
      if (feed && d.status) feed.status = d.status;
      if (feed && d.as_of) feed.as_of = d.as_of;
      patchInstruments(d.feed || d.exchange, d.instruments || []);
    } catch { /* ignore a malformed frame */ }
  });

  es.addEventListener('error', () => {
    // EventSource reconnects on its own; poll meanwhile so the strip stays fresh.
    if (!pollTimer && document.visibilityState === 'visible') {
      pollTimer = setInterval(refreshTicker, POLL_MS);
    }
  });

  return es;
}

async function initTicker() {
  if (!select || !track) return;
  const saved = localStorage.getItem(EXCH_KEY);
  if (saved && [...select.options].some((o) => o.value === saved)) select.value = saved;

  select.addEventListener('change', () => {
    localStorage.setItem(EXCH_KEY, select.value);
    paint();
  });

  await refreshTicker();          // paint immediately from the static file
  const stream = openStream();    // then upgrade to pushed updates if available

  const schedule = () => {
    clearInterval(pollTimer);
    pollTimer = null;
    // With a live stream there is nothing to poll for.
    if (!stream && document.visibilityState === 'visible') {
      pollTimer = setInterval(refreshTicker, POLL_MS);
    }
  };
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible' && !stream) refreshTicker();
    schedule();
  });
  schedule();
}

initTicker();
render();
