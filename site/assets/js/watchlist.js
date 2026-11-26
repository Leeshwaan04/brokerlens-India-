/* User-facing Watchlist stored locally in browser localStorage.
 * Zero PII, zero server tracking, works across all static pages and the SPA shell.
 */
import { safeUrl } from './store.js?v=b59cf0df04';

const STORAGE_KEY = 'bl_watchlist_v1';
const MAX_ITEMS = 100;

const STARTER_PACK = [
  { symbol: 'RELIANCE', name: 'Reliance Industries Limited', type: 'Stock', url: '/stock/reliance/' },
  { symbol: 'TCS', name: 'Tata Consultancy Services Limited', type: 'Stock', url: '/stock/tcs/' },
  { symbol: 'HDFCBANK', name: 'HDFC Bank Limited', type: 'Stock', url: '/stock/hdfcbank/' },
  { symbol: 'INFY', name: 'Infosys Limited', type: 'Stock', url: '/stock/infy/' },
  { symbol: 'NIFTYBEES', name: 'Nippon India ETF Nifty 50 BeES', type: 'ETF', url: '/etf/niftybees/' },
];

let searchCache = null;

function sanitizeItem(item) {
  if (!item || typeof item !== 'object') return null;
  const symbol = String(item.symbol || '').trim().toUpperCase().slice(0, 24);
  const name = String(item.name || symbol).trim().slice(0, 120);
  const type = String(item.type || 'Stock').trim().slice(0, 20);
  const rawUrl = String(item.url || '').trim();
  if (!symbol || !rawUrl.startsWith('/')) return null;
  const url = safeUrl(rawUrl);
  if (!url || url === '#') return null;
  return { symbol, name, type, url };
}

export function getWatchlist() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.map(sanitizeItem).filter(Boolean).slice(0, MAX_ITEMS);
  } catch {
    return [];
  }
}

function saveWatchlist(list) {
  try {
    const clean = (Array.isArray(list) ? list : []).map(sanitizeItem).filter(Boolean).slice(0, MAX_ITEMS);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(clean));
    window.dispatchEvent(new CustomEvent('bl:watchlist-changed', { detail: clean }));
  } catch {
    /* ignore quota errors */
  }
}

export function isWatched(symbol) {
  const sym = String(symbol || '').trim().toUpperCase();
  return getWatchlist().some((i) => i.symbol === sym);
}

export function toggleWatchlistItem(item) {
  const clean = sanitizeItem(item);
  if (!clean) return false;
  const list = getWatchlist();
  const idx = list.findIndex((i) => i.symbol === clean.symbol);
  let added = false;
  if (idx >= 0) {
    list.splice(idx, 1);
  } else {
    list.unshift(clean);
    added = true;
  }
  saveWatchlist(list);
  return added;
}

function removeWatchlistItem(symbol) {
  const sym = String(symbol || '').trim().toUpperCase();
  const list = getWatchlist().filter((i) => i.symbol !== sym);
  saveWatchlist(list);
}

async function fetchSearchIndex() {
  if (searchCache) return searchCache;
  try {
    const r = await fetch('/data/search.json');
    if (!r.ok) return [];
    const data = await r.json();
    searchCache = Array.isArray(data) ? data : [];
    return searchCache;
  } catch {
    return [];
  }
}

function detectCurrentAsset() {
  const path = location.pathname;
  const stockMatch = path.match(/^\/stock\/([a-z0-9-]+)\/?$/i);
  const etfMatch = path.match(/^\/etf\/([a-z0-9-]+)\/?$/i);
  const cryptoMatch = path.match(/^\/crypto\/([a-z0-9-]+)\/?$/i);
  if (!stockMatch && !etfMatch && !cryptoMatch) return null;

  const h1 = document.querySelector('h1');
  const title = h1 ? h1.textContent.trim() : '';
  const slug = (stockMatch || etfMatch || cryptoMatch)[1];
  const type = stockMatch ? 'Stock' : etfMatch ? 'ETF' : 'Crypto';

  // Extract ticker symbol if present in subtitle ("NSE: RELIANCE")
  let symbol = slug.toUpperCase();
  const mutedP = h1 && h1.nextElementSibling ? h1.nextElementSibling.textContent : '';
  const nseMatch = mutedP.match(/(?:NSE|BSE|Ticker):\s*([A-Z0-9&.-]+)/i);
  if (nseMatch) {
    symbol = nseMatch[1].toUpperCase();
  }
  return {
    symbol,
    name: title || symbol,
    type,
    url: path.endsWith('/') ? path : `${path}/`,
  };
}

