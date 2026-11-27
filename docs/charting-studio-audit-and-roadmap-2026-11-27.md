# BrokerLens Charting Studio: audit and phased roadmap (27 Nov 2026)

Written for: the owner of BrokerLens, as a decision document before any build.

Tags: **[measured]** read from the repo, the built site, the live site or the database today. **[estimate]** my projection. **[unverified]** not checked from here.

---

## 1. Verdict

1. **A good renderer exists; a charting product does not.** brokerlens.in has a capable stock chart (candles, line, area, baseline, five indicators, a saved target line, PNG export). Everything else you described is missing, and the paper-trading app has only a 60-point line.
2. **Data, not UI, is the binding constraint.** The chart is backed by 120 daily bars (about six months) per stock. MACD, Ichimoku, weekly and monthly charts, backtests and serious technical analysis need years, adjusted for splits and bonuses. There is no intraday data anywhere, and none can be had for free.
3. **Build one engine, not three charts.** A shared, framework-free engine (data model, resampling, indicators, drawings, themes, saved-config format) on the existing renderer, copied as static files into both sites. This keeps the paper app's worker size untouched.
4. **Two of your asks need decisions, not just work:** intraday timeframes (licensed data, legal review) and AI signals (SEBI research-analyst territory; the legal sign-off you received covers the 30-day price rule, not this).

---

## 2. Audit of what exists

### 2.1 brokerlens.in
| Area | Finding | Evidence |
|---|---|---|
| Renderer | TradingView Lightweight Charts v5.2.1, self-hosted, Apache-2.0 | `site/assets/js/vendor/...`, 198 KB raw, **62 KB gzip** [measured] |
| Stock chart | One 997-line script: 4 chart types, ranges 1W, 1M, 3M, 6M, All, SMA 20, EMA 20, EMA 50, Bollinger, RSI 14, "Smart Zones", volume, log scale, magnet crosshair, expand, PNG export | `stock-chart.js`, 33 KB raw, **8 KB gzip** [measured] |
| Drawing | Only a horizontal "target price" line | same file |
| Persistence | `localStorage` only (preferences, one target per stock). No accounts exist on this site | `PREFS_KEY`, `TARGETS_KEY` [measured] |
| Stock data | 2,619 files, 26 MB, **120 daily bars each**, real OHLCV from NSE bhavcopy. Live file for Reliance runs 4 Jun to 26 Nov 2026 (fresh) | `/data/equity-history/*.json` [measured live] |
| Crypto | 28 coins, 365 daily **closes only** (line, no candles), because the free feed has no daily OHLC past 30 days | `crypto-history` [measured] |
| Indices, commodities, currencies, F&O | **No chart data** | none on disk |
| Other charts | `chart.js`, a 7 KB dependency-free canvas renderer for broker series and comparisons. Keep as is | [measured] |
| Hard limits | Cloudflare Assets file ceiling 20,000 (site is at 19,655); strict CSP `script-src 'self'` | `_headers` [measured] |

### 2.2 paper.brokerlens.in
| Area | Finding |
|---|---|
| Chart | `PriceChart.tsx`, 69 lines of inline SVG: closes only, last 60 sessions, no interaction [measured] |
| Data | OHLCV in Postgres for the Nifty 500, **83 sessions** loaded (history window 90 days); capped at the practice date, which is 30 days behind the real one [measured] |
| Indices | 9 indices, daily open/high/low/close, 82 sessions [measured] |
| Persistence | Accounts and a database exist (Clerk, Supabase): saved layouts are feasible here |
| Worker budget | 2.40 MB of a 3 MB gzip limit [measured]. Static files served from the assets folder are not part of the worker script |

### 2.3 Reuse, enhance, rebuild
| | Items |
|---|---|
| **Reuse as is** | Lightweight Charts renderer; theme-token colour reading; PNG export; SMA, EMA, Bollinger and RSI maths (after tests); the small canvas renderer for non-price charts; bhavcopy ingestion; corporate-action detection (paper app) |
| **Enhance** | Range and timeframe handling (daily only today); preferences (versioned schema); target line (becomes a general price-line and drawing object); the 120-bar history (needs 5+ years) |
| **Rebuild** | The monolithic `stock-chart.js` into engine modules; the paper app's chart; drawing tools (none exist); persistence layer for signed-in users; anything intraday |

