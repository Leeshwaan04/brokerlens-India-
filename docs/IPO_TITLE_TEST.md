# IPO title and meta A/B test

Scope: every static IPO page at `/ipo/<slug>/` (about 1,250 pages). Code: `pipeline/ipo_facts.py`
(`title_group`, `build_title`, `build_description`).

## Why

Search Console (90 days to 17 Oct 2026): the `/ipo/*` family has 25,464 impressions and 27 clicks
(0.11 percent CTR). Searchers want price, date and listing facts for past issues. The old titles led
with "Latest Close, % since issue", which reads as a performance claim and answers none of those
queries.

## Split rule

```
group = "A" if zlib.crc32(slug.lower().encode("utf-8")) % 2 == 0 else "B"
```

`slug` is the lower-case symbol, the same string as in the URL (`kfintech` for
`/ipo/kfintech/`). CRC32 is deterministic across builds, machines and Python versions, so a page never
switches group. The built-in `hash` function is randomised per process and is never used.

The split is by slug parity, not matched on prior impressions (the page list and impressions change
every build). Over 1,254 real records the groups are 50 percent each, so the two groups are comparable
in size; compare CTR, not raw clicks, and check the impressions of each group before trusting a gap.

| Group | Title pattern |
|---|---|
| A | `{Name} IPO: Price Band Rs {lo} to {hi}, Dates {open} to {close}, Listing {date} \| BrokerLens` |
| B | `{Name} IPO Date, Price Band, Lot Size and Listing Date \| BrokerLens` |

Rules that apply to both:

- `{Name}` is the company name without a trailing "Limited" or "Ltd".
- Group A uses "Issue price Rs {x}" when only one price is on file (a fixed-price issue), and omits any
  part that is not on file (no price, no dates, no listing date).
- When the key part (before `| BrokerLens`) passes 100 characters, group A drops parts from the right:
  the bidding dates first for a listed IPO (the listing date is what people search), the listing date
  first for any other status.
- Group B drops "Lot Size" from the wording unless a sourced `lot_size` is on the record. None is on
  file today, so group B reads "IPO Date, Price Band and Listing Date".
- Dates read "19 to 21 Dec 2022". There are no dashes anywhere.
- Both groups share one meta description built only from fields on file, for example:
  `KFin Technologies IPO opened 19 Dec 2022 and closed 21 Dec 2022, listed 29 Dec 2022 on NSE. Issue price Rs 366 (price band Rs 347 to 366). Status: Listed.`
- The latest-close figure and any percent change are never in the title or meta. They stay in the page
  body, labelled with the close date.

## How to read it in Search Console

1. Open Search Console, Performance, Search results. Set the date range to 28 days after the deploy
   has been recrawled (compare against the 28 days before).
2. Add a filter: Page, "URL matches regex" (custom regex). Group membership is not guessable from the
   URL, so build the two regexes from the slug lists:

   ```
   python3 - <<'EOF'
   import json, zlib
   d = json.load(open("data/_ingest.json"))["nse"]["ipo"]
   slugs = sorted({r["symbol"].lower() for k in ("current", "upcoming", "past") for r in d[k]})
   for g in (0, 1):
       s = [x for x in slugs if zlib.crc32(x.encode()) % 2 == g]
       print("A" if g == 0 else "B", "https://www.brokerlens.in/ipo/(" + "|".join(s) + ")/$")
   EOF
   ```

   Search Console regex filters are RE2 and have a length limit, so split each list into chunks of
   about 150 slugs and add the chunks together in a spreadsheet, or export Pages to a sheet and
   classify each URL by the same crc32 rule.
3. For each group read Clicks, Impressions, CTR and Position. Do it with the "Pages" tab and the
   "Queries" tab (queries containing "price", "date", "listing").
4. Do not read results before 14 days: titles are recrawled slowly on a new domain. At day 14 run URL
   Inspection on about 10 URLs per group to confirm the new title is the indexed one.

## Success rule

- Group B CTR above 0.3 percent (about three times the 0.11 percent baseline), or group A at least 50
  percent higher than group B, over 28 days with similar average position (within about 1.5).
- If the groups differ by less than the noise (daily clicks are low, 28 to 69 site-wide), keep the
  split running for another 28 days before choosing.
- Roll the winning pattern to all IPO pages by returning it from `title_group` for every slug.

## Do not change during the test window

Position-affecting changes (new sections, internal links) ship in a second wave, so a CTR change can be
attributed to the snippet. The facts card, GMP section and noindex of listed-IPO sub-pages ship with the
titles in this release; note the deploy date, and treat the first 14 days as a settling period.

## Related changes shipped with this test

- Sub-pages (`basis-of-allotment`, `subscription-status`) of listed IPOs are canonical to the main IPO
  page, `noindex,follow`, and left out of the sitemap. Open and upcoming IPOs keep indexable sub-pages.
- Lot size is shown only when a sourced `lot_size` is on the record (none today); the estimate is gone.
- IPO page FAQs and FAQPage JSON-LD depend on status. A listed IPO never says it has not listed.