function createStarSvg(filled) {
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('width', '15');
  svg.setAttribute('height', '15');
  svg.setAttribute('viewBox', '0 0 16 16');
  svg.setAttribute('aria-hidden', 'true');
  const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
  path.setAttribute('d', 'M8 1.3l2.06 4.18 4.61.67-3.33 3.25.79 4.59L8 11.82l-4.13 2.17.79-4.59L1.33 6.15l4.61-.67L8 1.3z');
  path.setAttribute('fill', filled ? 'currentColor' : 'none');
  path.setAttribute('stroke', 'currentColor');
  path.setAttribute('stroke-width', '1.4');
  path.setAttribute('stroke-linejoin', 'round');
  svg.appendChild(path);
  return svg;
}

function mountPageWatchButton() {
  const asset = detectCurrentAsset();
  if (!asset) return;
  const h1 = document.querySelector('h1');
  if (!h1 || document.getElementById('page-watch-btn')) return;

  const row = document.createElement('div');
  row.className = 'watch-page-row';

  const btn = document.createElement('button');
  btn.id = 'page-watch-btn';
  btn.type = 'button';
  btn.className = 'btn btn-outline btn-sm watch-page-btn';

  const syncBtn = () => {
    const active = isWatched(asset.symbol);
    btn.replaceChildren(createStarSvg(active));
    const lbl = document.createElement('span');
    lbl.textContent = active ? 'Watching' : 'Add to Watchlist';
    btn.appendChild(lbl);
    btn.setAttribute('aria-pressed', active ? 'true' : 'false');
    btn.classList.toggle('is-watched', active);
  };

  btn.addEventListener('click', () => {
    toggleWatchlistItem(asset);
    syncBtn();
  });

  window.addEventListener('bl:watchlist-changed', syncBtn);
  syncBtn();

  h1.insertAdjacentElement('afterend', row);
  row.appendChild(btn);
}

