/**
 * DRAFT - NOT DEPLOYED. Do not run `wrangler deploy` from this directory without a
 * security review first (see README.md in this directory). Confirmed via
 * `wrangler deployments list --name brokerlens-edge-router` on 16 Nov 2026: this Worker
 * does not exist on the account. The live site (`wrangler.jsonc` at the repo root,
 * Worker name "brokerlens-india") is plain static-asset serving with no Worker script,
 * and is unrelated to this file.
 *
 * BrokerLens Cloudflare Edge Router & Caching Worker (design sketch)
 *
 * 1. Proxies /api/* requests directly to Cloud Run in Mumbai (asia-south1)
 * 2. Implements intelligent Edge Caching for /data/* and /assets/*
 * 3. Enforces strict security headers and eliminates Soft-404s
 *
 * Before this is ever deployed: confirm CLOUD_RUN_ORIGIN is a real, intentional backend
 * (brokerlens-web-649203501892.asia-south1.run.app has not been verified to exist or to
 * be owned by this project), and that forwarding every request header and the raw
 * cf-connecting-ip to it is what that backend expects.
 */

// Mirrors the allowlist api/ad-event.js already uses for the same reason: a bare
// "*" lets any site read the proxied response, including one that forged the request's
// Origin to look like it came from here.
const ALLOWED_ORIGINS = new Set(['https://www.brokerlens.in', 'https://brokerlens.in']);

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const cloudRunOrigin = env.CLOUD_RUN_ORIGIN || 'https://brokerlens-web-649203501892.asia-south1.run.app';

    // 1. Direct Proxy for Cloud Run APIs
    if (url.pathname.startsWith('/api/')) {
      const targetUrl = new URL(url.pathname + url.search, cloudRunOrigin);
      const modifiedRequest = new Request(targetUrl, {
        method: request.method,
        headers: request.headers,
        body: request.body,
        redirect: 'follow',
      });

      // Add edge tracing headers
      modifiedRequest.headers.set('X-Forwarded-Host', url.hostname);
      modifiedRequest.headers.set('X-Real-IP', request.headers.get('cf-connecting-ip') || '');

      const response = await fetch(modifiedRequest);
      const newHeaders = new Headers(response.headers);
      const requestOrigin = request.headers.get('Origin');
      if (requestOrigin && ALLOWED_ORIGINS.has(requestOrigin)) {
        newHeaders.set('Access-Control-Allow-Origin', requestOrigin);
        newHeaders.set('Vary', 'Origin');
      }
      newHeaders.set('X-Edge-Server', 'Cloudflare-Worker-asia');

      return new Response(response.body, {
        status: response.status,
        statusText: response.statusText,
        headers: newHeaders,
      });
    }

    // 2. Fetch Origin with Edge Caching rules
    let response = await fetch(request, {
      cf: {
        cacheTtl: url.pathname.startsWith('/assets/') ? 31536000 : (url.pathname.startsWith('/data/') ? 300 : 60),
        cacheEverything: true,
      },
    });

    // 3. Inject Performance and Security Headers
    const headers = new Headers(response.headers);
    headers.set('X-Frame-Options', 'DENY');
    headers.set('X-Content-Type-Options', 'nosniff');
    headers.set('Referrer-Policy', 'strict-origin-when-cross-origin');

    if (url.pathname.startsWith('/assets/')) {
      headers.set('Cache-Control', 'public, max-age=31536000, immutable');
    } else if (url.pathname.startsWith('/data/')) {
      headers.set('Cache-Control', 'public, max-age=60, s-maxage=300, stale-while-revalidate=86400');
    }

    return new Response(response.body, {
      status: response.status,
      statusText: response.statusText,
      headers: headers,
    });
  },
};
