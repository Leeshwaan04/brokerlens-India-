import { expect, test } from "@playwright/test";

// Signed out: the public pages work and say what search engines need, and
// everything private refuses.

const SECURITY_HEADERS = [
  "content-security-policy",
  "x-frame-options",
  "x-content-type-options",
  "referrer-policy",
  "permissions-policy",
  "strict-transport-security",
];

test("the landing page renders with its FAQ, structured data and canonical", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  const res = await page.goto("/");
  expect(res?.status()).toBe(200);
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Questions" })).toBeVisible();
  const ld = await page.locator('script[type="application/ld+json"]').first().textContent();
  const data = JSON.parse(ld ?? "{}");
  const types = (data["@graph"] ?? []).map((n: { "@type": string }) => n["@type"]);
  expect(types).toEqual(expect.arrayContaining(["WebApplication", "FAQPage"]));
  // Every FAQ answer in the structured data is visible on the page.
  const faq = data["@graph"].find((n: { "@type": string }) => n["@type"] === "FAQPage");
  for (const q of faq.mainEntity) await expect(page.getByText(q.name)).toBeVisible();
  expect(await page.locator('link[rel="canonical"]').getAttribute("href")).toMatch(/^https:\/\/paper\.brokerlens\.in\/?$/);
  expect(await page.locator('meta[property="og:image"]').getAttribute("content")).toContain("/og.png");
  expect(errors).toEqual([]);
});

test("How it works is public and canonical", async ({ page }) => {
  const res = await page.goto("/how-it-works");
  expect(res?.status()).toBe(200);
  await expect(page.getByRole("heading", { name: "How paper trading works here" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "How orders fill" })).toBeVisible();
  expect(await page.locator('link[rel="canonical"]').getAttribute("href")).toBe("https://paper.brokerlens.in/how-it-works");
});

test("robots.txt, the sitemap and the share image are served", async ({ request }) => {
  const robots = await (await request.get("/robots.txt")).text();
  expect(robots).toContain("Sitemap: https://paper.brokerlens.in/sitemap.xml");
  expect(robots).toMatch(/Disallow: \/api\//);
  expect(robots).toMatch(/Disallow: \/dashboard/);
  const sitemap = await (await request.get("/sitemap.xml")).text();
  for (const p of ["/", "/how-it-works", "/privacy"]) expect(sitemap).toContain(`<loc>https://paper.brokerlens.in${p === "/" ? "/" : p}</loc>`);
  const og = await request.get("/og.png");
  expect(og.status()).toBe(200);
  expect(og.headers()["content-type"]).toBe("image/png");
});

test("sign-in and sign-up are kept out of search results", async ({ page }) => {
  for (const path of ["/sign-in", "/sign-up"]) {
    await page.goto(path);
    expect(await page.locator('meta[name="robots"]').getAttribute("content")).toContain("noindex");
  }
});

test("every page carries the security headers", async ({ request }) => {
  for (const path of ["/", "/how-it-works", "/privacy", "/api/stocks/search?q=rel"]) {
    const res = await request.get(path, { maxRedirects: 0 });
    for (const h of SECURITY_HEADERS) expect(res.headers()[h], `${h} on ${path}`).toBeTruthy();
  }
});

test("private pages send signed-out visitors to sign in", async ({ page }) => {
  for (const path of ["/dashboard", "/trade", "/orders", "/portfolio", "/performance", "/costs", "/account", "/plus"]) {
    await page.goto(path);
    await expect(page, path).toHaveURL(/\/sign-in/);
  }
});

test("private APIs refuse signed-out callers", async ({ request }) => {
  const json = { headers: { "content-type": "application/json" } };
  expect((await request.post("/api/orders", { ...json, data: { symbol: "RELIANCE", side: "BUY", qty: 1 } })).status()).toBe(401);
  expect((await request.post("/api/billing/order", { ...json, data: { plan: "plus_month" } })).status()).toBe(401);
  expect((await request.post("/api/billing/verify", { ...json, data: {} })).status()).toBe(401);
  expect((await request.get("/api/reports/statement", { maxRedirects: 0 })).status()).toBe(401);
  expect((await request.get("/admin")).status()).toBe(404);
});

test("cross-site style requests to JSON endpoints are refused", async ({ request }) => {
  // A plain form or text/plain body is what a hostile page could send with cookies.
  const asText = await request.post("/api/orders", { headers: { "content-type": "text/plain" }, data: '{"symbol":"RELIANCE","side":"BUY","qty":1}' });
  expect(asText.status()).toBe(415);
  const foreign = await request.post("/api/billing/order", {
    headers: { "content-type": "application/json", origin: "https://evil.example" },
    data: { plan: "plus_month" },
  });
  expect(foreign.status()).toBe(403);
});

test("the price sync and webhooks refuse unauthenticated calls", async ({ request }) => {
  expect((await request.get("/api/cron/sync-eod-prices")).status()).toBe(401);
  expect((await request.get("/api/cron/sync-eod-prices", { headers: { authorization: "Bearer wrong" } })).status()).toBe(401);
  const rzp = await request.post("/api/webhooks/razorpay", { data: "{}", headers: { "x-razorpay-signature": "bad" } });
  expect([400, 503]).toContain(rzp.status());
  const clerk = await request.post("/api/webhooks/clerk", { data: "{}" });
  expect(clerk.status()).toBeGreaterThanOrEqual(400);
});

test("search treats hostile input as text", async ({ request }) => {
  for (const q of ["<script>alert(1)</script>", "' OR 1=1 --", "%00", "a".repeat(500)]) {
    const res = await request.get(`/api/stocks/search?q=${encodeURIComponent(q)}`);
    expect([200, 400, 401]).toContain(res.status());
    expect(await res.text()).not.toContain("<script>");
  }
});
