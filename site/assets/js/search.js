/* Global search: a client-side filter over a precomputed index
 * (/data/search.json), not a live query against anything. Same
 * static-JSON-only contract as the rest of the site - see store.js.
 *
 * The index covers every page family the pipeline writes (brokers, stocks,
 * ETFs, funds, SEBI entities, indices, broker/AMC hubs, reports, calculators,
 * core pages). It's fetched lazily, only on first open, so it never adds
 * weight to a page a visitor doesn't search from.
 */
import { esc, loadSearchIndex } from './store.js?v=b59cf0df04';
import './theme-audio.js?v=070f2dae6b';
import './footer-film.js?v=501ba51011';
import './ad-track.js?v=66ff17d053';

const toggle = document.getElementById('search-toggle');
const overlay = document.getElementById('search-overlay');
const input = document.getElementById('search-input');
const resultsEl = document.getElementById('search-results');
const clearBtn = document.getElementById('search-clear');

const TRENDING = [
  'NIFTY 50', 'Zerodha', 'Gold ETF', 'Swiggy IPO', 'HDFC Bank',
  'SIP Calculator', 'Angel One vs Zerodha', 'Groww'
];

const TYPE_LABEL = {
  broker: 'Broker', stock: 'Stock', etf: 'ETF', fund: 'Mutual fund',
  sebi: 'SEBI registry', index: 'Index', hub: 'Browse', report: 'Report',
  calc: 'Calculator', page: 'Page', crypto: 'Crypto', news: 'News', compare: 'Comparison', ipo: 'IPO',
};

const FILTERS = [
  { id: 'all', label: 'All' },
  { id: 'broker', label: 'Broker' },
  { id: 'sebi', label: 'SEBI Registry' },
  { id: 'stock', label: 'Stock' },
  { id: 'etf', label: 'ETF' },
  { id: 'fund', label: 'Mutual Fund' },
  { id: 'ipo', label: 'IPO' },
  { id: 'compare', label: 'Comparison' },
];

let index = null;
let indexPromise = null;
let active = -1;
let shown = [];
let currentFilter = 'all';

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

  // Multi-word fallback: the checks above only match when the query is one
  // contiguous phrase, so "zerodha fees" would never match a "Zerodha"
  // broker row or a "Brokerage Fee Calculator" row even though both are
  // exactly what that search means. Require every word to appear somewhere
  // across name+subtitle (order-independent), scored below every exact/
  // phrase match above so it only surfaces when nothing better exists.
  const tokens = q.split(/\s+/).filter(Boolean);
  if (tokens.length > 1) {
    const haystack = name + ' ' + sub;
    if (tokens.every((t) => haystack.includes(t))) {
      return 10 + tokens.filter((t) => name.includes(t)).length;
    }
  }
  return 0;
}

function search(q, filterType) {
  if (!index) return [];
  const needle = (q || '').trim().toLowerCase();
  const target = filterType || currentFilter;

  let candidates = index;
  if (target !== 'all') {
    candidates = candidates.filter((row) => row[2] === target);
  }

  if (!needle) {
    if (target !== 'all') {
      return candidates.slice(0, 20);
    }
    return [];
  }

  return candidates
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
  const needle = (q || '').trim();
  if (!needle && currentFilter === 'all') {
    resultsEl.innerHTML = '<div class="search-empty-state">'
      + '<div class="search-hint">Search brokers, stocks, mutual funds, ETFs, '
      + 'SEBI-registered entities and calculators by name.</div>'
      + '<div class="search-trending-title">Trending &amp; Popular Searches</div>'
      + '<div class="search-trending-chips">'
      + TRENDING.map((t) => '<button type="button" class="search-trending-chip" data-query="' + esc(t) + '">' + esc(t) + '</button>').join('')
      + '</div>'
      + '</div>';
    shown = [];
    active = -1;
    return;
  }
  shown = search(needle, currentFilter);
  active = shown.length ? 0 : -1;
  if (!shown.length) {
    const fObj = FILTERS.find((f) => f.id === currentFilter);
    const scopeSuffix = fObj && fObj.id !== 'all' ? ' in ' + fObj.label : '';
    resultsEl.innerHTML = '<div class="search-empty">No matches for "' + esc(needle) + '"' + esc(scopeSuffix) + '.</div>';
    return;
  }
  let lastType = null;
  resultsEl.innerHTML = shown.map((row, i) => {
    const [name, url, type, sub] = row;
    const groupHead = (currentFilter === 'all' && type !== lastType)
      ? '<div class="search-group-label">' + esc(TYPE_LABEL[type] || type) + '</div>' : '';
    lastType = type;
    return groupHead
      + '<a class="search-row' + (i === active ? ' active' : '') + '" href="' + esc(url) + '" data-idx="' + i + '">'
      + '<span class="n">' + esc(name) + '</span>'
      + (sub ? '<span class="s">' + esc(sub) + '</span>' : '')
      + '</a>';
  }).join('');
}

