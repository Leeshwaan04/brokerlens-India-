/**
 * BrokerLens Cloudflare Edge Router & Caching Worker
 * 
 * 1. Proxies /api/* requests directly to Cloud Run in Mumbai (asia-south1)
 * 2. Implements intelligent Edge Caching for /data/* and /assets/*
 * 3. Enforces strict security headers and eliminates Soft-404s
 */

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
      newHeaders.set('Access-Control-Allow-Origin', '*');
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
