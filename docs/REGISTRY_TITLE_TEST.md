# Registry page title test (area: registry)

Applies to every `/sebi-registry/<slug>/` page. Code: `pipeline/registry_entity.py`
(`title_group`, `make_title`, `make_description`), wired from `_write_registry_pages`
in `pipeline/publish.py`.

## The split

```
group = "AB"[zlib.crc32(slug.encode("utf-8")) % 2]     # 0 = A, 1 = B
```

`slug` is the page's own URL slug. `zlib.crc32` is stable across runs and Python
versions (the built-in `hash()` is randomised per process and must never be used).
Group membership is therefore permanent for a URL. Changing a slug moves it between groups.

| Group | Title pattern |
|---|---|
| A | `{Name}: SEBI Registration No. {number}, Validity and Exchanges \| BrokerLens` (shortened, see below) |
| B | `Is {Name} SEBI Registered? Registration No. {number} ({category})` (shortened, see below) |

The word "Segments" is no longer used: the register list holds exchange names and a validity
string only, so the page cannot promise segments.

### Length budget (shortening ladder)

Search results show about 60 characters, so the registration number must sit inside the first
60 characters and the whole title within about 70 (code: 72, `_TITLE_MAX`, `_TITLE_REG_BY = 60`).
`make_title` walks a ladder and takes the first rung that fits both limits; the ladder only ever
drops words, never the number:

* A: full name plus brand, then full name without ` | BrokerLens`, then the short name (legal
  suffix Private Limited / Pvt. Ltd. / Limited / Ltd. removed) with the tail, then
  `{Short}: SEBI Registration No. {number}`, then `{Short}: SEBI Reg. No. {number}`.
* B: full name with category, then the short name with category, then the short name without the
  category, then `Is {Short} SEBI Registered? No. {number}`.

On the 2026-10-02 register (1,792 page models) the mean title length fell from 105 to about 58
characters, 95 percent are 72 characters or fewer and 76 percent keep the number inside the first
60. Because the tail only survives when the name is short, most group A titles read
`{Name}: SEBI Registration No. {number}`; the A versus B contrast is therefore mainly
statement versus question. Both patterns are checked in `tests/qa_extra_registry.py`.

### Expired entries always use the non-question title

When the register's own validity end date is before the as-of date (`_end_before_asof`), the page
uses the group A pattern whatever its crc32 group, because a question title that invites a "Yes"
would be misleading. The model keeps `title_group` (the crc32 group) and adds `title_pattern`
(the pattern actually used). Exclude these pages (4 on the 2026-10-02 register) from the group
comparison, or compare on `title_pattern`.

* `{Name}` is the proper-cased legal name (all-caps register names are title-cased; names that
  already contain lower-case letters are left alone; single initials such as R.L.P., listed
  acronyms such as LLP or HDFC and vowel-less chunks such as GRD stay upper-case; "PVT" and
  "LTD" become "Pvt" and "Ltd"). The registration number is never altered.
* `{category}` comes from the registration number series: `INZ` is "Stock broker",
  `IN-DP` is "Depository participant (CDSL)" or "(NSDL)". In the B title a trailing bracket
  becomes a comma ("Depository participant, CDSL") so brackets never nest. It is never
  derived from which register list the row was pulled from.
* Meta description (both groups):
  `Yes, {Name} is listed in the SEBI register. Registration {number}, {category}, {exchanges}, effective {date}. Register as of {date}.`
  "Yes" is only ever written for a row that exists in the register file and whose listed end
  date is not before the as-of date. Otherwise the meta reads
  `{Name} appears in the SEBI register list; the validity end date listed is {end date}; check SEBI. Registration {number}, {category}, {exchanges}. Register as of {date}.`
  and FAQ 1 becomes "Does {Name} appear in the SEBI register list?" with a neutral answer. Exchanges are the
  trading exchanges listed on file (clearing corporations only when no exchange is listed);
  any part not on file is omitted. No claim of safety or quality is made anywhere.

## Deviation from the brief, on purpose

The brief's meta ends with "Register list dated {date}". The register carries no list date of
its own, so the only honest date is when BrokerLens last pulled the SEBI list (the ingest log
`_status.sebi_*.last_run`, falling back to `fetched_at`). The pages therefore say
"Register as of {date}" and explain in the footnote of the snapshot that it is the pull date.
If the date is missing, the sentence is dropped and the page says "Register date not on file".

## Canonical pages and the test population

One legal name can hold several registrations. Rows are grouped by a normalised legal name
(case, punctuation, Pvt/Private, Ltd/Limited ignored; dotted or spaced initials joined). The
stock broker (INZ) page is primary; otherwise CDSL then NSDL then registration number order.
Secondary pages stay live (HTTP 200, same URL), carry `<link rel=canonical>` to the primary
and are left out of the sitemap. A name is NOT merged when two members have different cities
on file, or when more than one INZ number sits under one name.

Consequence for the experiment: titles on canonicalised secondary pages are not expected to
be indexed. Measure the A/B groups on primary pages only: the primary slugs are every
sitemap URL under `/sebi-registry/`. Build the page filter in Search Console from those.

## How to read the test

1. Ship titles and meta (this change). The template change (answer line, snapshot table,
   FAQs) ships in the same release for the registry cluster, so the registry test measures
   the combined title plus template effect between groups, not template alone. Both groups
   get identical templates, so the A versus B difference still isolates the title pattern.
2. Run 28 days. Compare CTR and clicks by group using a Search Console page filter (regex on
   the slug list per group, generated with `crc32(slug) % 2`). Positions move at the same time
   as the template, so compare each group to itself before and after, then group to group.
3. Pre-registered success: group-level CTR at positions 8 to 10 above 0.5 percent (baseline
   0.10 percent on 1,952 impressions over 90 days). Daily clicks are low, so treat a gap
   smaller than the noise on a few dozen clicks as inconclusive.
4. Re-run URL Inspection on ten sampled primaries from each group at day 14 to confirm the
   recrawl picked up the title.
5. Roll the winning pattern to all primary pages; leave secondaries on their own pattern
   (they canonicalise away).

## What the pages will not say

No email address or telephone number (not in the page, not in structured data, not in
`registry.json`): the register's contact fields are not republished, and a street address is shown
only for clearly corporate legal names (Limited, Ltd, Private, Pvt, LLP, LLC, Bank, Corporation,
Company, Inc, PLC), never for individuals or "& Co" firms. Every page links the official SEBI
register list for its category instead. FAQ and structured-data wording says "as of BrokerLens's
pull of the register on {date}" because the register carries no date of its own.

No current good standing ("valid", "active") beyond quoting the register's own validity
text with its as-of date; no safety, quality or ranking claims; no complaint tables, no
enforcement orders and no name-change claims (no such fields are on file); no segment list
(equity, currency, commodity derivatives) because the register file holds exchange names
only. The only segment evidence shown is commodity exchange membership as listed.
