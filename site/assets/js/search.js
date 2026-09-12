/* Global search: a client-side filter over a precomputed index
 * (/data/search.json), not a live query against anything. Same
 * static-JSON-only contract as the rest of the site - see store.js.
 *
 * The index covers every page family the pipeline writes (brokers, stocks,
 * ETFs, funds, SEBI entities, indices, broker/AMC hubs, reports, calculators,
 * core pages). It's fetched lazily, only on first open, so it never adds
 * weight to a page a visitor doesn't search from.
 */
import { esc, loadSearchIndex } from './store.js?v=557d965307';

const toggle = document.getElementById('search-toggle');
const overlay = document.getElementById('search-overlay');
const input = document.getElementById('search-input');
const resultsEl = document.getElementById('search-results');

const TYPE_LABEL = {
  broker: 'Broker', stock: 'Stock', etf: 'ETF', fund: 'Mutual fund',
  sebi: 'SEBI registry', index: 'Index', hub: 'Browse', report: 'Report',
  calc: 'Calculator', page: 'Page', crypto: 'Crypto',
};

let index = null;
let indexPromise = null;
let active = -1;
let shown = [];

function ensureIndex() {
  if (!indexPromise) {
    indexPromise = loadSearchIndex().then((rows) => { index = rows; return rows; });
  }
  return indexPromise;
}

function score(row, q) {
  const name = row[0].toLowerCase();
  const sub = (row[3] || '').toLowerCase();
  if (name === q) return 100;
  if (name.startsWith(q)) return 80;
  if (sub === q) return 70;
  if (sub.startsWith(q)) return 60;
  if (name.includes(q)) return 40;
  if (sub.includes(q)) return 20;
  return 0;
}

function search(q) {
  if (!index || !q) return [];
  const needle = q.trim().toLowerCase();
  if (!needle) return [];
  return index
    .map((row) => [score(row, needle), row])
    .filter(([s]) => s > 0)
    .sort((a, b) => b[0] - a[0])
    .slice(0, 30)
    .map(([, row]) => row);
}

function render(q) {
  if (!index) {
    resultsEl.innerHTML = '<div class="search-hint">Loading search index...</div>';
    return;
  }
  if (!q.trim()) {
    resultsEl.innerHTML = '<div class="search-hint">Search brokers, stocks, mutual funds, ETFs, '
      + 'SEBI-registered entities and calculators by name.</div>';
    shown = [];
    active = -1;
    return;
  }
  shown = search(q);
  active = shown.length ? 0 : -1;
  if (!shown.length) {
    resultsEl.innerHTML = '<div class="search-empty">No matches for "' + esc(q) + '".</div>';
    return;
  }
  let lastType = null;
  resultsEl.innerHTML = shown.map((row, i) => {
    const [name, url, type, sub] = row;
    const groupHead = type !== lastType
      ? '<div class="search-group-label">' + esc(TYPE_LABEL[type] || type) + '</div>' : '';
    lastType = type;
    return groupHead
      + '<a class="search-row' + (i === active ? ' active' : '') + '" href="' + esc(url) + '" data-idx="' + i + '">'
      + '<span class="n">' + esc(name) + '</span>'
      + (sub ? '<span class="s">' + esc(sub) + '</span>' : '')
      + '</a>';
  }).join('');
}

function setActive(i) {
  const rows = resultsEl.querySelectorAll('.search-row');
  if (!rows.length) return;
  active = (i + rows.length) % rows.length;
  rows.forEach((r, idx) => r.classList.toggle('active', idx === active));
  rows[active].scrollIntoView({ block: 'nearest' });
}

function open() {
  if (!overlay) return;
  overlay.hidden = false;
  input.value = '';
  render('');
  ensureIndex().then(() => render(input.value));
  setTimeout(() => input.focus(), 0);
}

function close() {
  if (!overlay) return;
  overlay.hidden = true;
  toggle?.focus();
}

toggle?.addEventListener('click', open);

overlay?.addEventListener('click', (e) => {
  if (e.target === overlay) close();
});

input?.addEventListener('input', () => render(input.value));

input?.addEventListener('keydown', (e) => {
  if (e.key === 'ArrowDown') { e.preventDefault(); setActive(active + 1); }
  else if (e.key === 'ArrowUp') { e.preventDefault(); setActive(active - 1); }
  else if (e.key === 'Enter') {
    e.preventDefault();
    const row = shown[active];
    if (row) location.href = row[1];
  }
});

document.addEventListener('keydown', (e) => {
  if (overlay && !overlay.hidden && e.key === 'Escape') { close(); return; }
  const meta = e.metaKey || e.ctrlKey;
  if (meta && e.key.toLowerCase() === 'k') {
    e.preventDefault();
    if (overlay && !overlay.hidden) close(); else open();
  }
});