function syncFilterButtons(bar) {
  if (!bar) return;
  bar.querySelectorAll('.search-filter-btn').forEach((b) => {
    b.setAttribute('aria-pressed', b.dataset.filter === currentFilter ? 'true' : 'false');
  });
}

function setupFilterBar() {
  const modal = overlay ? overlay.querySelector('.search-modal') : null;
  if (!modal) return;
  let bar = modal.querySelector('.search-filter-bar');
  if (!bar) {
    bar = document.createElement('div');
    bar.className = 'search-filter-bar';
    bar.setAttribute('role', 'tablist');
    bar.setAttribute('aria-label', 'Filter search categories');
    const inputRow = modal.querySelector('.search-input-row');
    if (inputRow && resultsEl) {
      modal.insertBefore(bar, resultsEl);
    } else {
      modal.appendChild(bar);
    }
  }

  if (!bar.children.length) {
    bar.innerHTML = FILTERS.map((f) => {
      const isPressed = f.id === currentFilter;
      return '<button type="button" class="search-filter-btn" data-filter="' + esc(f.id) + '" '
        + 'aria-pressed="' + (isPressed ? 'true' : 'false') + '">'
        + esc(f.label)
        + '</button>';
    }).join('');
  }

  bar.onclick = (e) => {
    const btn = e.target.closest('.search-filter-btn');
    if (!btn) return;
    const fId = btn.dataset.filter;
    if (fId === currentFilter) return;
    currentFilter = fId;
    syncFilterButtons(bar);
    render(input ? input.value : '');
    if (input) input.focus();
  };
}

function setActive(i) {
  const rows = resultsEl.querySelectorAll('.search-row');
  if (!rows.length) return;
  active = (i + rows.length) % rows.length;
  rows.forEach((r, idx) => r.classList.toggle('active', idx === active));
  rows[active].scrollIntoView({ block: 'nearest' });
}

function syncClearButton() {
  if (clearBtn) {
    clearBtn.hidden = !input || !input.value.trim();
  }
}

function open() {
  if (!overlay) return;
  overlay.hidden = false;
  input.value = '';
  syncClearButton();
  currentFilter = 'all';
  setupFilterBar();
  const modal = overlay.querySelector('.search-modal');
  if (modal) {
    const bar = modal.querySelector('.search-filter-bar');
    syncFilterButtons(bar);
  }
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

clearBtn?.addEventListener('click', () => {
  if (!input) return;
  input.value = '';
  syncClearButton();
  render('');
  input.focus();
});

resultsEl?.addEventListener('click', (e) => {
  const chip = e.target.closest('.search-trending-chip');
  if (!chip || !input) return;
  const q = chip.dataset.query || chip.textContent.trim();
  input.value = q;
  syncClearButton();
  render(q);
  input.focus();
});

input?.addEventListener('input', () => {
  syncClearButton();
  render(input.value);
});

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

// Setup filter bar immediately on load so static pre-rendered modals are wired up
setupFilterBar();