---

## 3. Constraints that shape the design

1. **Intraday (1m to 4H) has no source.** NSE's public archives are end-of-day. Intraday history needs a licensed vendor or exchange feed, with redistribution terms and cost [unverified: prices and terms]. SEBI's rules on real-time data and the 30-day practice delay also apply. **Plan: ship Daily, Weekly and Monthly now (weekly and monthly are computed from daily, free). Treat intraday as a funded decision, not a build item.**
2. **History must be adjusted.** Raw bhavcopy prices jump on splits and bonuses, which makes charts and indicators wrong. Long history needs adjustment from corporate actions (the paper app already detects them).
3. **File ceiling.** The main site cannot add files. Five years per stock as one JSON per stock is about 90 KB each as plain JSON, 2,619 stocks [estimate], so use a compact columnar format inside the existing file count.
4. **Database size.** Supabase Free is 500 MB (19 MB used). Nifty 500 times 5 years is about 625,000 rows, roughly 60 MB [estimate]: fine. All 2,619 stocks times 5 years is about 3.3 million rows, about 200 MB [estimate]: not for the free plan.
5. **Practice-market rule.** In the paper app every chart must stop at the practice date (30 days behind). The shared engine takes data through an adapter that enforces the cap; it never fetches "latest" itself.
6. **Origins and CSP.** Scripts load only from their own origin. The engine is built once and copied into each site as static files; no cross-origin loading.
7. **Compliance for AI.** "Bullish signal" labels and screeners can read as research recommendations. Needs counsel before launch, labelled educational, explainable and never phrased as advice.

---

## 4. Target architecture

**`charting/` package in the repo** (TypeScript, built with esbuild, no framework):

```
core/        data model (Bar, Series), resampling (D/W/M), adjustments, time utilities
indicators/  pure functions, each with tests against known reference values
drawings/    object model, hit-testing, editing, undo/redo, serialization (versioned JSON)
render/      Lightweight Charts adapter (series, panes, price lines, primitives)
ui/          toolbar, indicator panel, drawing palette (small, accessible, themeable)
adapters/    data sources: static JSON (main site), API (paper app), cap-at-practice-date
```

- **Output:** a few small static files (core about 25 KB gzip target, each indicator group a lazy chunk of at most 10 KB), copied to `site/assets/js/charting/` and `virtual-trading/public/charting/`. The paper app loads them in the browser only, on demand, so the worker is unchanged.
- **Renderer decision:** keep Lightweight Charts (62 KB gzip, Apache-2.0, supports panes, custom series and drawing "primitives"). Build the drawing layer ourselves. In parallel, apply for TradingView's Advanced Charts library, which already has a full drawing and indicator toolkit but is licensed by application with its own terms [unverified]; if approved it could replace Phases 2 and 3 for the cost of its conditions and size.
- **Heavy work in a Web Worker:** indicators over 5 years of data run off the main thread.
- **Persistence:** guests use `localStorage` (versioned). Signed-in users (paper app only) get tables `chart_layouts`, `chart_templates`, `chart_drawings`, `price_alerts`, per account, capped, covered by the existing database lockdown. The main site has no accounts, so its charts stay local-first with JSON export, import and a "continue in the app" hand-off.
- **Accessibility:** a chart is a canvas, so every chart ships a text summary and a data table toggle.

---

## 5. Phased roadmap

Effort is in focused engineering weeks, assuming one builder with me [estimate; sequential, not a commitment].

