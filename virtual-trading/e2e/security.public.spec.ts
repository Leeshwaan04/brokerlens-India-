import { expect, test } from "@playwright/test";

// VAPT, signed out. Everything here is something an attacker or a scanner
// would try; the app must refuse it cleanly (4xx, never 5xx) without leaking
// code, paths, secrets or stack traces. Local server only.

const PAYLOADS = ["<script>alert(1)</script>", "'\"><img src=x onerror=alert(1)>", "../../../../etc/passwd", "%00", "${7*7}", "{{7*7}}", "a".repeat(2000)];
// (No "node_modules" pattern: the dev server's chunk names contain it; production pages do not, and the
// production bundle is scanned for leaks at deploy time.)
const LEAKS = [/\bat [A-Za-z_.]+ \(/, /DATABASE_URL/, /sk_(live|test)_/, /postgres(ql)?:\/\//, /CRON_SECRET/, /\.ts:\d+/];

function expectNoLeak(raw: string, where: string) {
  // The dev server's own script URLs (/_next/...) contain "node_modules"; only the page's content matters.
  const text = raw.replace(/\/_next\/[^"'\s)]*/g, "");
  for (const re of LEAKS) expect(text, `${where} leaked ${re}`).not.toMatch(re);
}

test("price history is for signed-in users only, and bad symbols are refused", async ({ request }) => {
  for (const p of ["/api/history/RELIANCE", "/api/history/NOPE", "/api/history/..%2F..%2Fetc", "/api/history/%00", "/api/history/" + "A".repeat(40)]) {
    const res = await request.get(p, { maxRedirects: 0 });
    expect([301, 302, 307, 308, 400, 401, 403, 404], `${p} -> ${res.status()}`).toContain(res.status());
    expectNoLeak(await res.text(), p);
  }
  // Static chart files are public (they hold code, no data), and carry no secrets.
  for (const p of ["/charting/engine.js", "/charting/lightweight-charts.js"]) {
    const res = await request.get(p);
    expect(res.status(), p).toBe(200);
    expectNoLeak(await res.text(), p);
  }
});

test("sensitive paths are not served", async ({ request }) => {
  for (const p of ["/.env", "/.env.local", "/.git/config", "/package.json", "/drizzle/0000_init.sql", "/lib/schema.ts", "/.next/server/app/page.js", "/wrangler.jsonc", "/%2e%2e/%2e%2e/etc/passwd", "/_next/../.env", "/..%2f..%2f.env"]) {
    const res = await request.get(p, { maxRedirects: 0 });
    expect([301, 302, 307, 308, 400, 401, 403, 404], `${p} -> ${res.status()}`).toContain(res.status());
    const body = await res.text();
    expectNoLeak(body, p);
    expect(body).not.toMatch(/root:.*:0:0/);
  }
});

test("hostile input in paths, queries and params never reaches a 5xx or reflects as markup", async ({ request }) => {
  const targets = (v: string) => [
    `/api/stocks/search?q=${encodeURIComponent(v)}`,
    `/api/stocks/${encodeURIComponent(v)}/price`,
    `/go/${encodeURIComponent(v)}`,
    `/?amount=${encodeURIComponent(v)}`,
    `/sign-in?redirect_url=${encodeURIComponent(v)}`,
  ];
  for (const v of PAYLOADS) {
    for (const t of targets(v)) {
      const res = await request.get(t, { maxRedirects: 0 });
      expect(res.status(), `${t.slice(0, 80)} -> ${res.status()}`).toBeLessThan(500);
      const body = await res.text();
      expect(body, `${t.slice(0, 60)} reflected raw markup`).not.toContain("<script>alert(1)</script>");
      expect(body).not.toContain("<img src=x onerror=alert(1)>");
      expectNoLeak(body, t.slice(0, 60));
    }
  }
});

test("a sign-in redirect_url pointing off-site does not turn this app into an open redirect", async ({ request }) => {
  for (const evil of ["https://evil.example/", "//evil.example", "javascript:alert(1)"]) {
    const res = await request.get(`/sign-in?redirect_url=${encodeURIComponent(evil)}`, { maxRedirects: 0 });
    const loc = res.headers()["location"] ?? "";
    expect(loc, `redirected to ${loc}`).not.toMatch(/evil\.example/);
  }
});

test("only the methods each route needs are accepted", async ({ request }) => {
  for (const [method, path] of [["PUT", "/"], ["DELETE", "/privacy"], ["PATCH", "/api/health"], ["POST", "/api/health"], ["DELETE", "/api/orders"], ["PUT", "/api/orders"]] as const) {
    const res = await request.fetch(path, { method, maxRedirects: 0, data: "{}", headers: { "content-type": "application/json" } });
    expect([401, 403, 404, 405, 415], `${method} ${path} -> ${res.status()}`).toContain(res.status());
  }
});

test("malformed, oversized and typed-wrong bodies are refused without a server error", async ({ request }) => {
  const json = { "content-type": "application/json" };
  const cases: [string, string | Buffer][] = [
    ["not json", "{not json"],
    ["empty", ""],
    ["array", "[]"],
    ["null", "null"],
    ["proto pollution", '{"__proto__":{"admin":true},"symbol":"RELIANCE","side":"BUY","qty":1}'],
    ["deep nesting", "[".repeat(5000) + "]".repeat(5000)],
    ["2 MB body", JSON.stringify({ symbol: "A".repeat(2_000_000), side: "BUY", qty: 1 })],
  ];
  for (const [name, body] of cases) {
    for (const path of ["/api/orders", "/api/billing/order", "/api/billing/verify"]) {
      const res = await request.post(path, { headers: json, data: body });
      expect(res.status(), `${name} ${path} -> ${res.status()}`).toBeLessThan(500);
      expectNoLeak(await res.text(), `${name} ${path}`);
    }
  }
});

test("cross-origin requests get no CORS grant", async ({ request }) => {
  for (const path of ["/api/health", "/api/stocks/search?q=rel", "/api/orders"]) {
    const res = await request.fetch(path, { method: "OPTIONS", headers: { origin: "https://evil.example", "access-control-request-method": "POST" }, maxRedirects: 0 });
    const allow = res.headers()["access-control-allow-origin"] ?? "";
    expect(allow, `${path} allowed ${allow}`).not.toMatch(/evil\.example|^\*$/);
  }
});

test("webhooks and the cron route reject forged callers", async ({ request }) => {
  const forged = [
    ["/api/webhooks/razorpay", { "x-razorpay-signature": "0".repeat(64) }],
    ["/api/webhooks/razorpay", {}],
    ["/api/webhooks/clerk", { "svix-id": "msg_1", "svix-timestamp": String(Math.floor(Date.now() / 1000)), "svix-signature": "v1,AAAA" }],
    ["/api/webhooks/clerk", {}],
  ] as const;
  for (const [path, headers] of forged) {
    const res = await request.post(path, { headers: { ...headers }, data: '{"event":"payment.captured","payload":{}}' });
    expect([400, 401, 403, 503], `${path} -> ${res.status()}`).toContain(res.status());
  }
  for (const auth of ["", "Bearer ", "Bearer x", "bearer " + "a".repeat(5000), "Basic YTpi"]) {
    const res = await request.get("/api/cron/sync-eod-prices?date=2026-01-01&history=999", { headers: auth ? { authorization: auth } : {} });
    expect(res.status(), `cron with "${auth.slice(0, 12)}"`).toBe(401);
  }
});

test("the account-opening redirect is an allow-list, not a pass-through", async ({ request }) => {
  const ok = await request.get("/go/zerodha", { maxRedirects: 0 });
  expect([302, 307]).toContain(ok.status());
  const to = ok.headers()["location"] ?? "";
  expect(to).toMatch(/^https:\/\//);
  // Anything that is not a known broker id goes to this app's own home page:
  // never to a request-supplied address, and no injected header or cookie.
  for (const bad of ["..%2fx", "zerodha%0d%0aSet-Cookie:x=1", "http%3A%2F%2Fevil.example", "ZERODHA", "zerodha%2f..%2f..%2fx"]) {
    const res = await request.get(`/go/${bad}`, { maxRedirects: 0 });
    expect([302, 307, 308, 404], `/go/${bad} -> ${res.status()}`).toContain(res.status());
    const loc = res.headers()["location"] ?? "";
    if (loc) expect(new URL(loc, "http://localhost:3200").origin, `/go/${bad} -> ${loc}`).toBe("http://localhost:3200");
    expect(JSON.stringify(res.headersArray())).not.toMatch(/x=1|evil\.example/);
  }
  expect(ok.headers()["location"]).not.toMatch(/evil\.example/);
});

test("error pages and headers disclose nothing", async ({ request }) => {
  for (const p of ["/definitely-not-a-page", "/api/nope", "/api/orders/not-a-uuid"]) {
    const res = await request.get(p, { maxRedirects: 0 });
    expect(res.status()).toBeLessThan(500);
    expectNoLeak(await res.text(), p);
    expect(res.headers()["x-powered-by"], `x-powered-by on ${p}`).toBeUndefined();
    expect(res.headers()["server"] ?? "", `server header on ${p}`).not.toMatch(/\d+\.\d+/);
  }
});

test("the page security policy blocks framing, plugins and mixed content", async ({ request }) => {
  const res = await request.get("/");
  const csp = res.headers()["content-security-policy"] ?? "";
  for (const d of ["frame-ancestors 'none'", "object-src 'none'", "base-uri 'self'", "form-action 'self'"]) expect(csp, d).toContain(d);
  expect(csp).not.toContain("'unsafe-eval'");
  expect(res.headers()["x-frame-options"]).toBe("DENY");
  expect(res.headers()["x-content-type-options"]).toBe("nosniff");
  expect(res.headers()["strict-transport-security"]).toMatch(/max-age=\d{7,}/);
});
