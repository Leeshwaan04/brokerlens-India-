import { expect, test, type Page } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { join } from "node:path";
import { E2E_USER, sql } from "./db";

// One user's whole life in the app, in order: sign-up, onboarding, every
// kind of order, settlement against real session prices, the pages that
// read the results, paid-feature gating, reset, and deletion.
test.describe.configure({ mode: "serial" });

let page: Page;
const pageErrors: string[] = [];

test.beforeAll(async ({ browser }) => {
  page = await browser.newPage();
  page.on("pageerror", (e) => pageErrors.push(e.message));
});

test.afterAll(async () => {
  expect(pageErrors, `uncaught browser errors: ${pageErrors.join(" | ")}`).toEqual([]);
  await page.close();
});

async function accountId(): Promise<string> {
  const [row] = await sql<{ id: string }>(`select id from virtual_accounts where user_id = $1`, [E2E_USER]);
  return row.id;
}

async function settleEverythingDue() {
  // The real settlement code, for each session the user's open orders
  // target, run as its own process (scripts/settle-session.mts).
  const settlePendingOrders = async (d: string) =>
    execFileSync("npx", ["tsx", "scripts/settle-session.mts", d], { cwd: join(__dirname, ".."), env: process.env, stdio: "pipe" });
  for (let i = 0; i < 3; i++) {
    const due = await sql<{ d: string }>(
      `select distinct to_char(target_trade_date, 'YYYY-MM-DD') d from orders o join virtual_accounts a on a.id = o.account_id
       where a.user_id = $1 and o.status = 'PENDING' order by 1`,
      [E2E_USER],
    );
    if (due.length === 0) return;
    for (const { d } of due) await settlePendingOrders(d);
  }
}

test("a new user is sent to onboarding and starts with ₹10 lakh", async () => {
  await page.goto("/");
  await expect(page).toHaveURL(/\/onboarding\/broker/);
  await expect(page.getByRole("heading", { name: "Choose a broker to practise with" })).toBeVisible();
  await page.locator('input[name="brokerId"][value="zerodha"]').check();
  await page.getByRole("button", { name: /Start with ₹10,00,000/ }).click();
  await expect(page).toHaveURL(/\/dashboard/);
  await expect(page.getByText("₹10,00,000.00").first()).toBeVisible();
  const [ev] = await sql<{ n: string }>(
    `select count(*) n from events where name = 'onboarding_completed' and account_id = $1`,
    [await accountId()],
  );
  expect(Number(ev.n)).toBe(1);
});

test("the trade screen shows the quote, chart, market watch and order window", async () => {
  await page.goto("/trade?symbol=RELIANCE");
  await expect(page.getByRole("heading", { name: "RELIANCE", exact: true })).toBeVisible();
  for (const label of ["Open", "High", "Low", "Prev. close", "Volume"]) await expect(page.getByText(label, { exact: true }).first()).toBeVisible();
  await expect(page.getByText(/Closes, last \d+ sessions/)).toBeVisible();
  await expect(page.getByText("Order window").first()).toBeVisible();
  await expect(page.getByText(/Practice market|Oct|Nov/).first()).toBeVisible();
});

test("a delivery market buy is placed and listed as open", async () => {
  await page.locator("#qty").fill("10");
  await expect(page.getByText(/fills at (the|today.s) .*(open|close)/i).first()).toBeVisible();
  await page.getByRole("button", { name: "Place buy order" }).click();
  await expect(page.getByText(/Market buy order for 10 RELIANCE placed/)).toBeVisible();
  const rows = await sql(`select * from orders where account_id = $1`, [await accountId()]);
  expect(rows).toHaveLength(1);
});

test("an out-of-band limit price is refused in the window, then a GTT limit is placed", async () => {
  await page.getByRole("radio", { name: "Limit" }).click();
  await page.locator("#price").fill("1");
  await expect(page.getByText(/Keep the limit price within 20%/)).toBeVisible();
  await expect(page.getByRole("button", { name: "Place buy order" })).toBeDisabled();
  const closeText = (await page.getByText(/Last close ₹/).first().textContent()) ?? "";
  const close = Number(closeText.replace(/[^\d.]/g, ""));
  await page.locator("#price").fill((close * 0.95).toFixed(2));
  await page.locator("#qty").fill("5");
  await page.getByLabel("GTT, up to 1 year").check();
  await page.getByRole("button", { name: "Place buy order" }).click();
  await expect(page.getByText(/Limit buy order for 5 RELIANCE placed/)).toBeVisible();
});

