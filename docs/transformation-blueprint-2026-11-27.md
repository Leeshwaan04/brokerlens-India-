# BrokerLens transformation blueprint (27 Nov 2026)

Written for: the owner of BrokerLens, as a decision document.

**How to read this.** Every figure is tagged. **[measured]** comes from Search Console, the repo, the live apps or the database as of 26 to 27 Nov 2026. **[estimate]** is my reasoned projection. **[unverified]** is a claim I could not check from here. This is an evidence-based audit of the data, the code and the two live products. It is not a page-by-page crawl of 16,879 pages, and it says where that limit matters.

---

## 1. The verdict

1. **The data asset is real, the audience is not yet.** BrokerLens holds verified fee schedules for 30 brokers, SEBI registry data, IPO history and calculators, and now a working practice-trading product. It earns about 37 Google clicks a day [measured: 1,034 clicks, 102,849 impressions, 28 days to 23 Nov].
2. **The traffic is concentrated and fragile.** 299 of the 343 clicks in the top 250 queries (87%) are "share price target" queries on stock pages [measured]. That is the one query family we deliberately stopped serving numbers for, because publishing target prices is SEBI research-analyst territory. The brand query "brokerlens" has 8 impressions in 28 days [measured]: almost nobody searches for us by name.
3. **Google is not yet trusting the site.** Impressions collapsed site-wide three times in 24 days (2 to 3 Nov, 12 to 14 Nov, 24 to 26 Nov), each lasting up to about 36 hours, with pages indexable and no deploy or manual action [measured]. The index holds about 46K pages against about 6.2K submitted, with 28.6K noindexed [measured]. That is the signature of a site Google treats as templated scale.
4. **The revenue model depends on traffic that does not exist.** Display ads plus sponsored banners plus broker referrals, on roughly 1,000 clicks a month, is worth very little. Referral codes exist for only 4 of 30 brokers [measured, from the affiliate audit].
5. **The strategic bet:** stop adding pages and become the place that answers one question better than anyone: **"what will investing actually cost me, and which broker is cheapest for how I trade?"**, then let the practice app prove it with the user's own trades. That is defensible, monetisable through referrals, safe under SEBI, and hard to copy because it needs the fee data we already hold.

**What I would not do:** chase 10 million visitors a day. That is the scale of India's largest finance portals, built over many years with newsrooms [reasoned]. The goal of 10K clicks a day is reachable in 12 to 18 months only if the moat below works. Anything faster means doorway pages, which is exactly what is putting the site's trust at risk now.

---

## 2. What the evidence says, by area

### 2.1 Product and UX (CPO, CDO)
| Finding | Evidence | Recommendation |
|---|---|---|
| Two products with no bridge. The main site is a reference; the practice app is a tool. Nothing links them. | Guide page is live; app has no inbound links by design (footer link removed). | One journey: stock page, "What does trading this cost at each broker", "Practise it" (deep link works for new visitors, shipped 27 Nov). |
| The site optimises for pages, not decisions. 16,879 HTML pages, 7,290 in sitemaps. | 26 Nov census (other agent) [measured]. | Organise navigation around five decisions: choose a broker, understand costs, practise, follow an IPO, research a company. |
| Heavy decorative layer (hero video, theme audio, footer film). | Files in `site/assets/js` [measured]; effect on Core Web Vitals [unverified]. | Remove audio entirely (copyright and trust risk, no user value). Gate video behind interaction. Measure LCP and INP before and after. |
| Client-rendered "not published yet" cards produced a soft 404 on Zerodha's profile. | Search Console, 10 Nov [measured]. | Never ship a profile with placeholders. Server-render real data or hide the card. |
| The app has gaps a first-time user feels: no onboarding tour, no explanation of why an order filled, circuit limits not enforced. | Code review. | Why-did-this-fill explainer, charges meter, missions. |

