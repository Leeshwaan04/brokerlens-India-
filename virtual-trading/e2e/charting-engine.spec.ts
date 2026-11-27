import { expect, test } from "@playwright/test";
import path from "node:path";

/* eslint-disable @typescript-eslint/no-explicit-any -- page.evaluate code runs in the browser against an untyped global */
// The charting engine in a real browser with synthetic data (no market data, no app, no account).
// Covers what the paper app does not ship yet: the intraday timeframes, which only appear when an
// adapter supplies minute bars.
const pub = path.join(__dirname, "..", "public", "charting");

test("intraday timeframes appear only with a minute source, and roll up correctly", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("about:blank");
  await page.setContent(`<!doctype html><body style="width:900px"><div id="host"></div></body>`);
  await page.addScriptTag({ path: path.join(pub, "lightweight-charts.js") });
  await page.addScriptTag({ path: path.join(pub, "engine.js") });

  const summary = await page.evaluate(async () => {
    const C = (window as unknown as { BrokerLensCharting: any }).BrokerLensCharting;
    // Two synthetic sessions of 1-minute bars, 09:15 to 15:29 IST (UTC+5:30).
    const bars: any[] = [];
    for (const [date, base] of [["2026-10-26", 100], ["2026-10-27", 104]] as const) {
      const [y, m, d] = date.split("-").map(Number);
      const midnightIst = Date.UTC(y, m - 1, d) / 1000 - 19800;
      for (let min = 555; min < 930; min++) {
        const p = base + (min - 555) * 0.01;
        bars.push({ t: midnightIst + min * 60, o: p, h: p + 0.05, l: p - 0.05, c: p + 0.01, v: 10 });
      }
    }
    const host = document.getElementById("host")!;
    await C.mountStudio(host, { adapter: C.minuteBarAdapter({ symbol: "SYNTH", loadMinutes: async () => bars }), storagePrefix: "t_intraday" });
    return { chips: [...host.querySelectorAll('[aria-label="Timeframe"] .blc-chip')].map((b) => b.textContent) };
  });
  expect(summary.chips).toEqual(["1m", "3m", "5m", "15m", "30m", "1H", "4H", "1D", "1W", "1M"]);

  const host = page.locator("#host");
  await host.getByRole("button", { name: "15m", exact: true }).click();
  await expect(host.getByRole("button", { name: "15m", exact: true })).toHaveAttribute("aria-pressed", "true");
  // 375 minutes per session is 25 fifteen-minute bars, two sessions.
  await expect(host.locator(".blc-sr")).toContainText(/SYNTH 15m chart, \d+ bars from 2026-10-2[67]/);
  await host.getByRole("button", { name: "4H", exact: true }).click();
  // 4H: 09:15-13:15 and 13:15-close, so four bars over two sessions.
  await expect(host.locator(".blc-sr")).toContainText(/SYNTH 4H chart, 4 bars/);
  // The 1D range chip exists on intraday timeframes only.
  await expect(host.getByRole("group", { name: "Time range" }).getByRole("button", { name: "1D", exact: true })).toBeVisible();
  await host.getByRole("button", { name: "1D", exact: true }).first().click(); // timeframe 1D
  await expect(host.getByRole("group", { name: "Time range" }).getByRole("button", { name: "1D", exact: true })).toHaveCount(0);
  expect(errors).toEqual([]);
});

test("a daily-only source never offers intraday", async ({ page }) => {
  await page.goto("about:blank");
  await page.setContent(`<!doctype html><body style="width:900px"><div id="host"></div></body>`);
  await page.addScriptTag({ path: path.join(pub, "lightweight-charts.js") });
  await page.addScriptTag({ path: path.join(pub, "engine.js") });
  const chips = await page.evaluate(async () => {
    const C = (window as unknown as { BrokerLensCharting: any }).BrokerLensCharting;
    const bars: any[] = [];
    for (let i = 0; i < 60; i++) {
      const t = Date.UTC(2026, 8, 1 + i) / 1000;
      bars.push({ t, o: 100 + i, h: 102 + i, l: 99 + i, c: 101 + i, v: 1000 });
    }
    const host = document.getElementById("host")!;
    await C.mountStudio(host, { adapter: { symbol: "DAILYONLY", loadDaily: async () => bars }, storagePrefix: "t_daily" });
    return [...host.querySelectorAll('[aria-label="Timeframe"] .blc-chip')].map((b) => b.textContent);
  });
  expect(chips).toEqual(["1D", "1W", "1M"]);
});