| Phase | Scope | Effort | Depends on | Success metric |
|---|---|---|---|---|
| **0. Foundations** | 5-year adjusted daily history for the Nifty 500 and the 9 indices, fetched from your Mac, stored in Postgres and exported compactly for the site. Advanced Charts licence enquiry. Written spec | 2 | NSE archive reachable from the Mac | History present for 95% or more of the Nifty 500; adjustment verified on 10 known splits and bonuses |
| **1. Unified engine v1** | Extract `stock-chart.js` into `charting/`; tests for existing indicators; chart types: candles, hollow candles, Heikin-Ashi, bars, line, area, baseline; timeframes D, W, M; paper app trade screen uses it (lazy-loaded); main site migrated with no regression | 3 | Phase 0 | Chart loads under 1 s after interaction; no worker size change; zero regressions in the main-site QA suite; stock-page LCP unchanged |
| **2. Indicators and compare** | Full library: WMA, VWAP (anchored, daily approximation, labelled), MACD, Stochastic, CCI, ROC, ATR, Keltner, Supertrend, ADX, Parabolic SAR, Ichimoku, OBV, MFI, volume profile (daily approximation), pivots; parameter editor; saved indicator sets; compare mode (%, indexed, relative); 2 and 4 chart layouts | 4 | Phase 1 | Each indicator matches reference values within tolerance; over 30% of chart users add an indicator |
| **3. Drawing toolkit** | Trendline, horizontal, vertical, ray, rectangle, arrow, text, parallel channel, pitchfork, Fibonacci retracement and extension, measure, risk/reward; edit, move, delete, undo and redo; local persistence | 5 | Phase 1 | Drawings survive reload; touch and mouse both work; under 1% drawing errors in logs |
| **4. Accounts and workspace** | Saved layouts and templates and drawings for signed-in users, across devices; watchlist beside the chart; price alerts evaluated at the daily sync (in-app, end-of-day: alerts here are not live) | 4 | Phases 2 and 3 | Over 25% of signed-in chart users save a layout; alert evaluation exact against test cases |
| **5. Paper-trading integration** | Order from the chart (click a price to prefill a limit or stop order); entry, stop and target lines tied to the order ticket; open orders and positions with P&L drawn on the chart; backtester v1 on daily data (rule-based strategies, with clear overfitting warnings) | 5 | Phases 3 and 4 | Share of orders placed from charts; backtests reproduce a hand-computed example exactly |
| **6. Chart intelligence** | Deterministic, explainable summaries from indicator values (no model, no cost); daily indicator snapshot table; natural-language screener (a small grammar first, a model only to translate text into that grammar); pattern detection v1 (a short list, each with stated uncertainty) | 6 | Phase 2; counsel on AI signals | Every insight links to the numbers behind it; zero advice wording (checked by test) |
| **7. More asset classes and intraday** | Index futures and options, stock F&O, commodities and currencies as their data arrives (follows the F&O roadmap); intraday only if licensed data is approved | open | Segment roadmap; vendor decision | Per segment |

**Total through Phase 6:** about 29 weeks [estimate]. Usable value arrives earlier: Phase 1 puts a real chart in the app, and Phases 2 and 3 are the competitive step.

---

## 6. Benchmarks (general knowledge, not a live audit [unverified])
- **TradingView:** the standard for drawings, indicators, layouts, alerts and community; strong intraday data. Our edge cannot be breadth.
- **Kite and Groww:** charts tied to order entry and real positions, with live data (which we deliberately do not have).
- **Our differentiation:** charts connected to broker-accurate costs and a safe practice market, with explainable analysis for learners, not a copy of a trading terminal. Phase 5 (chart-to-order with real fee schedules) and Phase 6 (explanations, with the numbers shown) are where this is distinctive.

## 7. Risks
| Risk | Mitigation |
|---|---|
| No intraday data, so the stated timeframes cannot all ship | Say so; Daily, Weekly, Monthly first; funded decision for intraday |
| Wrong charts from unadjusted splits and bonuses | Phase 0 adjustment tests before anything ships |
| Bundle growth, hurting page speed or the worker | Lazy chunks, size budgets in CI, load on interaction only |
| Canvas drawing tools on phones | Touch-first interaction design and a phone test pass per phase |
| AI wording becomes a recommendation | Deterministic first, wording tests, counsel review |
| Scope: this is a product, not a feature | Phase gates with metrics; stop or reprioritise at each |

## 8. Decisions needed from you
1. **Approve Phase 0 and Phase 1** (data foundation, then the engine with the paper app trade-screen chart). 
2. **Intraday:** park it for now, or open a vendor and legal enquiry?
3. **Advanced Charts licence:** apply in parallel as a possible shortcut? (Free to apply; terms unknown until we do.)
4. **AI signals:** ask counsel before Phase 6, as suggested above?