function buildDrawer() {
  if (document.getElementById('watchlist-drawer')) return;

  const backdrop = document.createElement('div');
  backdrop.id = 'watchlist-backdrop';
  backdrop.className = 'wl-backdrop';
  backdrop.hidden = true;

  const drawer = document.createElement('aside');
  drawer.id = 'watchlist-drawer';
  drawer.className = 'wl-drawer';
  drawer.setAttribute('role', 'dialog');
  drawer.setAttribute('aria-modal', 'true');
  drawer.setAttribute('aria-label', 'My Watchlist');
  drawer.hidden = true;

  // Header
  const head = document.createElement('div');
  head.className = 'wl-head';
  const titleWrap = document.createElement('div');
  const h2 = document.createElement('h2');
  h2.textContent = 'My Watchlist';
  h2.className = 'wl-title';
  const sub = document.createElement('div');
  sub.className = 'xs muted';
  sub.textContent = 'Saved locally on this browser';
  titleWrap.appendChild(h2);
  titleWrap.appendChild(sub);

  const closeBtn = document.createElement('button');
  closeBtn.type = 'button';
  closeBtn.className = 'icon-btn';
  closeBtn.setAttribute('aria-label', 'Close Watchlist');
  closeBtn.textContent = '×';

  head.appendChild(titleWrap);
  head.appendChild(closeBtn);

  // Quick Add Search
  const searchBox = document.createElement('div');
  searchBox.className = 'wl-search-box';
  const searchInput = document.createElement('input');
  searchInput.type = 'text';
  searchInput.className = 'wl-search-input';
  searchInput.placeholder = 'Quick add stock, ETF, or crypto...';
  searchInput.setAttribute('aria-label', 'Add symbol to watchlist');
  const searchResults = document.createElement('div');
  searchResults.className = 'wl-search-results';
  searchResults.hidden = true;
  searchBox.appendChild(searchInput);
  searchBox.appendChild(searchResults);

  // Body list
  const body = document.createElement('div');
  body.className = 'wl-body';

  // Footer
  const foot = document.createElement('div');
  foot.className = 'wl-foot';
  const paperLink = document.createElement('a');
  paperLink.href = 'https://paper.brokerlens.in/';
  paperLink.target = '_blank';
  paperLink.rel = 'noopener';
  paperLink.className = 'btn btn-primary btn-sm';
  paperLink.textContent = 'Open Virtual Trading ->';
  const clearBtn = document.createElement('button');
  clearBtn.type = 'button';
  clearBtn.className = 'btn btn-outline btn-sm';
  clearBtn.textContent = 'Clear';
  foot.appendChild(paperLink);
  foot.appendChild(clearBtn);

  drawer.appendChild(head);
  drawer.appendChild(searchBox);
  drawer.appendChild(body);
  drawer.appendChild(foot);
  document.body.appendChild(backdrop);
  document.body.appendChild(drawer);

  const closeDrawer = () => {
    drawer.hidden = true;
    backdrop.hidden = true;
    const navBtn = document.getElementById('watchlist-toggle');
    if (navBtn) navBtn.focus();
  };

  const openDrawer = () => {
    renderList();
    drawer.hidden = false;
    backdrop.hidden = false;
    searchInput.focus();
  };

  closeBtn.addEventListener('click', closeDrawer);
  backdrop.addEventListener('click', closeDrawer);
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && !drawer.hidden) closeDrawer();
  });

  clearBtn.addEventListener('click', () => {
    if (getWatchlist().length === 0) return;
    saveWatchlist([]);
  });

  // Search filter handler
  let debounceTimer = null;
  searchInput.addEventListener('input', () => {
    clearTimeout(debounceTimer);
    const q = searchInput.value.trim().toLowerCase();
    if (q.length < 2) {
      searchResults.hidden = true;
      searchResults.replaceChildren();
      return;
    }
    debounceTimer = setTimeout(async () => {
      const idx = await fetchSearchIndex();
      const hits = idx
        .filter((r) => {
          const url = String(r[1] || '');
          if (!url.startsWith('/stock/') && !url.startsWith('/etf/') && !url.startsWith('/crypto/')) return false;
          const title = String(r[0] || '').toLowerCase();
          const subText = String(r[3] || '').toLowerCase();
          return title.includes(q) || subText.includes(q);
        })
        .slice(0, 6);

      searchResults.replaceChildren();
      if (!hits.length) {
        const empty = document.createElement('div');
        empty.className = 'xs muted wl-search-empty';
        empty.textContent = 'No matching instruments found.';
        searchResults.appendChild(empty);
      } else {
        hits.forEach((h) => {
          const url = String(h[1] || '');
          const type = url.startsWith('/etf/') ? 'ETF' : url.startsWith('/crypto/') ? 'Crypto' : 'Stock';
          const symMatch = String(h[3] || '').match(/([A-Z0-9&.-]+)/);
          const slugSym = url.split('/').filter(Boolean).pop().toUpperCase();
          const sym = (symMatch && symMatch[1].length <= 15) ? symMatch[1] : slugSym;
          const row = document.createElement('button');
          row.type = 'button';
          row.className = 'wl-search-item';

          const info = document.createElement('span');
          const strong = document.createElement('strong');
          strong.textContent = sym;
          const nameSpan = document.createElement('span');
          nameSpan.className = 'xs muted';
          nameSpan.textContent = ` ${String(h[0] || '')}`;
          info.appendChild(strong);
          info.appendChild(nameSpan);

          const action = document.createElement('span');
          action.className = 'badge';
          action.textContent = isWatched(sym) ? 'Added' : `+ ${type}`;

          row.appendChild(info);
          row.appendChild(action);
          row.addEventListener('click', () => {
            if (!isWatched(sym)) {
              toggleWatchlistItem({ symbol: sym, name: String(h[0] || sym), type, url });
            }
            searchInput.value = '';
            searchResults.hidden = true;
            searchResults.replaceChildren();
          });
          searchResults.appendChild(row);
        });
      }
      searchResults.hidden = false;
    }, 150);
  });

  function renderList() {
    const list = getWatchlist();
    body.replaceChildren();

    if (!list.length) {
      const emptyWrap = document.createElement('div');
      emptyWrap.className = 'wl-empty';
      const p = document.createElement('p');
      p.className = 'small muted';
      p.textContent = 'Your watchlist is empty. Search above or tap "Add to Watchlist" on any stock, ETF, or crypto page.';
      const starterBtn = document.createElement('button');
      starterBtn.type = 'button';
      starterBtn.className = 'btn btn-outline btn-sm';
      starterBtn.textContent = '+ Load Nifty 50 Starter Pack';
      starterBtn.addEventListener('click', () => {
        saveWatchlist(STARTER_PACK);
      });
      emptyWrap.appendChild(p);
      emptyWrap.appendChild(starterBtn);
      body.appendChild(emptyWrap);
      clearBtn.disabled = true;
      return;
    }

    clearBtn.disabled = false;
    list.forEach((item) => {
      const card = document.createElement('div');
      card.className = 'wl-item';

      const main = document.createElement('div');
      main.className = 'wl-item-main';
      const link = document.createElement('a');
      link.href = safeUrl(item.url);
      link.className = 'wl-item-link';
      const symEl = document.createElement('strong');
      symEl.textContent = item.symbol;
      const badge = document.createElement('span');
      badge.className = 'badge';
      badge.textContent = item.type;
      const nameEl = document.createElement('div');
      nameEl.className = 'xs muted wl-item-name';
      nameEl.textContent = item.name;
      link.appendChild(symEl);
      link.appendChild(document.createTextNode(' '));
      link.appendChild(badge);
      link.appendChild(nameEl);
      main.appendChild(link);

      const actions = document.createElement('div');
      actions.className = 'wl-item-actions';

      if (item.type === 'Stock') {
        const tradeBtn = document.createElement('a');
        tradeBtn.href = safeUrl(`https://paper.brokerlens.in/trade?symbol=${encodeURIComponent(item.symbol)}`);
        tradeBtn.target = '_blank';
        tradeBtn.rel = 'noopener';
        tradeBtn.className = 'badge wl-trade-badge';
        tradeBtn.textContent = 'Practise';
        tradeBtn.title = `Practise trading ${item.symbol} with virtual money`;
        actions.appendChild(tradeBtn);
      }

      const rmBtn = document.createElement('button');
      rmBtn.type = 'button';
      rmBtn.className = 'icon-btn wl-rm-btn';
      rmBtn.setAttribute('aria-label', `Remove ${item.symbol} from watchlist`);
      rmBtn.textContent = '×';
      rmBtn.addEventListener('click', () => removeWatchlistItem(item.symbol));
      actions.appendChild(rmBtn);

      card.appendChild(main);
      card.appendChild(actions);
      body.appendChild(card);
    });
  }

  window.addEventListener('bl:watchlist-changed', renderList);
  window.addEventListener('storage', (e) => {
    if (e.key === STORAGE_KEY) {
      renderList();
      window.dispatchEvent(new CustomEvent('bl:watchlist-changed', { detail: getWatchlist() }));
    }
  });

  return { openDrawer };
}