### 2.2 Technology and architecture (CTO)
| Area | State | Risk or action |
|---|---|---|
| Main site | Python pipeline of 28K lines in 31 modules, static HTML, Cloudflare Workers Assets, 14 workflows. | Strength: cheap, fast, safe. Risk: the file ceiling is 20,000 assets and the site holds 19,655 [measured]. Every new page family needs a removal first. |
| Deploys | No local tree matches live; routine fresh builds deploy. I broke production for minutes on 27 Nov by deploying from the wrong folder. | Make deployment one audited workflow (build in CI, compare against live, deploy with a rollback id logged). Remove the manual path. |
| Practice app | Next.js on Workers Free, Supabase through Hyperdrive, Clerk, 2.40 MB of a 3 MB limit. | Free-plan ceilings: 10 ms CPU, 3 MB, 100K requests a day. Upgrade to the $5 plan the first time traffic needs it. |
| Data supply | NSE refuses GitHub's runners; prices come from a launchd job on one Mac. | Single point of failure. Run a second fetcher (a cheap always-on host), and keep the existing 10-day runway alert. |
| Security | Independent review: no critical or high findings; CSP, CSRF guards, webhook verification, Supabase API closed. | Re-test after each major feature; schedule a yearly external test. |
| Observability | Uptime and price-runway monitor every 30 minutes; encrypted nightly backups, restore tested. | Add error-rate alerts and a public status page. |
| Technical debt | Two stacks (Python static and Next.js); a bot committing generated `site/` files to `main` makes every push a 11-minute rebuild. | Stop committing generated output; build in CI only. Biggest developer-speed win available. |

### 2.3 SEO and organic growth (CMO, CGO)
| Finding | Evidence | Recommendation |
|---|---|---|
| Quality flapping. Three 36-hour collapses and a core update window. | Search Console [measured]. | Treat as a trust problem, not a bug. Reduce indexable templated pages; raise the average page's usefulness. |
| 46K indexed vs 6.2K submitted. | Search Console Pages report [measured]. | Keep removing indexable duplicates (trade pages noindexed 4 Nov; city branch pages 1,709 noindexed). Audit what else is indexed outside the sitemap monthly. |
| One query family carries the site. | 87% of top-query clicks [measured]. | Replace it with intent we can serve well: "[broker] charges", "[stock] brokerage calculator", "[broker] vs [broker]", "IPO allotment status". |
| Average position is 25.9, CTR 1.01%. | [measured] | Page-two content earns nothing. Pick 50 pages and make each the best answer on the web rather than improving 5,000. |
| Entity and trust signals. | Editorial policy and methodology pages exist; authorship and sourcing on each page [unverified at scale]. | A named editorial owner, a visible "data as of" stamp and source on every number. This is the single strongest answer to Google's quality systems for finance (YMYL). |
| Programmatic risk. Doorway-style combinations get demoted site-wide. | Past incident: a sitemap allowlist noindexed about 3,200 pages with real demand, later fixed. | Every new page family needs a human-checked sample, a unique-value test and a kill criterion before it ships. |

### 2.4 Business and monetisation (CEO, CBO, CFO)
| Stream | State | Reality check | Action |
|---|---|---|---|
| Broker referrals | Live links; 4 of 30 brokers have codes. | The main revenue line for a comparison site, paid per funded account. | Sign up to the programmes of the 10 brokers we send the most clicks to; rank by payout times conversion, not by payout alone. |
| Display ads | AdSense publisher id in `ads.txt`. | At about 37 clicks a day this earns a few rupees a day [estimate]. | Keep, do not optimise; it also adds page weight. |
| Sponsored banners | Live, labelled. | Needs traffic. | Sell the data instead: one sponsor per month on the cost-comparison tool, labelled, never affecting rank. |
| BrokerLens Plus (practice app) | Built, test mode; Rs 99 for 30 days or Rs 799 a year. | Worth buying only with features beyond a CSV. | Do not take real money until alerts, multiple portfolios and rewind mode exist, and the entity, GST and refund terms are ready. |
| B2B licensing | Not started. | Potentially the highest-value line: broker-fee data and the practice market licensed to brokers and learning companies. | Package a data sheet and a white-label demo; first target 3 conversations, not 30. |
| Costs | About Rs 0 a month infrastructure (free plans). | Founder time is the cost. | Do not spend on tools until the first referral cheque arrives. |

### 2.5 Competitive benchmark (from general knowledge, not a live audit [unverified])
| Competitor type | Their advantage | Our opening |
|---|---|---|
| Brokers' own education (Zerodha Varsity) | Trusted long-form teaching, brand. | They cannot compare themselves honestly. We can. |
| Research and screeners (Screener, Tickertape, Moneycontrol) | Deep company data, years of authority. | Do not fight on company data volume. Own the cost layer they ignore. |
| Comparison sites (broker review and finance marketplaces) | Large traffic, strong monetisation. | Their rankings tend to follow payouts; ours are sorted by cost alone and say so. That is our brand promise. |
| Paper-trading tools (Zerodha demo, TradingView, others) | Many refuse live Indian prices or are generic. | Our 30-day-delayed, broker-fee-accurate practice market is a legal and product differentiator. |
| Global peers (NerdWallet-style) | A single trusted brand per decision. | The model to copy: fewer pages, each a definitive answer, funded by referrals. |

