/* Mobile hamburger nav and the market-timings mega menu, shared between
 * app.js (the SPA shell) and every static page (registry, stock, index,
 * etf, fund, report, calculator). Extracted out of app.js so both places
 * run the exact same code instead of two copies drifting apart.
 *
 * The mega menu specifically cannot be pre-rendered at build time: "is this
 * session live right now" is computed from the current IST clock at view
 * time, and a static page can be viewed hours or days after its last build.
 * Baking in a live/closed status here would go stale exactly the way the
 * project has already been burned by once (the MCX ticker status bug). It
 * loads the same static /data/timings.json every other page uses and does
 * the live/closed math client-side, on every view.
 */
import { esc, loadTimings, safeUrl } from './store.js?v=b59cf0df04';
import './watchlist.js?v=51a60d4e37';

/* ------------------------------------------------------------- mobile nav */

const navToggle = document.getElementById('nav-toggle');
const navLinks = document.getElementById('navlinks');

/* Every dropdown registers its close function here, so opening one closes the
 * rest and closing the phone drawer closes whatever is open inside it. */
const dropdownClosers = [];
const closeAllDropdowns = (except) => dropdownClosers.forEach(([panel, close]) => { if (panel !== except) close(); });

function setNav(open) {
  if (!navLinks || !navToggle) return;
  navLinks.classList.toggle('open', open);
  navToggle.setAttribute('aria-expanded', String(open));
  if (!open) closeAllDropdowns();
}

navToggle?.addEventListener('click', (e) => {
  e.stopPropagation();
  setNav(!navLinks.classList.contains('open'));
});
// Following any link inside the drawer must close it (data-link on the SPA
// shell, plain <a> on every static page - either one navigates away).
navLinks?.addEventListener('click', (e) => {
  if (e.target.closest('a')) setNav(false);
});
// The dropdown panels sit outside the drawer's element, so a link followed from
// one (including a client-side route on the single-page shell, which does not
// reload the page) must close the drawer too.
document.querySelectorAll('.mega').forEach((m) =>
  m.addEventListener('click', (e) => { if (e.target.closest('a')) setNav(false); }));
// Escape closes the drawer only; each dropdown handles its own Escape (and returns
// focus to its button), which would not work if the drawer closed it first.
document.addEventListener('keydown', (e) => {
  if (e.key !== 'Escape' || !navLinks || !navToggle) return;
  navLinks.classList.remove('open');
  navToggle.setAttribute('aria-expanded', 'false');
});

/* ------------------------------------------------- timings mega menu
 *
 * Session timings per exchange/segment, curated in config/market_timings.json
 * and published as /data/timings.json. Highlighting is computed in IST at open
 * time, so the menu shows which sessions are live right now. Holiday calendars
 * are yearly circulars - we link to them rather than mirroring them, so a
 * one-off exchange notice never needs a code change to stay accurate.
 */

const megaBtn = document.getElementById('timings-toggle');
const megaPanel = document.getElementById('mega-timings');
const megaBody = document.getElementById('mega-timings-body');

/* Minutes since midnight + weekday, in IST, regardless of the viewer's zone. */
function istNow() {
  const parts = new Intl.DateTimeFormat('en-GB', {
    timeZone: 'Asia/Kolkata', hour: '2-digit', minute: '2-digit',
    weekday: 'short', hour12: false,
  }).formatToParts(new Date());
  const get = (t) => parts.find((p) => p.type === t)?.value;
  return {
    min: Number(get('hour')) * 60 + Number(get('minute')),
    weekday: get('weekday'),
    hhmm: `${get('hour')}:${get('minute')}`,
  };
}

const toMin = (hhmm) => {
  const [h, m] = String(hhmm).split(':').map(Number);
  return h * 60 + m;
};

const DAY_ORDER = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];

/* Sessions are stored 24h for comparisons; the audience reads 12h. */
const fmt12 = (min) => {
  const h = Math.floor(min / 60);
  const h12 = h % 12 || 12;
  return `${h12}:${String(min % 60).padStart(2, '0')} ${h < 12 ? 'am' : 'pm'}`;
};

/* When the next normal session starts, ignoring holidays (footer carries that
 * caveat). Returns e.g. "today 09:00", "tomorrow 09:15", "Mon 09:00". */
