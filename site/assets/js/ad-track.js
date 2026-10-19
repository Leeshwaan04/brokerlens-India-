/* First-party tracking for sponsored banners (the IBSL banners carry data-ad="ibsl").
 *
 * Records two anonymous events through navigator.sendBeacon to /api/ad-event:
 *   imp   the banner was at least half visible for one second (once per banner per page view)
 *   click a click on the banner link
 * Each event carries only: banner id, slot, page type, page path, referring site host and
 * phone-or-desktop. No cookie, no local storage, no IP address, no personal identifier.
 *
 * Banners have no close button; the Sponsored tag sits in their top-right corner.
 */
const ENDPOINT = '/api/ad-event';

function send(type, el) {
  const wrap = el && el.closest ? el.closest('[data-ad]') : null;
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

document.addEventListener('click', (e) => {
  const link = e.target.closest && e.target.closest('[data-ad-click]');
  if (link) send('click', link);
});

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
            timers.set(en.target, setTimeout(() => { send('imp', en.target); io.unobserve(en.target); timers.delete(en.target); }, 1000));
          }
        } else if (timers.has(en.target)) {
          clearTimeout(timers.get(en.target)); timers.delete(en.target);
        }
      });
    }, { threshold: [0, 0.5] });
  }
  io.observe(el);
}

function scan(root) { (root || document).querySelectorAll('[data-ad]').forEach(watch); }
scan();
// the home page is re-rendered client-side, so pick up banners that appear after first paint
new MutationObserver((muts) => {
  for (const m of muts) for (const n of m.addedNodes) {
    if (n.nodeType === 1) { if (n.matches && n.matches('[data-ad]')) watch(n); scan(n); }
  }
}).observe(document.documentElement, { childList: true, subtree: true });
