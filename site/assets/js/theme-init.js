/* Loaded early, blocking, in <head> on every static page (registry, stock,
 * index, etf, fund, report, calculator) - none of them load app.js, so
 * without this a user who picked dark mode on the homepage saw it silently
 * revert to light on every one of those ~8,000 pages. Must be a separate
 * file (CSP here is script-src 'self' with no unsafe-inline, so an inline
 * <script> would be blocked outright) and must run before first paint
 * (no defer/async) or the page flashes light before switching to dark. */
try {
  var t = localStorage.getItem('bl-theme');
  if (t === 'dark' || t === 'light') document.documentElement.dataset.theme = t;
} catch (e) { /* localStorage blocked (private mode, etc.) - fall back to prefers-color-scheme */ }

/* Button wiring waits for the DOM (the button doesn't exist yet when the
 * block above runs), but the FOUC-preventing read above must stay
 * synchronous and unconditional - only the click handler is deferred. */
document.addEventListener('DOMContentLoaded', function () {
  var btn = document.getElementById('theme-toggle');
  if (!btn) return;
  btn.addEventListener('click', function () {
    var cur = document.documentElement.dataset.theme
      || (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
    var next = cur === 'dark' ? 'light' : 'dark';
    document.documentElement.dataset.theme = next;
    try { localStorage.setItem('bl-theme', next); } catch (e) { /* private mode, etc. */ }
    window.dispatchEvent(new Event('resize')); // canvases (broker pages) must re-render for new tokens
  });
});

/* Google Analytics GA4 (Measurement ID: G-XJK97Q2CD7) */
try {
  window.dataLayer = window.dataLayer || [];
  function gtag(){window.dataLayer.push(arguments);}
  window.gtag = window.gtag || gtag;
  if (!window._ga_loaded) {
    window._ga_loaded = true;
    gtag('js', new Date());
    gtag('config', 'G-XJK97Q2CD7');
    if (!document.querySelector('script[src*="googletagmanager.com/gtag/js"]')) {
      var gas = document.createElement('script');
      gas.async = true;
      gas.src = 'https://www.googletagmanager.com/gtag/js?id=G-XJK97Q2CD7';
      document.head.appendChild(gas);
    }
  }
} catch (e) { /* analytics never breaks page rendering */ }

/* Google AdSense (ca-pub-8447377943455646) */
try {
  if (!document.querySelector('script[src*="pagead2.googlesyndication.com"]')) {
    var ads = document.createElement('script');
    ads.async = true;
    ads.src = 'https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-pub-8447377943455646';
    ads.crossOrigin = 'anonymous';
    document.head.appendChild(ads);
  }
} catch (e) { /* ads never break page rendering */ }

/* Auto ads: let Google place and size ad units itself instead of relying on
 * hand-coded <ins class="adsbygoogle"> slots. The one manual slot this site
 * carried (in-article, on news pages) had data-ad-slot="brokerlens-in-article"
 * - a placeholder string, never a real numeric id issued by the AdSense
 * dashboard - so it could never have served an ad regardless of account
 * approval status. Removed in favour of this, which needs no per-unit id. */
try {
  (window.adsbygoogle = window.adsbygoogle || []).push({
    google_ad_client: 'ca-pub-8447377943455646',
    enable_page_level_ads: true
  });
} catch (e) { /* ads never break page rendering */ }
