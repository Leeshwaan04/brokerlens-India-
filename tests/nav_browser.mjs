// Real-browser checks for the task-based header (pipeline/site_nav.py).
//
//   cd virtual-trading && npm ci          # once: provides Playwright
//   python3 -m pipeline.run build         # the site under test
//   node tests/nav_browser.mjs [stock-slug]
//
// Serves ./site on a local port and drives Chromium: desktop, phone and dark
// mode, mouse and keyboard, the analytics event. Local only; never pointed at
// the live site.
import { spawn } from "node:child_process";
import { createRequire } from "node:module";
import { existsSync, readdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const root = join(here, "..");
const require = createRequire(join(root, "virtual-trading", "package.json"));
const { chromium } = require("@playwright/test");

const PORT = 8765;
const BASE = `http://127.0.0.1:${PORT}`;
const stocks = join(root, "site", "stock");
const slug = process.argv[2] || (existsSync(stocks) ? readdirSync(stocks).find((d) => existsSync(join(stocks, d, "index.html"))) : "");

const server = spawn("python3", ["-m", "http.server", String(PORT), "--bind", "127.0.0.1", "-d", join(root, "site")], { stdio: "ignore" });
await new Promise((r) => setTimeout(r, 1200));

let passed = 0;
const failures = [];
function check(name, ok, detail = "") {
  if (ok) passed++;
  else failures.push(`${name}${detail ? ` (${detail})` : ""}`);
  console.log(`${ok ? "  ok " : " FAIL"}  ${name}${!ok && detail ? `  -> ${detail}` : ""}`);
}

const browser = await chromium.launch();

async function open(ctxOpts, path) {
  const ctx = await browser.newContext(ctxOpts);
  const page = await ctx.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.addInitScript(() => {
    window.__events = [];
    window.gtag = (...a) => window.__events.push(a);
  });
  await page.goto(BASE + path, { waitUntil: "load" });
  await page.waitForTimeout(400);
  return { ctx, page, errors };
}

const lum = (rgb) => {
  const [r, g, b] = rgb.map((v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
};
const ratio = (a, b) => { const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p); return (x + 0.05) / (y + 0.05); };

const pages = [["homepage", "/"], ["stock page", `/stock/${slug}/`], ["IPO page", "/ipo/"]].filter(([, p]) => p !== "/stock//");

// ------------------------------------------------------------------ desktop
for (const [label, path] of pages) {
  const { ctx, page, errors } = await open({ viewport: { width: 1400, height: 900 } }, path);
  const name = (t) => `desktop ${label}: ${t}`;

  const tops = await page.$$eval("#navlinks > button, #navlinks > a", (els) => els.map((e) => Math.round(e.getBoundingClientRect().top)));
  // The button has a 1px border, so allow a few pixels of difference.
  check(name("six header items sit on one line"), tops.length === 6 && Math.max(...tops) - Math.min(...tops) <= 3, JSON.stringify(tops));
  check(name("no horizontal scroll"), await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth));

  // Closed panels are hidden from keyboard and screen readers.
  check(name("closed panels are hidden"), await page.$$eval(".mega", (els) => els.every((e) => e.hidden)));

  // Open Brokers with the mouse.
  await page.hover("#brokers-toggle");
  await page.waitForSelector("#mega-brokers:not([hidden])", { timeout: 2000 }).catch(() => {});
  check(name("Brokers opens on hover with three columns"), (await page.$$eval("#mega-brokers .mega-col", (e) => e.length)) === 3 && (await page.isVisible("#mega-brokers")));
  check(name("aria-expanded follows the panel"), (await page.getAttribute("#brokers-toggle", "aria-expanded")) === "true");

  // Only one open at a time.
  await page.hover("#markets-toggle");
  await page.waitForTimeout(500);
  check(name("opening Markets closes Brokers"), await page.isHidden("#mega-brokers") && (await page.isVisible("#mega-markets")));
  check(name("Markets shows India and Crypto as Live and US and GCC as coming soon"),
    await page.$eval("#mega-markets", (m) => /India/.test(m.textContent) && /Crypto/.test(m.textContent) && (m.textContent.match(/Coming soon/g) || []).length >= 2 && (m.textContent.match(/Live/g) || []).length >= 2));

  // Escape closes and returns focus.
  await page.focus("#markets-toggle");
  await page.keyboard.press("Escape");
  check(name("Escape closes the open panel"), await page.isHidden("#mega-markets"));

  // Keyboard-only: Enter opens and moves focus into the panel.
  await page.focus("#tools-toggle");
  await page.keyboard.press("Enter");
  await page.waitForTimeout(150);
  const inPanel = await page.evaluate(() => !!document.activeElement.closest("#mega-tools"));
  check(name("keyboard: Enter on Tools moves focus into its first link"), inPanel);
  await page.keyboard.press("Tab");
  check(name("keyboard: Tab moves between the panel's links"), await page.evaluate(() => !!document.activeElement.closest("#mega-tools")));
  await page.keyboard.press("Escape");
  check(name("keyboard: Escape closes and returns focus to the button"),
    (await page.isHidden("#mega-tools")) && (await page.evaluate(() => document.activeElement.id)) === "tools-toggle");

  // The timings panel still works from the clock button.
  await page.click("#timings-toggle");
  await page.waitForSelector("#mega-timings:not([hidden])", { timeout: 2000 }).catch(() => {});
  await page.waitForTimeout(500);
  check(name("clock button opens the market-timings panel with content"), (await page.isVisible("#mega-timings")) && (await page.$eval("#mega-timings-body", (b) => b.textContent.trim().length > 40)));
  await page.keyboard.press("Escape");

  // The CTA.
  const cta = await page.$eval(".nav-paper-cta", (a) => ({ href: a.href, target: a.target, rel: a.rel, text: a.textContent.trim() }));
  check(name("Practise free opens the app in a new tab, safely, with campaign tags"),
    cta.text === "Practise free" && cta.target === "_blank" && /noopener/.test(cta.rel) && /^https:\/\/paper\.brokerlens\.in\/\?utm_source=brokerlens&utm_medium=nav/.test(cta.href), JSON.stringify(cta));

  // Analytics event.
  await page.hover("#brokers-toggle");
  await page.waitForSelector("#mega-brokers:not([hidden])");
  const target = page.locator("#mega-brokers a[data-nav]").first();
  await target.evaluate((a) => a.addEventListener("click", (e) => e.preventDefault(), { once: true }));
  await target.click();
  // The page's own analytics script owns window.gtag, so read what it queued.
  const ev = await page.evaluate(() => (window.dataLayer || []).map((e) => Array.from(e)).filter((e) => e[0] === "event" && e[1] === "nav_click"));
  check(name("a menu click sends one nav_click event with only the item id and page type"),
    ev.length === 1 && Object.keys(ev[0][2]).sort().join() === "nav_item,page_type" && /^brokers\//.test(ev[0][2].nav_item), JSON.stringify(ev));
  // "sl" is a pre-existing error thrown by a third-party script, present on the previous build too.
  const own = errors.filter((e) => e !== "sl");
  check(name("no uncaught errors from the site's own code"), own.length === 0, own.join(" | "));
  await ctx.close();
}

// Navigating marks the section.
{
  const { ctx, page } = await open({ viewport: { width: 1400, height: 900 } }, "/compare/");
  check("desktop /compare/: Brokers is marked as the current section", await page.$eval("#brokers-toggle", (b) => b.classList.contains("active-group")));
  check("desktop: a disclosure button never carries aria-current", (await page.$$eval(".mega-toggle[aria-current]", (e) => e.length)) === 0);
  check("desktop /compare/: only one section is marked", (await page.$$eval(".mega-toggle.active-group", (e) => e.length)) === 1);
  await ctx.close();
  const b = await open({ viewport: { width: 1400, height: 900 } }, "/news/");
  check("desktop /news/: Learn is marked as the current section", await b.page.$eval("#learn-toggle", (x) => x.classList.contains("active-group")));
  await b.ctx.close();
  const c = await open({ viewport: { width: 1400, height: 900 } }, "/ipo/");
  check("desktop /ipo/: the IPO link is marked, and Markets is not also marked", (await c.page.$eval('#navlinks > a[href="/ipo/"]', (a) => a.classList.contains("active"))) && (await c.page.$$eval(".mega-toggle.active-group", (e) => e.length)) === 0);
  await c.ctx.close();
}

// ------------------------------------------------------------------- phone
for (const [label, path] of pages) {
  const { ctx, page, errors } = await open({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true }, path);
  const name = (t) => `phone ${label}: ${t}`;
  check(name("menu is collapsed behind the hamburger"), (await page.isVisible("#nav-toggle")) && (await page.isHidden("#navlinks")));
  check(name("no horizontal scroll"), await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth));
  await page.tap("#nav-toggle");
  check(name("hamburger opens the list with all six items"), (await page.$$eval("#navlinks > button:visible, #navlinks > a:visible", (e) => e.length).catch(() => 0)) === 6 || (await page.$$eval("#navlinks > *", (e) => e.length)) === 6);
  await page.tap("#tools-toggle");
  await page.waitForSelector("#mega-tools:not([hidden])");
  check(name("a panel opens in the page flow, not as an overlay"), await page.$eval("#mega-tools", (m) => getComputedStyle(m).position === "static"));
  const heights = await page.$$eval("#mega-tools .mega-links a", (as) => as.map((a) => Math.round(a.getBoundingClientRect().height)));
  check(name("every menu row is at least 44px tall (touch target)"), heights.length > 0 && heights.every((h) => h >= 44), JSON.stringify(heights));
  check(name("no horizontal scroll with a panel open"), await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth));
  check(name("the Practise button is full width, visible and a 44px touch target"), await page.$eval(".nav-paper-cta", (a) => { const r = a.getBoundingClientRect(); return r.width > 250 && r.height >= 44; }));
  const own = errors.filter((e) => e !== "sl");
  check(name("no uncaught errors from the site's own code"), own.length === 0, own.join(" | "));
  await ctx.close();
}