function mountNavbarWatchlist() {
  const searchBtn = document.getElementById('search-toggle');
  if (!searchBtn || document.getElementById('watchlist-toggle')) return;

  const drawerApi = buildDrawer();

  const btn = document.createElement('button');
  btn.id = 'watchlist-toggle';
  btn.type = 'button';
  btn.className = 'icon-btn watchlist-nav-btn';
  btn.title = 'My Watchlist';
  btn.setAttribute('aria-label', 'My Watchlist');

  const countBadge = document.createElement('span');
  countBadge.className = 'wl-count-badge';

  const syncCount = () => {
    const n = getWatchlist().length;
    countBadge.textContent = n > 0 ? String(n) : '';
    countBadge.hidden = n === 0;
    btn.setAttribute('aria-label', n > 0 ? `My Watchlist (${n})` : 'My Watchlist');
  };

  btn.appendChild(createStarSvg(false));
  btn.appendChild(countBadge);
  btn.addEventListener('click', () => drawerApi && drawerApi.openDrawer());
  window.addEventListener('bl:watchlist-changed', syncCount);
  syncCount();

  searchBtn.insertAdjacentElement('afterend', btn);
}

function initWatchlist() {
  mountNavbarWatchlist();
  mountPageWatchButton();
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initWatchlist);
} else {
  initWatchlist();
}