function nextOpen(ex, now) {
  const starts = [];
  (ex.segments || []).forEach((sg) => (sg.sessions || []).forEach((s) => {
    if (s.kind === 'normal') starts.push(toMin(s.start));
  }));
  if (!starts.length) return null;
  const earliest = Math.min(...starts);
  const hhmm = fmt12(earliest);
  const today = DAY_ORDER.indexOf(now.weekday);
  for (let d = 0; d <= 7; d++) {
    const wd = (today + d) % 7;
    if (wd === 0 || wd === 6) continue;                 // weekend
    if (d === 0 && now.min >= earliest) continue;       // today's open already passed
    const when = d === 0 ? 'today' : d === 1 ? 'tomorrow' : DAY_ORDER[wd];
    return `${when} ${hhmm}`;
  }
  return null;
}

function renderMega(t) {
  const now = istNow();
  const tradingDay = !['Sat', 'Sun'].includes(now.weekday);
  const liveNow = (s) => tradingDay && now.min >= toMin(s.start) && now.min < toMin(s.end);
  const range = (s) => `${fmt12(toMin(s.start))} to ${fmt12(toMin(s.end))}`;

  const cols = (t.exchanges || []).map((ex) => {
    const anyLive = (ex.segments || []).some((sg) => (sg.sessions || []).some(liveNow));
    const opens = anyLive ? null : nextOpen(ex, now);

    const segs = (ex.segments || []).map((sg) => {
      const sessions = sg.sessions || [];
      const main = sessions.find((s) => s.kind === 'normal') || sessions[0];
      const subs = sessions.filter((s) => s !== main);
      return `<div class="mega-seg">
        <div class="mega-seg-head ${liveNow(main) ? 'live' : ''}"${main.note ? ` title="${esc(main.note)}"` : ''}>
          <span>${esc(sg.label)}${main.note ? ' *' : ''}</span>
          <span class="t">${range(main)}</span>
        </div>
        ${subs.map((s) => `
          <div class="sess ${liveNow(s) ? 'live' : ''}"${s.note ? ` title="${esc(s.note)}"` : ''}>
            <span>${esc(s.label)}${s.note ? ' *' : ''}</span>
            <span class="t">${range(s)}</span>
          </div>`).join('')}
      </div>`;
    }).join('');

    return `<div class="mega-col">
      <h4>${esc(ex.id)}
        <span class="badge ${anyLive ? 'badge-up' : ''}">${anyLive ? 'Open' : 'Closed'}</span>
        ${opens ? `<span class="xs faint">opens ${esc(opens)} IST</span>` : ''}
      </h4>
      ${segs}
    </div>`;
  }).join('');

  const holidays = (t.holiday_links || []).map((h) =>
    `<a href="${safeUrl(h.url)}" target="_blank" rel="noopener">${esc(h.exchange)}</a>`).join(' · ');

  megaBody.innerHTML = `${cols}
    <div class="mega-foot">
      All times IST. Now ${fmt12(now.min)}${tradingDay ? '' : ' (weekend, markets closed)'}.
      Sessions run Mon to Fri except exchange holidays: <a href="/stock-market-holidays/">NSE holiday list</a>; exchange calendars: ${holidays}.
      * hover for detail. Curated from exchange material, last reviewed ${esc((t.last_reviewed || '').slice(0, 10))}.
      Verify with the exchange before relying on an edge case.
    </div>`;
}

/* Generic open/close/hover/escape/outside-click wiring, shared by every
 * button+panel dropdown in the nav (market timings, markets). Extracted
 * after a second dropdown (markets) needed the exact same behaviour - one
 * copy is a pattern, two hand-written copies are a maintenance bug waiting
 * to happen when only one gets a future fix. */
