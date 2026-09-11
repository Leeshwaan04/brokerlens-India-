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
import { esc, loadTimings, safeUrl } from './store.js';

/* ------------------------------------------------------------- mobile nav */

const navToggle = document.getElementById('nav-toggle');
const navLinks = document.getElementById('navlinks');

function setNav(open) {
  if (!navLinks || !navToggle) return;
  navLinks.classList.toggle('open', open);
  navToggle.setAttribute('aria-expanded', String(open));
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
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') setNav(false);
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
      Sessions run Mon to Fri except exchange holidays: ${holidays}.
      * hover for detail. Curated from exchange material, last reviewed ${esc((t.last_reviewed || '').slice(0, 10))}.
      Verify with the exchange before relying on an edge case.
    </div>`;
}

/* Generic open/close/hover/escape/outside-click wiring, shared by every
 * button+panel dropdown in the nav (market timings, markets). Extracted
 * after a second dropdown (markets) needed the exact same behaviour - one
 * copy is a pattern, two hand-written copies are a maintenance bug waiting
 * to happen when only one gets a future fix. */
const HOVER_CAPABLE = window.matchMedia('(hover: hover)').matches;

function wireDropdown(btn, panel, onOpen) {
  if (!btn || !panel) return () => {};
  const set = (open) => {
    panel.hidden = !open;
    btn.setAttribute('aria-expanded', String(open));
    if (open && onOpen) onOpen();
  };

  btn.addEventListener('click', (e) => {
    e.stopPropagation();
    if (panel.hidden) set(true);
    else if (!HOVER_CAPABLE) set(false);
  });

  /* Hover behaviour, only on devices that actually hover (desktop). The close
   * is delayed a beat so the pointer can travel from the button into the
   * panel, and cancelled the moment it arrives. Hovering a sibling nav link
   * dismisses. */
  if (HOVER_CAPABLE) {
    let closeTimer = null;
    const cancelClose = () => { clearTimeout(closeTimer); closeTimer = null; };
    const scheduleClose = () => { cancelClose(); closeTimer = setTimeout(() => set(false), 250); };

    btn.addEventListener('mouseenter', () => { cancelClose(); if (panel.hidden) set(true); });
    panel.addEventListener('mouseenter', cancelClose);
    btn.addEventListener('mouseleave', scheduleClose);
    panel.addEventListener('mouseleave', scheduleClose);
    document.querySelectorAll('#navlinks a, #navlinks button').forEach((a) => {
      if (a !== btn) a.addEventListener('mouseenter', () => { if (!panel.hidden) set(false); });
    });
  }
  document.addEventListener('click', (e) => {
    if (panel.hidden) return;
    if (!panel.contains(e.target) && e.target !== btn) { set(false); return; }
    // A real navigating link inside the panel (e.g. the markets dropdown)
    // must close it too, or it's left floating over the page it navigated
    // to - found live via screenshot, not from the DOM state alone.
    if (e.target.closest('a')) set(false);
  });
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && !panel.hidden) set(false);
  });
  return set;
}

wireDropdown(megaBtn, megaPanel, () => {
  loadTimings().then(renderMega).catch(() => {
    megaBody.innerHTML = `<div class="small faint" style="padding:16px 0">
      Timings unavailable - run <code>python3 -m pipeline.run build</code> first.</div>`;
  });
});

/* ------------------------------------------------------- markets dropdown
 *
 * "Brokers" in the nav is now a dropdown naming every market BrokerLens
 * plans to cover, not just the one that's live. Static content (no fetch),
 * so it needs no onOpen callback - unlike the timings panel above.
 */
wireDropdown(document.getElementById('markets-toggle'), document.getElementById('mega-markets'));