### 2.6 AI and automation (CTO, CPO)
Use AI where it removes cost or adds personal value, never to mass-produce pages.
- **Explain my trade** after settlement, in plain English and Hindi (high value, low risk, runs on rules first).
- **Fee-change monitor:** detect broker fee-page changes and propose the diff for human approval (protects data accuracy, our moat).
- **Support and FAQ drafting** from the methodology, answers shown with their sources.
- **Anomaly alerts** on the data pipelines (IPO field renames silently removed about 490 pages in November; a check would have caught it in a day).
- **Do not:** generate stock commentary, price targets or "buy/sell" language; that is advice and the single biggest legal risk.

---

## 3. Challenged assumptions
1. *"More pages means more traffic."* The evidence says the opposite here: 46K indexed pages produced about 37 clicks a day, and removing pages coincided with recoveries.
2. *"We need to rank for share price targets."* We cannot serve those numbers legitimately, and 87% of our clicks depend on them. Replace, do not defend.
3. *"A leaderboard will drive engagement."* Ranking users by returns invites SEBI scrutiny and encourages risk-taking; process badges and learning streaks give the retention without the exposure.
4. *"Display ads are a revenue line."* At this traffic they are decoration. Referral and licensing are the lines.
5. *"Free for ever."* The free plans are fine for launch and wrong as a plan; budget for the $5 plan and a proper database as soon as signed-in traffic appears.
6. *"We should cover every asset class."* Stocks, then F&O, then commodities is the right order; funds and ETFs wait for traction (your own decision, 26 Nov).

---

## 4. Prioritised initiatives (impact, effort, cost)
Scale: impact 1 to 5, effort in engineer-weeks.

| # | Initiative | Impact | Effort | Cost | Why now |
|---|---|---|---|---|---|
| 1 | Bridge the products: "Practise this" on stock and broker pages, cost-per-broker module, deep links | 5 | 2 | Rs 0 | Turns existing traffic into the only monetisable action |
| 2 | Consolidate the index: cut indexable templated pages, strengthen the top 50 | 5 | 3 | Rs 0 | Addresses the quality flapping directly |
| 3 | Referral programme sign-ups for the top 10 brokers | 5 | 1 | Rs 0 | No revenue without codes |
| 4 | Replace the "price target" dependency with broker and calculator intent pages | 4 | 4 | Rs 0 | Removes 87% concentration risk |
| 5 | Build CI-only site builds; stop committing generated files | 4 | 2 | Rs 0 | Faster, safer shipping |
| 6 | Single audited deploy workflow with logged rollback | 4 | 1 | Rs 0 | Prevents a repeat of the 27 Nov mistake |
| 7 | App learning layer: why-did-this-fill, charges meter, missions | 4 | 3 | Rs 0 | Retention and shareable proof |
| 8 | Remove audio and defer video; measure Core Web Vitals | 3 | 1 | Rs 0 | Trust and speed |
| 9 | Second price-data fetcher | 3 | 1 | about Rs 400 a month [estimate] | Removes the single point of failure |
| 10 | F&O practice (index futures and options, then stock) | 5 | 8 to 10 | Rs 0 to $5 | Largest retail segment; main product differentiator |
| 11 | B2B data sheet and white-label demo | 4 | 2 | Rs 0 | Highest-value line |
| 12 | Plus features (alerts, portfolios, rewind) then payments | 3 | 6 | 2% payment fees | Only after the entity and GST are ready |

---

## 5. Roadmap with KPIs

### 0 to 30 days: fix trust, connect the products
| Deliverable | Owner | KPI and target | Depends on |
|---|---|---|---|
| Practise buttons and cost module on top 200 stock and all broker pages | CPO + CTO | Click-through to the app above 2% of those pages' sessions; app sign-ups per week measured | QA run, routine deploy |
| Referral codes for 10 more brokers | CBO | Codes on 14 of 30 brokers; first tracked account opening | Owner signs agreements |
| Index consolidation plan and first cut | CMO | Indexed-but-not-submitted pages down 30%; zero new collapses in 30 days | Search Console access |
| Single audited deploy; CI-only builds | CTO | No manual production deploys; push-to-live time under 15 minutes | Workflow time |
| Legal sign-off on the 30-day rule | CEO | Written counsel opinion | Counsel |
| Remove audio; Core Web Vitals baseline | CDO | LCP under 2.5 s on mobile for the 20 top pages | None |

