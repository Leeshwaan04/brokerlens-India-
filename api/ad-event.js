'use strict';
/* Anonymous banner-event endpoint (Vercel Node function): POST /api/ad-event
 *
 * Receives the beacon from ad-track.js (impression or click of a sponsored banner), checks
 * it strictly, and writes one structured line to the function's runtime logs. It stores nothing
 * else and never records the caller: no IP address, no user agent, no headers, no cookies.
 *
 * Strictness: same-site Origin only, JSON body under 600 bytes, every field must match a fixed
 * whitelist or pattern, per-address rate limit kept in memory (the address itself is never logged).
 * Responds 204 with no body. No CORS headers are ever sent.
 *
 * Durable counting: logs are short-lived. When a durable store is enabled for the project this
 * is the single place to add the write (see docs/GROWTH_PLAN_2026-10.md).
 */

const ALLOWED_HOSTS = new Set(['www.brokerlens.in', 'brokerlens.in']);
const TYPES = new Set(['imp', 'click']);
const ADS = new Set(['ibsl']);
const SLOTS = new Set(['strip', 'wide', 'card']);
const PAGE_TYPES = new Set(['home', 'ipo', 'broker', 'stock', 'news', 'calculator']);
const DEVICES = new Set(['m', 'd']);
const PATH_RE = /^\/[A-Za-z0-9/_.\-&%]{0,199}$/;
const HOST_RE = /^[a-z0-9.-]{0,100}$/;
const WINDOW_MS = 10 * 60 * 1000;
const MAX_PER_WINDOW = 120;
const hits = new Map();

function done(res, status) {
  res.setHeader('Cache-Control', 'no-store');
  res.setHeader('X-Content-Type-Options', 'nosniff');
  res.status(status).end();
}

// Only this project's own preview deployments (brokerlens-india-<hash-or-branch>.vercel.app),
// never an arbitrary *.vercel.app host: any attacker can get a free vercel.app subdomain, and
// a bare ".vercel.app" suffix check let any of them pass as an "allowed" origin and forge events.
const PREVIEW_HOST_RE = /^brokerlens-india(-[a-z0-9-]+)?\.vercel\.app$/i;

function originAllowed(req) {
  const origin = req.headers.origin;
  if (!origin) return false;
  try {
    const host = new URL(origin).host;
    return ALLOWED_HOSTS.has(host) || PREVIEW_HOST_RE.test(host);
  } catch (e) {
    return false;
  }
}

function rateLimited(key) {
  const now = Date.now();
  const list = (hits.get(key) || []).filter((t) => now - t < WINDOW_MS);
  list.push(now);
  hits.set(key, list);
  if (hits.size > 5000) { for (const [k, v] of hits) { if (!v.some((t) => now - t < WINDOW_MS)) hits.delete(k); } }
  return list.length > MAX_PER_WINDOW;
}

function clean(body) {
  if (!body || typeof body !== 'object' || Array.isArray(body)) return null;
  if (body.v !== 1) return null;
  if (!TYPES.has(body.t) || !ADS.has(body.ad) || !SLOTS.has(body.slot) || !PAGE_TYPES.has(body.pt) || !DEVICES.has(body.dev)) return null;
  if (typeof body.path !== 'string' || !PATH_RE.test(body.path)) return null;
  const ref = typeof body.ref === 'string' ? body.ref : '';
  if (!HOST_RE.test(ref)) return null;
  return { t: body.t, ad: body.ad, slot: body.slot, pt: body.pt, path: body.path, ref, dev: body.dev };
}

module.exports = async function handler(req, res) {
  if (req.method !== 'POST') { res.setHeader('Allow', 'POST'); return done(res, 405); }
  if (!originAllowed(req)) return done(res, 403);

  let body = req.body;
  if (typeof body === 'string') {
    if (body.length > 600) return done(res, 413);
    try { body = JSON.parse(body); } catch (e) { return done(res, 400); }
  }
  if (JSON.stringify(body || {}).length > 600) return done(res, 413);

  const limiterKey = String(req.headers['x-forwarded-for'] || '').split(',')[0].trim() || 'unknown';
  if (rateLimited(limiterKey)) return done(res, 429);

  const evt = clean(body);
  if (!evt) return done(res, 400);

  console.log(JSON.stringify({ evt: 'ad', ts: new Date().toISOString(), ...evt }));
  return done(res, 204);
};
