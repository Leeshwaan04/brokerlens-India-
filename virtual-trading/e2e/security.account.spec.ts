import { expect, test } from "@playwright/test";
import { E2E_USER, purgeE2eUser, sql } from "./db";

// VAPT, signed in as the throwaway user_e2e (dev auth, local server only):
// input fuzzing, cross-account access, races and caps on the order API.
test.describe.configure({ mode: "serial" });

const json = { "content-type": "application/json" };
let accountId = "";

async function orderCount(): Promise<number> {
  const [r] = await sql<{ n: string }>(`select count(*) n from orders where account_id = $1`, [accountId]);
  return Number(r.n);
}

test.beforeAll(async () => {
  await purgeE2eUser();
  await sql(`insert into users (id, email) values ($1, 'e2e-vapt@example.test') on conflict do nothing`, [E2E_USER]);
  const [a] = await sql<{ id: string }>(
    `insert into virtual_accounts (user_id, broker_id, cash_balance, starting_balance) values ($1, 'zerodha', 1000000, 1000000) returning id`,
    [E2E_USER],
  );
  accountId = a.id;
});

test.afterAll(async () => {
  await sql(`delete from orders where account_id in (select id from virtual_accounts where user_id like 'user_vapt_other%')`).catch(() => undefined);
  await sql(`delete from virtual_accounts where user_id like 'user_vapt_other%'`).catch(() => undefined);
  await sql(`delete from users where id like 'user_vapt_other%'`).catch(() => undefined);
  await purgeE2eUser();
});

test("order fuzzing: every malformed order is refused and none is stored", async ({ request }) => {
  const base = { symbol: "RELIANCE", side: "BUY", qty: 1 };
  const bad: [string, object][] = [
    ["zero qty", { ...base, qty: 0 }],
    ["negative qty", { ...base, qty: -5 }],
    ["fractional qty", { ...base, qty: 1.5 }],
    ["huge qty", { ...base, qty: 1e12 }],
    ["infinite qty", { ...base, qty: 1e999 }],
    ["string qty", { ...base, qty: "10" }],
    ["unknown symbol", { ...base, symbol: "NOTASTOCK" }],
    ["sql in symbol", { ...base, symbol: "RELIANCE'; DROP TABLE orders;--" }],
    ["bad side", { ...base, side: "HOLD" }],
    ["bad order type", { ...base, orderType: "ICEBERG" }],
    ["bad validity", { ...base, validity: "FOREVER" }],
    ["limit without price", { ...base, orderType: "LIMIT" }],
    ["limit far outside band", { ...base, orderType: "LIMIT", limitPrice: 1 }],
    ["negative limit", { ...base, orderType: "LIMIT", limitPrice: -100 }],
    ["huge limit", { ...base, orderType: "LIMIT", limitPrice: 1e15 }],
    ["stop-loss without trigger", { ...base, side: "SELL", orderType: "SL_M" }],
    ["MIS stop on wrong side", { ...base, product: "MIS", orderType: "LIMIT", limitPrice: 1200, stopLossPrice: 2000 }],
    ["short sell delivery", { ...base, side: "SELL" }],
    ["order beyond cash", { ...base, qty: 100000 }],
    ["nested objects", { symbol: { $ne: null }, side: ["BUY"], qty: { v: 1 } }],
    ["long client id", { ...base, clientOrderId: "x".repeat(10000) }],
  ];
  const before = await orderCount();
  for (const [name, body] of bad) {
    const res = await request.post("/api/orders", { headers: json, data: body });
    expect([400, 422], `${name} -> ${res.status()} ${(await res.text()).slice(0, 120)}`).toContain(res.status());
  }
  expect(await orderCount(), "a refused order was stored").toBe(before);
});

test("cross-site and wrong-type requests to the order API are refused even when signed in", async ({ request }) => {
  expect((await request.post("/api/orders", { headers: { "content-type": "text/plain" }, data: '{"symbol":"RELIANCE","side":"BUY","qty":1}' })).status()).toBe(415);
  expect((await request.post("/api/orders", { headers: { ...json, origin: "https://evil.example" }, data: { symbol: "RELIANCE", side: "BUY", qty: 1 } })).status()).toBe(403);
  expect((await request.post("/api/orders", { headers: { ...json, origin: "null" }, data: { symbol: "RELIANCE", side: "BUY", qty: 1 } })).status()).toBe(403);
  expect(await orderCount()).toBe(0);
});