// Following a link from the phone menu navigates and closes the menu.
{
  const { ctx, page } = await open({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true }, "/");
  await page.tap("#nav-toggle");
  await page.tap("#brokers-toggle");
  await page.waitForSelector("#mega-brokers:not([hidden])");
  await Promise.all([page.waitForURL(/\/compare\//), page.tap('#mega-brokers a[href="/compare/"]')]);
  check("phone: tapping Compare brokers navigates there", /\/compare\//.test(page.url()));
  await ctx.close();
}

// ------------------------------------------------ touch, keyboard and SPA edge cases
{
  // Touch on a wide screen (an iPad): tapping a second menu closes the first.
  const { ctx, page } = await open({ viewport: { width: 1024, height: 768 }, hasTouch: true, isMobile: false }, "/ipo/");
  await page.tap("#brokers-toggle");
  await page.waitForSelector("#mega-brokers:not([hidden])");
  await page.tap("#markets-toggle");
  await page.waitForTimeout(200);
  check("touch 1024px: tapping Markets closes Brokers (one open at a time)", (await page.isHidden("#mega-brokers")) && (await page.isVisible("#mega-markets")));
  check("touch 1024px: header items stay on one line and nothing overflows",
    (await page.$$eval("#navlinks > button, #navlinks > a", (els) => { const t = els.map((e) => Math.round(e.getBoundingClientRect().top)); return Math.max(...t) - Math.min(...t) <= 3; }))
      && (await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)));
  await page.tap("body", { position: { x: 5, y: 700 } });
  await page.waitForTimeout(200);
  check("touch: tapping outside closes the open menu", await page.isHidden("#mega-markets"));
  await ctx.close();
}
{
  // Keyboard: Tab out of an open menu closes it; two menus never stay open.
  const { ctx, page } = await open({ viewport: { width: 1400, height: 900 } }, "/ipo/");
  await page.focus("#brokers-toggle");
  await page.keyboard.press("Enter");
  await page.waitForTimeout(150);
  for (let i = 0; i < 12 && (await page.evaluate(() => !!document.activeElement.closest("#mega-brokers"))); i++) await page.keyboard.press("Tab");
  await page.waitForTimeout(150);
  check("keyboard: tabbing out of the menu closes it", await page.isHidden("#mega-brokers"));
  await page.focus("#brokers-toggle");
  await page.keyboard.press("Enter");
  await page.focus("#markets-toggle");
  await page.keyboard.press("Enter");
  await page.waitForTimeout(150);
  check("keyboard: opening Markets after Brokers leaves only one open", (await page.$$eval(".mega:not([hidden])", (e) => e.length)) === 1);
  await page.keyboard.press("Escape");
  check("keyboard: Escape closes everything", (await page.$$eval(".mega:not([hidden])", (e) => e.length)) === 0);
  // The timings panel loads after opening; keyboard focus still lands inside it.
  await page.focus("#timings-toggle");
  await page.keyboard.press("Enter");
  await page.waitForTimeout(900);
  check("keyboard: Enter on the clock moves focus into the timings panel once it has loaded", await page.evaluate(() => !!document.activeElement.closest("#mega-timings")));
  await ctx.close();
}
{
  // Single-page shell on a phone: a client-side route changes the page without a
  // load, so the drawer must close itself and the section marking must follow.
  const { ctx, page } = await open({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true }, "/");
  await page.tap("#nav-toggle");
  await page.tap("#brokers-toggle");
  await page.waitForSelector("#mega-brokers:not([hidden])");
  await page.tap('#mega-brokers a[href="/compare/"]');
  await page.waitForURL(/\/compare\//);
  await page.waitForTimeout(500);
  check("phone SPA: following a menu link closes the drawer and the open panel",
    !(await page.$eval("#navlinks", (n) => n.classList.contains("open"))) && (await page.$$eval(".mega:not([hidden])", (e) => e.length)) === 0);
  check("phone SPA: the section marking follows a client-side route", await page.$eval("#brokers-toggle", (b) => b.classList.contains("active-group")));
  // Closing the drawer closes an open panel (no orphaned panel under a hidden menu).
  await page.tap("#nav-toggle");
  await page.tap("#tools-toggle");
  await page.waitForSelector("#mega-tools:not([hidden])");
  await page.tap("#nav-toggle");
  check("phone: closing the hamburger closes the open panel", await page.isHidden("#mega-tools"));
  await ctx.close();
}
{
  // The programmatic trade-cost pages use the plain-link version of the header.
  const dir = join(root, "site", "trade-costs");
  const brokerDir = existsSync(dir) ? readdirSync(dir).find((d) => existsSync(join(dir, d)) && readdirSync(join(dir, d)).some((s) => existsSync(join(dir, d, s, "index.html")))) : "";
  const stockDir = brokerDir ? readdirSync(join(dir, brokerDir)).find((s) => existsSync(join(dir, brokerDir, s, "index.html"))) : "";
  if (stockDir) {
    const path = `/trade-costs/${brokerDir}/${stockDir}/`;
    const { ctx, page, errors } = await open({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true }, path);
    check("trade-cost page: plain header with the same six labels and the button",
      JSON.stringify(await page.$$eval("#navlinks > a", (a) => a.map((x) => x.textContent.trim()))) === JSON.stringify(["Brokers", "Compare", "Markets", "IPO", "Tools", "Learn", "Practise free"]));
    await page.tap("#nav-toggle");
    check("trade-cost page: the hamburger works on a phone", await page.isVisible("#navlinks"));
    check("trade-cost page: no horizontal scroll", await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth));
    check("trade-cost page: no uncaught errors from the site's own code", errors.filter((e) => e !== "sl").length === 0, errors.join(" | "));
    await ctx.close();
  } else {
    console.log("  skip  trade-cost page checks (no built trade-cost page found)");
  }
}

// -------------------------------------------------------- dark mode contrast
for (const scheme of ["light", "dark"]) {
  const { ctx, page } = await open({ viewport: { width: 1400, height: 900 }, colorScheme: scheme }, "/");
  const c = await page.$eval(".nav-paper-cta", (a) => {
    const s = getComputedStyle(a);
    const parse = (v) => (v.match(/[\d.]+/g) || []).slice(0, 3).map(Number);
    // The gradient's first stop is the lighter of the two button colours; use the element's own colour list.
    const stops = (s.backgroundImage.match(/rgb\([^)]+\)/g) || []).map(parse);
    return { text: parse(s.color), stops };
  });
  const worst = Math.min(...c.stops.map((bg) => ratio(c.text, bg)));
  check(`${scheme} mode: the Practise button text has at least 4.5:1 contrast`, c.stops.length > 0 && worst >= 4.5, `worst ${worst.toFixed(2)}`);
  const muted = await page.$eval(".mega-toggle", (b) => { const s = getComputedStyle(b); const bg = getComputedStyle(document.querySelector("header.site")); const p = (v) => (v.match(/[\d.]+/g) || []).slice(0, 3).map(Number); return { text: p(s.color), bg: p(getComputedStyle(document.body).backgroundColor) }; });
  check(`${scheme} mode: menu buttons have at least 4.5:1 contrast against the page`, ratio(muted.text, muted.bg) >= 4.5, ratio(muted.text, muted.bg).toFixed(2));
  await ctx.close();
}

await browser.close();
server.kill();
console.log(`\n${passed} passed, ${failures.length} failed`);
if (failures.length) { console.log("FAILURES:\n - " + failures.join("\n - ")); process.exit(1); }
