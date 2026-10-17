'use strict';
/* IPO event-alert signup endpoint (Vercel Node function).
 *
 *   GET  /api/subscribe  -> { enabled: boolean }   (the page only shows the form when true)
 *   POST /api/subscribe  -> JSON { email, consent: true, source, website }
 *
 * Collects an email address and nothing else (plus the page it was given on and the
 * consent time) and hands it to the email service provider configured by the
 * ALERTS_API_KEY environment variable. With no key set the endpoint reports
 * enabled:false and the site shows no form at all, so nothing is ever collected
 * without somewhere to send the confirmation from. The provider sends the
 * double-opt-in confirmation, so no email is sent to anyone who did not confirm.
 *
 * Abuse controls: same-site Origin required, honeypot field, small body cap,
 * per-IP rate limit (best effort, per warm instance), strict email shape.
 */

const ALLOWED_HOSTS = new Set(['www.brokerlens.in', 'brokerlens.in']);
const CONSENT_VERSION = '2026-10-17';
const WINDOW_MS = 10 * 60 * 1000;
const MAX_PER_WINDOW = 5;
const hits = new Map();

function send(res, status, body) {
  res.setHeader('Cache-Control', 'no-store');
  res.setHeader('X-Content-Type-Options', 'nosniff');
  res.status(status).json(body);
}

function rateLimited(ip) {
  const now = Date.now();
  const list = (hits.get(ip) || []).filter((t) => now - t < WINDOW_MS);
  list.push(now);
  hits.set(ip, list);
  if (hits.size > 5000) { for (const [k, v] of hits) { if (!v.some((t) => now - t < WINDOW_MS)) hits.delete(k); } }
  return list.length > MAX_PER_WINDOW;
}

function originAllowed(req) {
  const origin = req.headers.origin;
  if (!origin) return false;
  try {
    const host = new URL(origin).host;
    return ALLOWED_HOSTS.has(host) || host.endsWith('.vercel.app');
  } catch (e) {
    return false;
  }
}

module.exports = async function handler(req, res) {
  const key = process.env.ALERTS_API_KEY;

  if (req.method === 'GET') return send(res, 200, { enabled: Boolean(key) });
  if (req.method !== 'POST') { res.setHeader('Allow', 'GET, POST'); return send(res, 405, { error: 'method_not_allowed' }); }
  if (!key) return send(res, 503, { error: 'not_enabled' });
  if (!originAllowed(req)) return send(res, 403, { error: 'forbidden' });

  const ip = String(req.headers['x-forwarded-for'] || '').split(',')[0].trim() || 'unknown';
  if (rateLimited(ip)) return send(res, 429, { error: 'too_many_requests' });

  const body = req.body && typeof req.body === 'object' ? req.body : {};
  if (JSON.stringify(body).length > 2048) return send(res, 413, { error: 'too_large' });

  // Honeypot: bots fill every field. Pretend success, store nothing.
  if (typeof body.website === 'string' && body.website.trim() !== '') return send(res, 200, { ok: true });

  const email = typeof body.email === 'string' ? body.email.trim().toLowerCase() : '';
  if (email.length < 6 || email.length > 254 || !/^[^\s@<>()[\]\\,;:"]+@[^\s@<>()[\]\\,;:"]+\.[a-z]{2,}$/.test(email)) {
    return send(res, 400, { error: 'invalid_email' });
  }
  if (body.consent !== true) return send(res, 400, { error: 'consent_required' });
  const source = typeof body.source === 'string' && /^[a-z0-9/_-]{1,80}$/i.test(body.source) ? body.source : 'unknown';

  const ctl = new AbortController();
  const timer = setTimeout(() => ctl.abort(), 8000);
  try {
    const r = await fetch('https://api.buttondown.com/v1/subscribers', {
      method: 'POST',
      headers: { Authorization: 'Token ' + key, 'Content-Type': 'application/json' },
      body: JSON.stringify({
        email_address: email,
        tags: ['ipo-alerts'],
        metadata: { source, consent_at: new Date().toISOString(), consent_version: CONSENT_VERSION },
      }),
      signal: ctl.signal,
    });
    if (r.status === 200 || r.status === 201) return send(res, 200, { ok: true });
    // Already subscribed or pending confirmation: say the same thing, reveal nothing.
    if (r.status === 400 || r.status === 409) {
      const text = (await r.text()).toLowerCase();
      if (text.includes('already') || text.includes('exist') || text.includes('subscribed')) return send(res, 200, { ok: true });
      return send(res, 400, { error: 'invalid_email' });
    }
    return send(res, 502, { error: 'upstream' });
  } catch (e) {
    return send(res, 502, { error: 'upstream' });
  } finally {
    clearTimeout(timer);
  }
};
