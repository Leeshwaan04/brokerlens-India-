/* Tracking for every sponsored placement on the site.
 *
 * Google Analytics 4 (all partners): two events, sent through the gtag that theme-init.js loads.
 *   ad_impression  a partner banner was at least half visible for one second (once per banner
 *                  per page view). Banners are the IBSL ads (data-ad), the partner cards
 *                  (.aff-banner: Zerodha, 5paisa, Jiraaf, Binance, Delta) and the IBSL article card.
 *   ad_click       a click on any sponsored link (rel="sponsored"), inside a banner or not.
 * Parameters:
 *   ad_id        partner: ibsl, zerodha, 5paisa, jiraaf, ... (data-ad, else the link's host)
 *   ad_slot      strip / wide / card for IBSL ads, card for partner cards, article_card,
 *                sticky (mobile bar) or inline (a text link)
 *   ad_format    banner or link
 *   page_type    data-page-type when the banner has one, else the first path segment (home for /)
 *   link_domain, link_url   where the click went (GA4's built-in outbound-link dimensions)
 *
 * First-party (IBSL banners only, data-ad="ibsl"): the same impression and click also go
 * through navigator.sendBeacon to /api/ad-event as 'imp' / 'click', carrying only banner id,
 * slot, page type, page path, referring site host and phone-or-desktop.
 *
 * No cookie, no local storage, no IP address, no personal identifier is read or written here.
 * Banners have no close button; the Sponsored tag sits in their top-right corner.
 */
const ENDPOINT = '/api/ad-event';

// Link host -> partner id. Any other sponsored host is reported by its own host name.
const PARTNERS = [
  [/(^|\.)indiabullssecurities\.(com|onelink\.me)$/, 'ibsl'],
  [/(^|\.)zerodha\.com$/, 'zerodha'],
  [/(^|\.)5paisa\.com$/, '5paisa'],
  [/(^|\.)jiraaf\.com$/, 'jiraaf'],
  [/(^|\.)angelone\.in$/, 'angelone'],
  [/(^|\.)upstox\.com$/, 'upstox'],
  [/(^|\.)dhan\.co$/, 'dhan'],
  [/(^|\.)binance\.com$/, 'binance'],
  [/(^|\.)delta\.exchange$/, 'delta'],
];
const SPONSORED = 'a[rel~="sponsored"], a[data-ad-click]';
const BANNERS = '[data-ad], .aff-banner, .aff-article-card';

function hostOf(link) {
  try { return new URL(link.href, location.href).hostname.toLowerCase(); } catch (e) { return ''; }
}

function partnerOf(host) {
  for (const [re, id] of PARTNERS) if (re.test(host)) return id;
  return host.replace(/^www\./, '').slice(0, 40) || 'unknown';
}

function pageType(el) {
  const tagged = el.closest('[data-page-type]');
  if (tagged && tagged.dataset.pageType) return tagged.dataset.pageType;
  const seg = location.pathname.split('/')[1] || '';
  return seg ? seg.slice(0, 40) : 'home';
}

// GA4 parameters for a banner (impression) or a sponsored link (click).
function describe(el) {
  const wrap = el.closest(BANNERS);
  const link = el.matches(SPONSORED) ? el : (wrap && wrap.querySelector(SPONSORED));
  const host = link ? hostOf(link) : '';
  let slot = 'inline';
  if (wrap) slot = wrap.dataset.slot || (wrap.classList.contains('aff-article-card') ? 'article_card' : 'card');
  else if (el.closest('.mobile-sticky-lead')) slot = 'sticky';
  const params = {
    ad_id: (wrap && wrap.dataset.ad) || partnerOf(host),
    ad_slot: slot,
    ad_format: wrap ? 'banner' : 'link',
    page_type: pageType(el),
  };
  if (host) { params.link_domain = host; params.link_url = link.href.slice(0, 300); }
  return params;
}

function ga(name, el) {
  try {
    if (typeof window.gtag === 'function') window.gtag('event', name, describe(el));
  } catch (e) { /* tracking never breaks the page */ }
}

// First-party beacon, IBSL banners only (api/ad-event.js accepts nothing else).
function beacon(type, el) {
  const wrap = el.closest('[data-ad]');
  if (!wrap) return;
  let ref = '';
  try { ref = document.referrer ? new URL(document.referrer).host : ''; } catch (e) { ref = ''; }
  const payload = JSON.stringify({
    v: 1, t: type, ad: wrap.dataset.ad, slot: wrap.dataset.slot, pt: wrap.dataset.pageType,
    path: location.pathname.slice(0, 200), ref: ref.slice(0, 100), dev: window.innerWidth < 900 ? 'm' : 'd',
  });
  try {
    if (navigator.sendBeacon && navigator.sendBeacon(ENDPOINT, new Blob([payload], { type: 'application/json' }))) return;
  } catch (e) { /* fall through */ }
  try { fetch(ENDPOINT, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: payload, keepalive: true }); } catch (e) { /* tracking never breaks the page */ }
}

function onClick(e) {
  if (e.type === 'auxclick' && e.button !== 1) return; // middle-click opens the link too; right-click does not
  const link = e.target && e.target.closest ? e.target.closest(SPONSORED) : null;
  if (!link) return;
  beacon('click', link);
  ga('ad_click', link);
}
// capture phase, so a handler that stops propagation further down cannot hide a click
document.addEventListener('click', onClick, true);
document.addEventListener('auxclick', onClick, true);

const seen = new WeakSet();
let io = null;
function watch(el) {
  if (seen.has(el) || !('IntersectionObserver' in window)) return;
  seen.add(el);
  if (!io) {
    const timers = new WeakMap();
    io = new IntersectionObserver((entries) => {
      entries.forEach((en) => {
        if (en.isIntersecting && en.intersectionRatio >= 0.5) {
          if (!timers.has(en.target)) {
            timers.set(en.target, setTimeout(() => {
              beacon('imp', en.target); ga('ad_impression', en.target);
              io.unobserve(en.target); timers.delete(en.target);
            }, 1000));
          }
        } else if (timers.has(en.target)) {
          clearTimeout(timers.get(en.target)); timers.delete(en.target);
        }
      });
    }, { threshold: [0, 0.5] });
  }
  io.observe(el);
}

function scan(root) { (root || document).querySelectorAll(BANNERS).forEach(watch); }
scan();
// the home page is re-rendered client-side, so pick up banners that appear after first paint
new MutationObserver((muts) => {
  for (const m of muts) for (const n of m.addedNodes) {
    if (n.nodeType === 1) { if (n.matches && n.matches(BANNERS)) watch(n); scan(n); }
  }
}).observe(document.documentElement, { childList: true, subtree: true });
