# Intraday charts: what is built, what is missing, how to switch it on

Written for: the owner of BrokerLens, to decide and then to hand to whoever sets up a data source.

Tags: **[built]** done and tested in this repo. **[unverified]** not checked from here; confirm before relying on it.

## Where things stand (27 Nov 2026)

- **[built]** The charting engine supports 1m, 3m, 5m, 15m, 30m, 1H and 4H bars, aligned to the 09:15 NSE open (1H bars start 09:15, 10:15 and so on; 4H bars are 09:15 to 13:15 and 13:15 to the close). Pre-open and post-close minutes are dropped.
- **[built]** The chart shows the intraday timeframes only when its data source supplies one-minute bars (`minuteBarAdapter`). Without a source, the chips do not exist. The chart never builds intraday bars out of daily ones.
- **[built]** Tests: rollup maths (`charting/test`) and the chart in a browser on synthetic minutes (`virtual-trading/e2e/charting-engine.spec.ts`). No real market data is used in any test.
- **Missing: a lawful source of one-minute bars.** NSE's free public archive is end-of-day only. Nothing free and redistributable exists for intraday.

## What a source must give us

1. One-minute OHLCV per instrument, with history of at least a few months (more for 4H and indicators).
2. A licence that allows showing the data to the public on a website. A personal or single-account API licence does not cover this [unverified for each vendor].
3. For the paper app: the practice market runs 30 days behind real time, so the licence must allow delayed display, and the chart must stop at the practice date. The history API already enforces the date cap for daily bars; the minute path needs the same cap before any intraday data is exposed.
4. A way to run it without a server we pay for: a daily job on the owner's Mac (as the price job does), writing into Postgres.

## Storage, so the free database lasts

One-minute bars are about 375 per stock per day. Nifty 500 for one year is roughly 47 million rows, far over the 500 MB free limit. Plan accordingly:

- Keep minutes only for a short window (for example the last 30 to 60 sessions) and roll older sessions up to 5-minute bars, or
- Start with the Nifty 50 and the main indices only, or
- Store one compressed blob per symbol per month (columnar integers) instead of rows.

Decide this before loading anything.

## Options to evaluate [all unverified]

- NSE's own paid data products (the exchange is the licensor for NSE data).
- Licensed market-data vendors that sell redistribution rights (ask each for the display and delay terms).
- Broker APIs: usually licensed for the account holder's own use, not public display. Do not use them for a public chart.

## Steps once a source is approved

1. Write the loader that fills a `price_minutes` table (or the blob store above) from the Mac job.
2. Add `/api/history/<symbol>/minutes`, session-gated and capped at the practice date, with the same symbol checks as the daily route.
3. In `ChartStudio`, build the adapter with `minuteBarAdapter` instead of `columnsAdapter`.
4. Extend the e2e suite with a seeded synthetic day (never real data in tests).
5. Counsel check on the display and delay wording before launch.

## Rules that stay in force

- Never scrape or imitate a browser to get data. If a source blocks plain requests, report it and stop.
- No claim about regulatory compliance in the UI beyond counsel's written wording.