### 30 to 90 days: build the moat
| Deliverable | Owner | KPI and target | Depends on |
|---|---|---|---|
| Broker and calculator intent pages replace the price-target dependency | CMO | Clicks from non-target queries above 50% of total | Content plan, editor |
| App learning layer (explainer, charges meter, missions) | CPO | Week-4 retention of signed-up users above 20% [estimate for the segment] | Engineering |
| F&O phase 1: index futures and option buying, 30-day delayed | CTO | Feature shipped with settlement tests; no margin invented | NSE F&O file fetch from the Mac |
| Second price fetcher and error alerts | CTO | Price runway never under 10 days | Small hosting spend |
| B2B data sheet; 3 conversations | CBO | 1 pilot discussion | Sales effort |

### 3 to 6 months: monetise
| Deliverable | Owner | KPI and target | Depends on |
|---|---|---|---|
| Plus features and live payments | CBO + CFO | 1.5 to 3% of active practisers buy [estimate] | Entity, GST, refund terms |
| F&O phase 2: option selling with margin from the clearing corporation's files | CTO | Margin matches the published parameters on a test set | Data source check |
| Commodity feasibility (MCX or NSE commodity files fetchable plainly?) | CTO | Decision memo | None; stop if blocked |
| Classrooms for colleges | CGO | 3 institutions piloting | Product |

### 6 to 12 months: scale the position
| Deliverable | Owner | KPI and target | Depends on |
|---|---|---|---|
| Hindi, then Marathi and Gujarati | CMO | Regional traffic share above 10% [estimate] | Native review of money terms |
| White-label licence for a broker or learning company | CBO | One signed licence | Pilot result |
| ETFs, mutual funds, SIPs | CPO | Unparked only if the practice app is above its traction threshold | Traction |
| Re-evaluate the site's size ceiling and move the main site to a dynamic stack if needed | CTO | Decision memo | Roadmap results |

### North-star and guardrails
- **North star:** monthly active practisers who then open a funded broker account through a tracked link. Everything else is a leading indicator.
- **Leading indicators:** sessions from broker and calculator pages to the app; activation (first order in 24 hours); week-4 retention; referral clicks per active user.
- **Guardrails:** no invented numbers; no advice; no live prices (30-day rule); no leaderboard by returns; indexable pages never grow faster than their average usefulness; Search Console clicks reported weekly, not daily.
- **Realistic ranges [estimate]:** 12 months, if initiatives 1 to 4 work: 1,000 to 3,000 clicks a day. 10,000 a day is an 18 to 36 month outcome and depends on earning brand searches, which today are close to zero.

---

## 6. Risks
| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Google quality systems keep suppressing the templated pages | High | High | Initiative 2 and 4 |
| SEBI rule on the 30-day lag reads against us | Medium | High | Counsel sign-off before scaling traffic to the app |
| Single-machine data supply fails | Medium | Medium | Second fetcher, runway alert |
| Free-plan limits hit as the app grows | Medium | Medium | Budget for the $5 plan; no code change needed |
| Production mistake like 27 Nov | Medium | High | Initiative 6 |
| Referral programmes pay less than modelled | Medium | Medium | Measure per broker; B2B as the second line |

## 7. What I could not verify
- Per-page content quality across the 16,879 pages (the census was by another agent; I sampled only through Search Console and the repo).
- Core Web Vitals, accessibility scores and real mobile behaviour: no Lighthouse or field data was pulled.
- Competitor traffic, pricing and feature details: general knowledge, not live research.
- Revenue to date: no ad, banner or referral earnings data was available to me.
- A number of the checklist items in the other agent's 100-point list (for example the STT rates, the audio-copyright claim, and the lead paragraph structure) are plausible but unchecked.

## 8. The first five actions (this week)
1. Sign the referral agreements for the top 10 brokers by click volume.
2. Ask counsel for the 30-day-rule opinion.
3. Approve the index-consolidation approach (cut before add).
4. Approve "Practise this" on stock and broker pages (I build it, QA, routine deploy).
5. Copy the backup private key into your password manager and rotate the two exposed secrets.
