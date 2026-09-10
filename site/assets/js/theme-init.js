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