function wireDropdown(btn, panel, onOpen) {
  if (!btn || !panel) return () => {};
  let hoverOpened = false;        // opened by the pointer hovering: the first click keeps it open
  const set = (open) => {
    if (open) closeAllDropdowns(panel);        // one panel at a time, however it was opened
    panel.hidden = !open;
    btn.setAttribute('aria-expanded', String(open));
    if (!open) hoverOpened = false;
    return open && onOpen ? onOpen() : undefined;
  };
  dropdownClosers.push([panel, () => { if (!panel.hidden) set(false); }]);

  btn.addEventListener('click', (e) => {
    if (panel.hidden) {
      const ready = set(true);
      // Opened from the keyboard (Enter or Space report no pointer position): the
      // panel's links are not next in tab order, so move focus into it, once its
      // content exists (the timings panel loads after opening).
      if (e.detail === 0) Promise.resolve(ready).then(() => panel.querySelector('a')?.focus());
    } else if (hoverOpened && e.detail !== 0) {
      hoverOpened = false;                      // a click on a hover-opened menu pins it open
    } else {
      set(false);
    }
  });

  /* Hover behaviour, for a real mouse only (a tap on a hybrid touch laptop also
   * reports hover, and must behave like a tap). The close is delayed a beat so
   * the pointer can travel from the button into the panel, and cancelled the
   * moment it arrives. */
  let closeTimer = null;
  const cancelClose = () => { clearTimeout(closeTimer); closeTimer = null; };
  const scheduleClose = (e) => { if (e.pointerType !== 'mouse') return; cancelClose(); closeTimer = setTimeout(() => { if (hoverOpened) set(false); }, 250); };
  btn.addEventListener('pointerenter', (e) => {
    if (e.pointerType !== 'mouse') return;
    cancelClose();
    if (panel.hidden) { set(true); hoverOpened = true; }
  });
  panel.addEventListener('pointerenter', (e) => { if (e.pointerType === 'mouse') cancelClose(); });
  btn.addEventListener('pointerleave', scheduleClose);
  panel.addEventListener('pointerleave', scheduleClose);

  // Click or tap anywhere outside this dropdown closes it. (No stopPropagation
  // anywhere: every dropdown sees every click, so opening one closes the others.)
  document.addEventListener('click', (e) => {
    if (panel.hidden) return;
    if (!panel.contains(e.target) && !btn.contains(e.target)) { set(false); return; }
    // A real navigating link inside the panel must close it too, or it is left
    // floating over the page it navigated to.
    if (e.target.closest && e.target.closest('a') && panel.contains(e.target)) set(false);
  });
  // Keyboard focus leaving both the button and the panel closes it, so Tab never
  // strands an open panel behind the page.
  document.addEventListener('focusin', (e) => {
    if (panel.hidden) return;
    if (!panel.contains(e.target) && !btn.contains(e.target)) set(false);
  });
  document.addEventListener('keydown', (e) => {
    if (e.key !== 'Escape' || panel.hidden) return;
    const inside = panel.contains(document.activeElement);
    set(false);
    if (inside) btn.focus();
  });
  return set;
}

wireDropdown(megaBtn, megaPanel, () => loadTimings().then(renderMega).catch(() => {
  megaBody.innerHTML = `<div class="small faint" style="padding:16px 0">
    Timings unavailable - run <code>python3 -m pipeline.run build</code> first.</div>`;
}));

/* ------------------------------------------------------- markets dropdown
 *
 * "Brokers" in the nav is now a dropdown naming every market BrokerLens
 * plans to cover, not just the one that's live. Static content (no fetch),
 * so it needs no onOpen callback - unlike the timings panel above.
 */
/* The four task dropdowns, plus the clock button's timings panel above. */
['brokers', 'markets', 'tools', 'learn'].forEach((key) =>
  wireDropdown(document.getElementById(`${key}-toggle`), document.getElementById(`mega-${key}`)));

/* Mark where the visitor is: the direct link for the current section (IPO), or
 * else the first dropdown that links to it. Class only: a disclosure button is
 * not a page link, so it gets no aria-current. */
function markActiveGroup() {
  const seg = location.pathname.split('/')[1] || '';
  const direct = [...document.querySelectorAll('#navlinks > a:not(.nav-paper-cta)')];
  let hitDirect = false;
  direct.forEach((a) => {
    const on = !!seg && (a.getAttribute('href') || '').split('/')[1] === seg;
    a.classList.toggle('active', on);
    if (on) hitDirect = true;
  });
  let found = hitDirect;
  document.querySelectorAll('.mega-toggle').forEach((btn) => {
    const panel = document.getElementById(btn.getAttribute('aria-controls'));
    const hit = !found && !!seg && !!panel
      && [...panel.querySelectorAll('a')].some((a) => (a.getAttribute('href') || '').split('/')[1] === seg);
    if (hit) found = true;
    btn.classList.toggle('active-group', hit);
  });
}
markActiveGroup();
window.addEventListener('popstate', markActiveGroup);
window.addEventListener('bl:route', markActiveGroup);

/* Menu analytics: which item was used, through the gtag the page already
   loads (theme-init.js). Only the item's id and the page type: no personal
   data, no cookies of our own. */
document.addEventListener('click', (e) => {
  const a = e.target.closest && e.target.closest('a[data-nav]');
  if (!a || typeof window.gtag !== 'function') return;
  window.gtag('event', 'nav_click', {
    nav_item: String(a.dataset.nav).slice(0, 80),
    page_type: (location.pathname.split('/')[1] || 'home').slice(0, 40),
  });
});
