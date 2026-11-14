/* 404 Recovery & Analytics Event Dispatcher.
 *
 * 1. Emits a dedicated `page_not_found` event to GA4 with the exact broken path
 *    so site administrators can track broken links, mistyped symbols, and bot probes.
 * 2. Reads the requested URL path and attempts client-side suggestion resolution
 *    to prevent user drop-off and retain high-intent search traffic.
 */
import { esc, safeUrl } from './store.js?v=b59cf0df04';

try {
  if (typeof window.gtag === 'function') {
    window.gtag('event', 'page_not_found', {
      broken_path: window.location.pathname,
      page_location: window.location.href,
      referrer: document.referrer || '(direct)'
    });
  }
} catch (e) { /* analytics never breaks page */ }

document.addEventListener('DOMContentLoaded', async () => {
  const box = document.getElementById('smart-404-suggestions');
  if (!box) return;

  const rawPath = window.location.pathname.replace(/\/+/g, '/').replace(/^\/|\/$/g, '');
  if (!rawPath) return;

  const segments = rawPath.split('/');
  const query = (segments[segments.length - 1] || '').replace(/[-_]+/g, ' ').trim().toLowerCase();

  if (query.length < 2) return;

  try {
    const res = await fetch('/data/search.json');
    if (!res.ok) return;
    const index = await res.json();
    if (!Array.isArray(index)) return;

    const matches = index.filter(row => {
      const title = (row[0] || '').toLowerCase();
      const sub = (row[3] || '').toLowerCase();
      return title.includes(query) || sub.includes(query);
    }).slice(0, 3);

    if (matches.length > 0) {
      box.innerHTML = `
        <div class="card" style="margin-bottom:24px;padding:16px 20px;text-align:left;background:var(--bg-raised);border-left:4px solid var(--accent);border-radius:var(--radius-lg)">
          <div style="font-weight:700;font-size:14px;color:var(--text);margin-bottom:8px">Were you looking for one of these?</div>
          <div style="display:flex;flex-direction:column;gap:8px">
            ${matches.map(m => `
              <a href="${safeUrl(m[1])}" class="btn btn-outline btn-sm" style="display:flex;justify-content:space-between;align-items:center;text-align:left;padding:8px 12px">
                <span><strong>${esc(m[0])}</strong> <span class="xs faint">${esc(m[3] || '')}</span></span>
                <span>&rarr;</span>
              </a>
            `).join('')}
          </div>
        </div>
      `;
      box.style.display = 'block';
    }
  } catch (err) {
    /* silent degradation on fetch failure */
  }
});
