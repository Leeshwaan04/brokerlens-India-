# BrokerLens India: what to build next

**Date:** 2026-08-01

Three constraints shape every idea here, and they are features, not limitations:

1. **No paid placement, no lead selling.** Removed deliberately. Anything that
   needs a broker's cooperation to exist is fragile and pulls the product back
   toward selling access to the firms it rates.
2. **No personal data.** All collection was removed, which eliminated the DPDP
   Act surface entirely. Nothing below reintroduces a form, a login, or a
   tracker.
3. **No advice.** The site publishes facts and disclosed arithmetic. It names no
   "best broker". The moment a page recommends, SEBI's investment-adviser and
   research-analyst regimes apply.

**The strategic point:** the moat is not the comparison table, which anyone can
copy. It is that everything is assembled from *regulator primary sources*.
Features built on regulatory data nobody else structures are defensible and need
no broker's permission. That is also what makes them work for **all** brokers,
not just the 48 with rich profiles.

---

## The coverage problem, stated plainly

| Population | Count | What they get today |
|---|---|---|
| Brokers profiled in depth | 48 | Full profile, charts, rankings, comparison |
| Other SEBI-registered entities | 1,685 | One row in a table |
| Defaulter / expelled records held | 445 | A boolean flag, nothing more |

So "does this apply to all brokers?" is today: **no, it applies to 2.8% of them.**
Items A1, A2 and B6 below are specifically the ones that close that gap, and
they close it without any broker's involvement because the data is the
regulator's, not the broker's.

---

## Tier A: complete the regulatory record

The highest-value work, and the hardest for anyone to copy.

### A1. Registration lifecycle and validity monitor
**Coverage: all 1,733 registered entities. Data: already ingested, unused.**

We already hold a `validity` field for **831 of 831** commodity-broking entities
plus every CDSL and NSDL depository-participant registration, and we publish
none of it beyond a raw string in one table cell.

Surface it as the fact it is: registered since when, perpetual or expiring,
which segments the licence actually covers, and which legal entity holds it. A
registration that has lapsed, or that covers commodities but not equity, is the
single most consequential thing a customer can know about a broker, and no
comparison site in India presents it clearly.

Pairs with a real gap we documented: the site currently verifies brokers through
SEBI's *commodity* register because the stock-broker register returns nothing.
That nuance belongs on the page, not in a code comment.

### A2. The defaulter and expelled archive
**Coverage: all 445 records held. Data: already ingested, used only as a flag.**

Today these 445 records produce a single boolean on 48 profiles. They deserve to
be a first-class, searchable resource: which firms were declared defaulters or
expelled, by which exchange, under which registration number.

Then add the part nobody writes neutrally: **what actually happens to your money
and your shares when a broker fails.** The Investor Protection Fund, the
exchange arbitration route, how holdings in your own demat account differ from
funds lying with the broker, realistic timelines. This is a genuine public
service, it is entirely factual, and it is the most emotionally urgent question
in the category.

### A3. SEBI enforcement actions and adjudication orders
**Coverage: all entities. Data: not yet ingested. Highest untapped source.**

SEBI publishes adjudication orders, settlement orders and enforcement actions,
per entity, as public records. This is the richest regulatory dataset we are not
touching. Structured per broker and per registration number it becomes the
factual backbone of the whole product.

Handle with the discipline we just built into the pipeline: exact-match or
registration-number attribution only, never fuzzy. An enforcement order attached
to the wrong firm is a defamation exposure.

### A4. Annexure-B complaint crawler
**Coverage: all registered brokers eventually; start with the top 50. Known gap.**

Every registered broker must publish monthly received/resolved/pending complaint
figures on its own website in SEBI's Annexure-B format, usually as a PDF. This
is real, free, mandated, public data. It needs a per-broker crawler and a PDF
table parser: genuine work, entirely doable, and the single highest-value thing
to build. It also retires the biggest sample-data caveat on the site.

The metrics engine is now ready for it: windows are enforced, rates only publish
over a complete 12 months, and non-disclosure is distinguishable from zero.

### A5. NSE member-wise UCC active clients
**Coverage: all NSE trading members. Known gap.**

The other headline metric currently on sample data. NSE publishes member-wise
active-client counts monthly, just not at a stable machine-readable URL. Pin the
file location or license it. Until then, the honest move is to keep the banner.

---

## Tier B: the long tail becomes the product

### B6. A real page for every SEBI-registered entity
**Coverage: 1,685 entities that today get one table row.**

Every one of them already has: legal name, registration number, validity,
exchange memberships, categories, city, and DP status. That is enough for a
genuine page, without a single line of curation.