test("an intraday order with a stop-loss and target is placed", async () => {
  await page.goto("/trade?symbol=RELIANCE");
  await page.getByRole("radio", { name: "Intraday (MIS)" }).click();
  await page.getByRole("radio", { name: "Limit" }).click();
  const closeText = (await page.getByText(/Last close ₹/).first().textContent()) ?? "";
  const close = Number(closeText.replace(/[^\d.]/g, ""));
  await page.locator("#price").fill(close.toFixed(2));
  await page.locator("#qty").fill("20");
  await page.locator("#mis-stop").fill((close * 0.97).toFixed(2));
  await page.locator("#mis-target").fill((close * 1.03).toFixed(2));
  await expect(page.getByText(/^Intraday: /)).toBeVisible();
  await expect(page.getByText(/Margin blocked/)).toBeVisible();
  await page.getByRole("button", { name: "Place buy order" }).click();
  await expect(page.getByText(/Intraday Limit buy order for 20 RELIANCE placed/)).toBeVisible();
  const [mis] = await sql<{ n: string }>(`select count(*) n from orders where account_id = $1 and product = 'MIS'`, [await accountId()]);
  expect(Number(mis.n)).toBe(1);
});

test("keyboard shortcuts switch side and move through the market watch", async () => {
  await page.goto("/trade?symbol=RELIANCE");
  await page.locator("body").click({ position: { x: 5, y: 300 } });
  await page.keyboard.press("s");
  await expect(page).toHaveURL(/side=SELL/);
  await page.keyboard.press("ArrowDown");
  await expect(page).not.toHaveURL(/symbol=RELIANCE/);
});

test("the watchlist toggles", async () => {
  await page.goto("/trade?symbol=RELIANCE");
  await page.getByRole("button", { name: /Watch$/ }).click();
  await expect(page.getByRole("button", { name: /Watching/ })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Watchlist" })).toBeVisible();
});

test("settlement fills orders against real session prices and every page agrees", async () => {
  await settleEverythingDue();
  const rows = await sql<{ status: string; product: string; order_type: string }>(
    `select status, product, order_type from orders where account_id = $1`,
    [await accountId()],
  );
  expect(rows.length).toBe(3);
  // The delivery market buy always fills; the others fill or end by their own rules.
  expect(rows.find((r) => r.product === "CNC" && r.order_type === "MARKET")?.status).toBe("FILLED");
  expect(rows.every((r) => ["FILLED", "CANCELLED", "PENDING"].includes(r.status))).toBe(true);

  await page.goto("/orders");
  await expect(page.getByRole("heading", { name: "Orders", exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "How fills work" })).toBeVisible();
  await expect(page.getByText(/Filled/).first()).toBeVisible();

  await page.goto("/portfolio");
  await expect(page.getByText("RELIANCE").first()).toBeVisible();

  await page.goto("/dashboard");
  await expect(page.getByText(/Charges paid/i).first()).toBeVisible();
});

test("the cost replay ranks brokers and switching broker is confirmed", async () => {
  await page.goto("/costs");
  await expect(page.getByRole("heading", { name: "Broker cost replay", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Practise with" }).first().click();
  await expect(page.getByText(/You are now practising with/).first()).toBeVisible();
});

test("Plus is offered, and its statement is gated until bought", async () => {
  await page.goto("/plus");
  await expect(page.getByRole("heading", { name: "BrokerLens Plus", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Pay for Plus, 1 month" })).toBeVisible();
  await expect(page.getByText(/Test mode: no real money moves/).first()).toBeVisible();
  await page.goto("/api/reports/statement");
  await expect(page).toHaveURL(/\/plus\?from=statement/);
});

test("the admin page does not exist for a normal user", async () => {
  const res = await page.goto("/admin");
  expect(res?.status()).toBe(404);
});

test("the trade screen fits a phone without sideways scrolling", async () => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/trade?symbol=RELIANCE");
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
  await expect(page.getByText("Order window").first()).toBeVisible();
  await page.setViewportSize({ width: 1400, height: 900 });
});

test("starting over clears trades and restores the cash", async () => {
  await page.goto("/account");
  const form = page.locator("form", { has: page.getByRole("button", { name: "Reset portfolio" }) });
  await form.locator('input[name="confirm"]').fill("RESET");
  await form.getByRole("button", { name: "Reset portfolio" }).click();
  await expect.poll(async () => (await sql(`select 1 from orders where account_id = $1`, [await accountId()])).length).toBe(0);
  const [acct] = await sql<{ cash: string }>(`select cash_balance cash from virtual_accounts where user_id = $1`, [E2E_USER]);
  expect(Number(acct.cash)).toBe(1_000_000);
});

test("deleting the account removes the user and everything tied to them", async () => {
  await page.goto("/account");
  const form = page.locator("form", { has: page.getByRole("button", { name: "Delete my account" }) });
  await form.locator('input[name="confirm"]').fill("DELETE");
  await form.getByRole("button", { name: "Delete my account" }).click();
  await expect.poll(async () => (await sql(`select 1 from users where id = $1`, [E2E_USER])).length).toBe(0);
  expect(await sql(`select 1 from virtual_accounts where user_id = $1`, [E2E_USER])).toHaveLength(0);
});
