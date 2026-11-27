# Launching BrokerLens Virtual Trading

The app runs on Cloudflare Workers as the worker `brokerlens-paper`, built by
[`@opennextjs/cloudflare`](https://opennext.js.org/cloudflare), with Postgres
on Supabase (through Cloudflare Hyperdrive) and sign-in by Clerk, all on free
plans. Production address: `https://paper.brokerlens.in`.

Each step says who does it:

- **Owner**: needs your accounts, your keys, a payment or a legal decision. An
  agent must not do these for you.
- **Agent**: an agent (or you) can run it once the owner steps before it are
  done. Commands run from `virtual-trading/`.

Never paste keys into chat, commit them, or put them in `wrangler.jsonc`.
Secrets go in with `npx wrangler secret put`, which prompts for the value.

---

## 0. Decisions before anything else (Owner)

1. **Legal sign-off (received, per the owner, 27 Nov 2026).** The owner
   reports counsel's sign-off on SEBI's 8 May 2026 circular (30-day lag for
   price data used in education, in force 1 July 2026). The opinion itself is
   not in this repository. The app ships with `VT_PRICE_LAG_DAYS=30`; only
   lower it on legal advice. The site makes no compliance claim beyond what
   counsel approved in writing: add approved wording only from the opinion.
2. **Cloudflare plan.** The app is built to run on the **Workers Free plan**
   (see "Running on free plans" below). Upgrade to Workers Paid (USD 5 a
   month) when traffic nears the free limits listed there.

## Running on free plans (as set up on 26 Nov 2026)

| Piece | Service and plan | Free limit that matters |
|---|---|---|
| App | Cloudflare Workers Free, worker `brokerlens-paper` | 100,000 requests a day; 10 ms CPU a request; 3 MiB gzipped worker (the app is about 2.6 MiB) |
| Database | Supabase Free, project `brokerlens-paper` (ref `zojfefftkqbuvivwzqid`, Mumbai `ap-south-1`, org "Leeshwaan04's Org") | 500 MB (13 MB used at launch); paused after 7 days without activity, which the daily sync prevents |
| Database pooler | Cloudflare Hyperdrive Free, config `brokerlens-paper-db` (`ade55fc3221945f6a997d9525a371bc4`) | 100,000 queries a day (a signed-in page makes about 5 to 15) |
| Daily price sync | GitHub Actions (`virtual-trading-eod-sync.yml`), secret `VT_DATABASE_URL` | public repository, no minutes limit |
| Sign-in | Clerk Free | 50,000 monthly users |

What makes the Free plan workable:

- The daily sync (download and unzip NSE's bhavcopy, settle orders) runs in
  GitHub Actions as a Node script, `scripts/eod-sync.mts`, straight against
  the database. Inside the Worker it would need far more than 10 ms of CPU.
- The Worker reaches the database through Hyperdrive, which keeps pooled,
  already-authenticated connections near the database, so a request does no
  TLS or password handshake of its own. Hyperdrive verifies Supabase's
  certificate (`verify-full` against Supabase's root CA, uploaded to
  Cloudflare as `supabase-root-2021`); query caching is off, so pages never
  show a balance from before the user's last order. It may open at most 10
  connections, leaving room in Supabase's session pool for the sync.
- From Node, `lib/pg-ssl.ts` pins the same root CA and verifies it.

Measured on launch day (383 requests): median 23 ms of CPU, 300 to 850 ms on
a cold start, and no request refused; Cloudflare is not holding this worker
to the 10 ms figure today, but it may. When to upgrade: the Worker's
**Metrics** tab shows errors with "exceeded CPU" (error 1102) or requests
near 100,000 a day, or Hyperdrive's metrics near 100,000
queries a day. Workers Paid lifts both (CPU to 5 minutes a request,
Hyperdrive unlimited) with no code change.

Supabase's Free plan has no point-in-time recovery. Before real money flows
(Plus), consider Supabase Pro or a scheduled `pg_dump` kept somewhere
private (never as a GitHub Actions artifact: this repository is public).

## 1. The database (done 26 Nov 2026)

The connection details live only in `~/.config/brokerlens-paper/prod.env`
on the owner's Mac (readable by that user only): the database password and
`SUPABASE_SESSION_URL`, the session-mode pooler string
`postgresql://postgres.zojfefftkqbuvivwzqid:<password>@aws-0-ap-south-1.pooler.supabase.com:5432/postgres`.
The same string is stored in Hyperdrive and in the GitHub secret
`VT_DATABASE_URL`.

If the database password is ever reset (Supabase **Project Settings >
Database**), update all three:

```bash
npx wrangler hyperdrive update ade55fc3221945f6a997d9525a371bc4 --origin-password '<new password>'
printf '%s' '<new session URL>' | gh secret set VT_DATABASE_URL
# and edit ~/.config/brokerlens-paper/prod.env
```

## 2. Sign-in: Clerk (done 26 Nov 2026)

- Application **Brokerlens** in "Sumit's Organization" (Hobby, free). Its
  production instance is a *secondary application* on `paper.brokerlens.in`,
  so everything stays under that subdomain: Frontend API
  `clerk.paper.brokerlens.in`, account portal `accounts.paper.brokerlens.in`,
  email from `@paper.brokerlens.in`. Its five DNS records (CNAMEs for
  `clerk.paper`, `accounts.paper`, `clkmail.paper`, `clk._domainkey.paper`,
  `clk2._domainkey.paper`, all DNS only) were added through Cloudflare's
  one-time Domain Connect approval; brokerlens.in's own records, including
  its Hostinger mail, are untouched.
- Sign-in is by email (code or link) or Google. Phone numbers and SMS MFA
  are off (Clerk Pro features). Google uses its own OAuth client in the
  Google Cloud project `brokerlens-seo` (Google Auth Platform: app
  "BrokerLens Virtual Trading", External, **In production**, authorised
  domain `brokerlens.in`, no logo so no verification is needed; client
  "Clerk production (paper.brokerlens.in)" with origin
  `https://paper.brokerlens.in` and redirect
  `https://clerk.paper.brokerlens.in/v1/oauth_callback`). Its client secret
  lives only in Clerk (**SSO connections > Google**). To rotate it: Google
  Cloud > Clients > that client > **Add secret**, paste the new one into
  Clerk and save, then disable and delete the old secret in Google Cloud.
- Keys: the publishable key `pk_live_...` is public and lives in
  `wrangler.jsonc`. The secret key (named `cloudflare-worker-brokerlens-paper`
  in Clerk) and the webhook signing secret are worker secrets, with copies in
  `~/.config/brokerlens-paper/prod.env`.
- Webhook: `https://paper.brokerlens.in/api/webhooks/clerk`, events
  `user.created` and `user.deleted`; its signing secret was rotated once on
  26 Nov 2026 and tested (200).

## 3. Set up the database (Agent; done 26 Nov 2026)

```bash
set -a; . ~/.config/brokerlens-paper/prod.env; set +a
export DATABASE_URL="$SUPABASE_SESSION_URL"
npx drizzle-kit migrate            # applies every migration in drizzle/
npm run sync:broker-rates          # broker fee schedules from seed/broker-rates.json
npm run seed:market-holidays       # NSE trading holidays
npm run sync:stock-universe        # Nifty 50, 100 and 500 constituents (the universe is the Nifty 500)
npx tsx scripts/eod-sync.mts --history 60   # price history; run twice on a new database
unset DATABASE_URL
# Supabase only: close its Data API to the app's tables (see the file)
PGPASSWORD="$SUPABASE_DB_PASSWORD" psql "host=aws-0-ap-south-1.pooler.supabase.com port=5432 dbname=postgres user=postgres.zojfefftkqbuvivwzqid sslmode=verify-full sslrootcert=<Supabase root CA file>" -f scripts/supabase-lockdown.sql
```

Run new migrations the same way before deploying code that needs them, and
re-run `scripts/supabase-lockdown.sql` after any migration that adds tables.
Supabase grants its public `anon` and `authenticated` API roles full rights
on new tables by default; the lockdown removed them (checked: the REST API
answers "permission denied" for every table).

## 4 to 8. Keys, deploy, domain, webhook (done 26 Nov 2026)

Deploy from a clean worktree (no `.env.local`, whose dev values would
otherwise be bundled), with the public values in the environment because
Next.js inlines `NEXT_PUBLIC_*` at build time:

```bash
git worktree add --detach /tmp/vt-build HEAD && cd /tmp/vt-build/virtual-trading && npm ci
export NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=pk_live_Y2xlcmsucGFwZXIuYnJva2VybGVucy5pbiQ \
  NEXT_PUBLIC_CLERK_SIGN_IN_URL=/sign-in NEXT_PUBLIC_CLERK_SIGN_UP_URL=/sign-up \
  NEXT_PUBLIC_APP_URL=https://paper.brokerlens.in
npm run cf:build
grep -rl -e user_local_dev -e rzp_test_ -e localhost:5432 .open-next || echo clean
OPEN_NEXT_DEPLOY=true npx wrangler deploy
```

`npm run cf:deploy` would also work, but OpenNext's deploy first starts a
local emulator that insists on a local Hyperdrive connection string; with no
incremental cache configured it does nothing beyond `wrangler deploy`, so
the command above skips it. Secrets persist across deploys; set or change
one with `npx wrangler secret put <NAME>`.

Routing: `wrangler.jsonc` gives the worker the custom domain
`paper.brokerlens.in` **and** the route `paper.brokerlens.in/*`. The zone
also has a dashboard route `*brokerlens.in/*` for the main site
(`brokerlens-india`); its leading wildcard matches every subdomain and served
the main site on `paper.` until the more specific route was added. Leave that
dashboard route alone: brokerlens.in and www depend on it. `workers_dev` is
off, so there is no second public copy on `*.workers.dev`.

## 9. Load price history (Agent; done 26 Nov 2026)

Done in step 3 with `scripts/eod-sync.mts --history 60` (82 sessions, 28 Jul
to 25 Nov 2026; practice market at 26 Oct 2026). To fetch more from GitHub
instead: **Actions > Virtual Trading EOD Price Sync > Run workflow**, with a
history count.

## 10. Daily price sync and CI deploys

`.github/workflows/virtual-trading-eod-sync.yml` runs `scripts/eod-sync.mts`
at 19:00 IST every day with the `VT_DATABASE_URL` secret. It moves the
practice market forward and settles orders from the closes already stored,
which needs nothing from NSE.

**NSE refuses GitHub's runners** (HTTP 403 from nsearchives.nseindia.com,
seen 26 Nov 2026), so the Actions run cannot fetch new closes; it records a
`failed` row in `price_sync_runs` and carries on. Do not work around that
block with browser-imitating headers or other evasion. New closes are
fetched from a machine NSE serves normally, such as the owner's Mac:

```bash
set -a; . ~/.config/brokerlens-paper/prod.env; set +a
DATABASE_URL="$SUPABASE_SESSION_URL" npx tsx scripts/eod-sync.mts --history 20
```

Each run fills every missing day in the window, so running it every few days
is enough: the practice market reads closes 30 days old, so a gap only shows
if nothing is fetched for about four weeks. The database had closes to
25 Nov 2026 at launch.

Optional, so CI deploys on every push to `main` (Owner):

```bash
gh secret set CLOUDFLARE_API_TOKEN              # a token scoped to Workers Scripts: Edit
```

Without it, `virtual-trading-ci.yml` tests but skips the deploy, and deploys
are run by hand (steps 4 to 8).

## 10a. Monitoring (live since 26 Nov 2026)

- `GET /api/health` (public, never cached): 200 with `ok`, `db`, the newest
  stored close and `priceRunwayDays` (days before the practice market reaches
  it); 503 if the database does not answer.
- `.github/workflows/virtual-trading-uptime.yml` calls the home page and the
  health check every 30 minutes and fails, which emails the owner, when
  either is down or fewer than 10 days of closes remain (lib/health.ts).
- Worker logs: **Workers & Pages > brokerlens-paper > Observability**
  (200,000 events a day on the Free plan).

## 10b. Daily prices from the owner's Mac (installed 26 Nov 2026)

NSE refuses GitHub's runners but serves this Mac, so `scripts/install-mac-job.sh`
installs a launchd agent (`in.brokerlens.paper-daily`) that runs at 19:40 and 21:15 every
day (or when the Mac next wakes). `scripts/mac-daily.sh` keeps its own clone of
`main` in `~/.local/share/brokerlens-paper/repo`, reads
`~/.config/brokerlens-paper/prod.env`, and runs `scripts/eod-sync.mts --history 20`:
equity closes, index closes, the practice market's date, order settlement.
Log: `~/Library/Logs/brokerlens-paper-daily.log`. Run now:
`launchctl kickstart gui/$(id -u)/in.brokerlens.paper-daily`. Remove:
`scripts/install-mac-job.sh --remove`. If the Mac is off for days, the next run
catches up; the uptime monitor (10a) warns when fewer than 10 days of closes
remain.

## 10c. Backups (live from 26 Nov 2026)

`virtual-trading-backup.yml` backs up every table except the re-fetchable
price tables each night at 02:00 IST and keeps the file as a GitHub Actions
artifact for 90 days. The file is encrypted to a **public** key (GitHub secret
`VT_BACKUP_PUBLIC_KEY`); the **private key** is
`~/.config/brokerlens-paper/backup-private.pem` on the owner's Mac.
**Copy that file into your password manager now**: without it no backup can be
read, and nobody (including us) can recover it. This repository is public, so
its artifacts are downloadable by any GitHub user; the encryption (RSA-4096
wrapping an AES-256-GCM key, `lib/backup-crypto.ts`) is what keeps them private.

Restore into an EMPTY database whose tables exist (`npx drizzle-kit migrate`
first):

```bash
gh run download -R Leeshwaan04/brokerlens-India- -n vt-backup-<stamp> -D /tmp/vt-backup
DATABASE_URL=<empty db url> npx tsx scripts/restore-backup.mts /tmp/vt-backup/backup-<stamp>.bin \
  --private-key ~/.config/brokerlens-paper/backup-private.pem --apply
```

Then re-run the daily sync to refill prices. Tested end to end on 26 Nov 2026
(every table's rows matched, ciphertext holds no readable text). To read a
backup without restoring, use `--out dump.ndjson` instead of `--apply`.

## 11. Admin access (Owner)

Sign up on `https://paper.brokerlens.in`, find your user id in Clerk
(**Users** in the production instance, starts with `user_`), then:

```bash
npx wrangler secret put ADMIN_USER_IDS          # comma-separated user ids
```

`/admin` returns 404 for everyone else.

## 12. Price lag (Owner)

`VT_PRICE_LAG_DAYS` is `30` in `wrangler.jsonc`. Change it only on legal
advice, then deploy again.

## 12a. Payments for Plus (Owner; optional at launch)

Plus is a prepaid pass (Rs 99 for 30 days, Rs 799 for 12 months, set in
`lib/billing.ts`), bought through Razorpay Checkout. The practice market
stays free. With no Razorpay keys set, the Plus page says payments are not
available and nothing else changes.

Before taking real money:

1. Decide the legal entity that sells Plus, its GST registration, and whether
   the prices include GST (ask your accountant). Publish refund and
   cancellation terms on the Terms page; Razorpay's activation needs them.
2. Complete Razorpay account activation (KYC) so live keys are issued.
3. Generate the live keys in the Razorpay dashboard and put them straight
   into the worker's secrets (next step). Live keys never go into chat, email
   or a file. (Test keys were regenerated on 26 Nov 2026; they cannot move
   real money.)
4. Set the worker's secrets (live keys only here, never in a file):

```bash
npx wrangler secret put RAZORPAY_KEY_ID          # rzp_live_...
npx wrangler secret put RAZORPAY_KEY_SECRET
npx wrangler secret put RAZORPAY_WEBHOOK_SECRET  # a long random string you choose
```

5. In the Razorpay dashboard, **Webhooks**: URL
   `https://paper.brokerlens.in/api/webhooks/razorpay`, the same secret, events
   `payment.captured` and `order.paid`. The webhook grants Plus if a buyer
   closes the browser before returning from Checkout.
6. Make one real Rs 99 purchase yourself, check `/plus` shows Plus active and
   `/admin` shows it under Plus payments, then refund it from the Razorpay
   dashboard if you like.

Payment records stay in the `payments` table after an account is deleted,
unlinked from the person, as tax records must be kept.

## 12b. Abuse limits at Cloudflare (Owner, in the dashboard)

The app caps each account at 50 open orders (20 GTT) and 10 checkouts an
hour, but per-IP limits belong at the edge. Under **Security > WAF > Rate
limiting rules** for paper.brokerlens.in:

- `POST` to `/api/orders`, `/api/billing/` and any path with the
  `next-action` header (server actions): about 30 requests a minute per IP.
- `/go/`: about 30 a minute per IP (keeps account-opening click counts clean).
- `/api/cron/` and `/api/webhooks/`: leave open (they authenticate themselves).

`"workers_dev": false` is already set, so the app is reachable only at
paper.brokerlens.in.

At go-live with live Razorpay keys, clear any Plus granted in test mode:

```sql
update users set plus_until = null
where id in (select user_id from payments where mode = 'test' and status = 'paid');
```

A production build with `rzp_test_` keys treats payments as switched off,
unless `RAZORPAY_ALLOW_TEST_MODE=true` is set (for a staging copy only).

## 13. Smoke test (Agent, a few gentle requests; never a load or scan tool)

- [ ] `/` loads signed out and shows broker fees and a close date about 30 days ago.
- [ ] `/privacy` loads.
- [ ] Sign up, choose a broker, land on `/dashboard`; the header shows the practice market's date.
- [ ] `/trade`: place a market buy, a limit buy and a stop-loss sell; each appears under Orders as open.
- [ ] After the next 19:00 IST sync, the orders fill or expire by the rules on the Orders page.
- [ ] `/go/<broker>` redirects to the broker and the click shows in `/admin`.
- [ ] `/api/cron/sync-eod-prices` without the secret returns 401.
- [ ] Account page: start over, then delete account; the user disappears from Clerk.
- [ ] Worker logs (**Workers & Pages > brokerlens-paper > Logs**) show no errors.

## 14. Rollback (Agent)

```bash
npx wrangler deployments list --name brokerlens-paper
npx wrangler rollback <version-id>               # back to a previous version
```

To take the app offline entirely, remove the custom domain (step 7).

---

## Local preview of the production build

```bash
cp .dev.vars.example .dev.vars   # fill in a local DATABASE_URL and Clerk keys
npm run cf:preview               # OpenNext build, then wrangler dev on workerd
```

## Known risks

- Next.js 16 runs `proxy.ts` on the Node.js runtime, which OpenNext supports
  on Cloudflare as **experimental** ("not officially maintained ... use at
  your own risk"). It works in the local preview; watch the logs after launch.
  `proxy.ts` must import nothing that pulls in the database stack: doing so
  crashed every request on workerd ("Promise.prototype.then called on
  incompatible receiver"), which is why the campaign helpers live in
  `lib/campaign.ts`.
- On Workers a database connection belongs to one request, so `lib/db.ts`
  creates one client per request there (keyed by OpenNext's request context),
  connecting to Hyperdrive.
- Next.js lists Cloudflare's integration as not yet built on its verified
  adapter API, so check OpenNext's release notes before upgrading Next.js.