Two payoffs. First, utility: someone handed a broker's name by a relative or a
Telegram group can look it up and see whether it is real, current and licensed
for what it claims. Second, reach: 1,685 pages of unique regulator-sourced
content aimed at "is X registered", which is exactly what people search when
they are about to hand over money.

This is the answer to "does it work for all brokers": it is how 48 becomes 1,733.

### B7. "Verify a broker" tool
**Coverage: every registered entity.**

One input, one answer. Paste a firm name, a registration number, or an app name:
is it SEBI-registered, is the registration current, which segments does it
cover, is it on the defaulter list, which legal entity is behind the brand.

This is the highest-frequency, highest-stakes question in the category, it is
pure fact, and it is a fraud-prevention utility. It needs no personal data and
no broker's cooperation. It is also the most natural thing for a journalist or a
regulator to link to.

---

## Tier C: cost and mechanics, told truthfully

### C8. True all-in cost, including statutory charges
**Coverage: every broker with published charges.**

The calculator deliberately excludes STT, stamp duty, exchange transaction
charges, SEBI turnover fees and GST, on the sound reasoning that they are
identical across brokers. But a retail investor does not want to know the
*comparable* cost, they want to know **what leaves their account**. These
charges are formulaic and public.

Publish both: "broker charges" for comparison, "total cost of this trade" for
reality, with the split shown. Nobody does the second one honestly.

### C9. Charge change history
**Coverage: every broker whose charges page we can read. Nobody does this.**

Snapshot each broker's published charges over time and publish the diffs:
"Broker X introduced an AMC on this date", "Broker Y raised F&O brokerage from
₹20 to ₹25". Brokers quietly change pricing and customers discover it in a
statement. A dated, sourced, factual change log is enormously trust-building,
costs nothing to maintain once built, and is the kind of thing people cite.

### C10. How to leave a broker
**Coverage: universal.**

Account closure, demat transfer between CDSL and NSDL participants, what happens
to unsettled positions, what a broker may and may not charge you to leave. Every
broker writes the joining guide; nobody writes the leaving guide.

---

## Tier D: market reference (universal, cheap, compounding)

Already shipped: market timings across NSE, BSE and MCX by segment.

- **D11. Trading holiday calendar**, machine-readable per exchange. It completes
  the timings feature, and it fixes a real pipeline blind spot: archive fetchers
  currently walk backwards past holidays blindly, and the "currently open"
  highlight can be wrong on a holiday.
- **D12. Corporate actions calendar.** We already ingest 40 BSE records every
  run and display none of them. Ex-dates, record dates, purposes.
- **D13. Settlement and margin reference.** T+1 mechanics, peak margin norms,
  pledge and re-pledge, what "delivery" actually means operationally.
- **D14. Investor grievance pathway.** SCORES, the SEBI ODR portal, exchange
  arbitration: who to approach, in what order, within what time limits.

---

## What we should deliberately NOT build

Worth writing down, because each is individually tempting.

| Not building | Why |
|---|---|
| "Best broker" verdicts or star ratings | Triggers SEBI's investment-adviser and research-analyst regimes. Rankings must stay sorted-by-a-stated-metric. |
| User reviews and ratings | Unverifiable, trivially gamed by brokers, and a defamation surface. It would also undermine the one thing that makes this site different: everything is checkable against a regulator. |
| Returns, tips, model portfolios, "which stock" | Straight into advice. |
| Affiliate or referral links | Reintroduces exactly the incentive we removed, and silently changes the meaning of every ranking. |
| Portfolio tracking, account linking, logins | Reintroduces personal data and the entire DPDP obligation set we just eliminated. |
| Realtime price redistribution | Licensed activity. Settle NSE/BSE/MCX terms before monetising anything derived from it. |
| Scraping Chittorgarh and other aggregators | Their compiled tables are their work product. Primary sources only, both legally and because it is the whole proposition. |

---

## Suggested order

**Now (unblocks the sample-data caveat):** A4 Annexure-B crawler, then A5 UCC.
These retire the two banners and make every existing ranking real.

**Next (cheap, high leverage, already have the data):** A1 validity lifecycle,
A2 defaulter archive, B6 the 1,685 entity pages, B7 verify-a-broker. All four
are built on data already sitting in `data/_ingest.json`, and together they take
coverage from 48 brokers to the whole registered market.

**Then (differentiation):** A3 enforcement orders, C9 charge history. These are
the two nobody else will have.

**Ongoing (cheap reference content):** D11 to D14.

**Before any public launch, regardless of features:** settle the exchange data
licensing position, and finish the remaining items in `GAP_ANALYSIS.md` §5.