test("another account's order cannot be read, cancelled or changed by this user", async ({ request }) => {
  await sql(`insert into users (id, email) values ('user_vapt_other', 'other-vapt@example.test') on conflict do nothing`);
  const [other] = await sql<{ id: string }>(
    `insert into virtual_accounts (user_id, broker_id, cash_balance, starting_balance) values ('user_vapt_other', 'zerodha', 1000000, 1000000) returning id`,
  );
  const [o] = await sql<{ id: string }>(
    `insert into orders (account_id, symbol, side, qty, status, target_trade_date) values ($1, 'RELIANCE', 'BUY', 1, 'PENDING', current_date + 1) returning id`,
    [other.id],
  );
  const del = await request.delete(`/api/orders/${o.id}`, { headers: json });
  expect([404, 409], `cancel foreign order -> ${del.status()}`).toContain(del.status());
  const [after] = await sql<{ status: string }>(`select status from orders where id = $1`, [o.id]);
  expect(after.status).toBe("PENDING");
  // The statement export never includes another account's rows.
  const stmt = await request.get("/api/reports/statement", { maxRedirects: 0 });
  expect(await stmt.text()).not.toContain(o.id);
});

test("races cannot spend the same cash twice", async ({ request }) => {
  const [px] = await sql<{ close: string }>(
    `select close from daily_prices where symbol = 'RELIANCE' order by trade_date desc limit 1`,
  );
  const close = Number(px.close);
  const qty = Math.floor(780_000 / close);
  const results = await Promise.all(
    Array.from({ length: 10 }, () => request.post("/api/orders", { headers: json, data: { symbol: "RELIANCE", side: "BUY", qty } })),
  );
  const codes = results.map((r) => r.status());
  expect(codes.every((c) => c < 500), `codes ${codes}`).toBe(true);
  expect(codes.filter((c) => c === 201).length, `accepted: ${codes}`).toBe(1);
  await sql(`delete from orders where account_id = $1`, [accountId]);
});

test("a repeated client order id is placed once", async ({ request }) => {
  const body = { symbol: "TCS", side: "BUY", qty: 1, clientOrderId: "vapt-dup-1" };
  const rs = await Promise.all([1, 2, 3, 4].map(() => request.post("/api/orders", { headers: json, data: body })));
  expect(rs.every((r) => r.status() < 500)).toBe(true);
  const [r] = await sql<{ n: string }>(`select count(*) n from orders where account_id = $1 and client_order_id = 'vapt-dup-1'`, [accountId]);
  expect(Number(r.n)).toBe(1);
  await sql(`delete from orders where account_id = $1`, [accountId]);
});

test("open-order caps hold under a flood", async ({ request }) => {
  const mk = (i: number) => request.post("/api/orders", { headers: json, data: { symbol: "INFY", side: "BUY", qty: 1, orderType: "LIMIT", limitPrice: 1000 + i * 0, validity: "GTT" } });
  // GTT orders are capped lower than ordinary open orders.
  const rs = await Promise.all(Array.from({ length: 30 }, (_, i) => mk(i)));
  const accepted = rs.filter((r) => r.status() === 201).length;
  // Busy is a clean 503 with Retry-After; a 500 (an unexplained failure) is a bug.
  expect(rs.map((r) => r.status()).filter((c) => c >= 500 && c !== 503), `statuses ${rs.map((r) => r.status())}`).toEqual([]);
  for (const r of rs.filter((x) => x.status() === 503)) expect(r.headers()["retry-after"]).toBeTruthy();
  expect(accepted, "GTT cap").toBeLessThanOrEqual(20);
  await sql(`delete from orders where account_id = $1`, [accountId]);
});

test("billing routes refuse bad plans and unsigned confirmations", async ({ request }) => {
  for (const plan of ["", "free", "plus_month; drop table payments", "__proto__", 1, null, ["plus_month"]]) {
    const res = await request.post("/api/billing/order", { headers: json, data: { plan } });
    expect([400, 422, 429, 503], `plan ${JSON.stringify(plan)} -> ${res.status()}`).toContain(res.status());
  }
  const forged = await request.post("/api/billing/verify", {
    headers: json,
    data: { razorpay_order_id: "order_FAKE", razorpay_payment_id: "pay_FAKE", razorpay_signature: "0".repeat(64) },
  });
  expect([400, 404, 422, 503]).toContain(forged.status());
  const [u] = await sql<{ plus_until: string | null }>(`select plus_until from users where id = $1`, [E2E_USER]);
  expect(u.plus_until, "Plus was granted by a forged confirmation").toBeNull();
});

test("the post-onboarding redirect cannot be pointed off-site", async ({ page }) => {
  for (const evil of ["https://evil.example", "//evil.example", "/\\evil.example"]) {
    await page.goto(`/onboarding/broker?next=${encodeURIComponent(evil)}`);
    await expect(page).toHaveURL(/localhost:3200\/dashboard/);
  }
});

test("hostile text in pages is shown as text, not run", async ({ page }) => {
  let dialog = false;
  page.on("dialog", (d) => { dialog = true; void d.dismiss(); });
  for (const q of ["<img src=x onerror=alert(1)>", "\"><script>alert(1)</script>"]) {
    await page.goto(`/trade?symbol=${encodeURIComponent(q)}`);
    await page.goto(`/trade?symbol=RELIANCE&side=${encodeURIComponent(q)}`);
    await page.goto(`/costs?switched=${encodeURIComponent(q)}`);
    await page.goto(`/orders?x=${encodeURIComponent(q)}`);
  }
  expect(dialog, "script ran").toBe(false);
});
