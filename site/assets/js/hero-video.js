/* Home-hero background video (Golden bull vs black bear).
 *
 * Decorative only: it is aria-hidden, muted and looping, and the page reads
 * the same without it. To keep it from costing anything it doesn't earn:
 *  - the markup ships with a poster image and preload="none", so no video
 *    bytes load until the hero is actually on screen;
 *  - people who ask for reduced motion, enable Data Saver or sit on a 2G link
 *    just keep the poster frame;
 *  - playback pauses when the hero scrolls out of view or the tab is hidden.
 * The home page is re-rendered client-side, so a MutationObserver sets up any
 * hero video that appears after first paint.
 */
const reduced = window.matchMedia('(prefers-reduced-motion: reduce)');

function posterOnly() {
  const c = navigator.connection;
  return reduced.matches || !!(c && (c.saveData || /(^|-)2g$/.test(c.effectiveType || '')));
}

function setup(v) {
  if (v.dataset.ready) return;
  v.dataset.ready = '1';
  if (posterOnly() || !('IntersectionObserver' in window)) return;

  let inView = false;
  const sync = () => {
    if (inView && !document.hidden) {
      if (!v.getAttribute('src')) v.src = v.dataset.src;
      const p = v.play();
      if (p && p.then) p.then(() => v.classList.add('is-playing')).catch(() => { /* blocked: poster stays */ });
    } else {
      v.pause();
    }
  };
  new IntersectionObserver((entries) => {
    inView = entries.some((e) => e.isIntersecting);
    sync();
  }, { threshold: 0.15 }).observe(v);
  document.addEventListener('visibilitychange', sync);
  reduced.addEventListener('change', () => { if (reduced.matches) { v.pause(); v.classList.remove('is-playing'); } else sync(); });
}

function scan(root) {
  (root || document).querySelectorAll('.pitch-video').forEach(setup);
}

scan();
new MutationObserver((muts) => {
  for (const m of muts) {
    for (const n of m.addedNodes) {
      if (n.nodeType === 1 && (n.matches('.pitch-video') || n.querySelector('.pitch-video'))) { scan(n.parentNode || document); return; }
    }
  }
}).observe(document.documentElement, { childList: true, subtree: true });
