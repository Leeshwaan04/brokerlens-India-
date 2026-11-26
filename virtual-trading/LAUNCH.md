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

1. **Legal sign-off.** Confirm with counsel how SEBI's 8 May 2026 circular
   (30-day lag for price data used in education, in force 1 July 2026)
   applies, and approve the privacy notice (`/privacy`) and terms. The app
   ships with `VT_PRICE_LAG_DAYS=30`; only lower it on legal advice.
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

When to upgrade: the Worker's **Metrics** tab shows errors with "exceeded
CPU" or requests near 100,000 a day, or Hyperdrive's metrics near 100,000
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

## 2. Create the sign-in service (Owner)

1. Sign up at <https://dashboard.clerk.com>, create an application
   (email sign-in; Google is optional) and create its **production instance**
   for the domain `paper.brokerlens.in`.
2. Clerk lists DNS records (CNAMEs) for the production instance. Add them in
   Cloudflare DNS for `brokerlens.in` exactly as Clerk shows them (DNS only,
   grey cloud, if Clerk says so) and wait for Clerk to verify them.
3. From **API keys** keep the production publishable key (`pk_live_...`,
   public) and secret key (`sk_live_...`, private).

## 3. Set up the database (Agent; done 26 Nov 2026)

```bash
set -a; . ~/.config/brokerlens-paper/prod.env; set +a
export DATABASE_URL="$SUPABASE_SESSION_URL"
npx drizzle-kit migrate            # applies every migration in drizzle/
npm run sync:broker-rates          # broker fee schedules from seed/broker-rates.json
npm run seed:market-holidays       # NSE trading holidays
npm run sync:stock-universe        # Nifty 100 constituents from NSE
npx tsx scripts/eod-sync.mts --history 60   # price history; run twice on a new database
unset DATABASE_URL
```

Run new migrations the same way before deploying code that needs them.

## 4. Put the publishable key in the build (Owner, then Agent)

Next.js inlines `NEXT_PUBLIC_*` values at build time, so the publishable key
must be present when the worker is built and at runtime:

1. Add it to `wrangler.jsonc` under `vars` (it is public):
   `"NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY": "pk_live_..."`.
2. For CI deploys, store it as a repository variable:
   `gh variable set NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY --body 'pk_live_...'`

## 5. Set the worker's secrets (Owner)

Log in once with `npx wrangler login`, then run each command and paste the
value at the prompt. The first one creates the worker if it does not exist.

```bash
npx wrangler secret put CLERK_SECRET_KEY             # sk_live_... (step 2)
openssl rand -hex 32                                 # make a cron secret, keep it
npx wrangler secret put CRON_SECRET                  # paste that value
```

The Worker gets its database through the Hyperdrive binding in
`wrangler.jsonc`, so it needs no `DATABASE_URL` secret. `CRON_SECRET` only
guards the sync route, which production does not use (the sync runs in
GitHub Actions). `CLERK_WEBHOOK_SIGNING_SECRET` comes in step 8 and
`ADMIN_USER_IDS` in step 11.

## 6. First deploy (Agent)

```bash
npm ci
NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY='pk_live_...' npm run cf:deploy
```

`cf:deploy` runs the OpenNext build, then `opennextjs-cloudflare deploy`. It
prints a `*.workers.dev` URL; the app is not public on `paper.brokerlens.in`
until step 7.

## 7. Custom domain (Owner approves, Agent runs)

Check that Cloudflare DNS has no existing record for `paper`. Then either:

- Dashboard: **Workers & Pages > brokerlens-paper > Settings > Domains &
  Routes > Add > Custom domain** `paper.brokerlens.in`; or
- add to `wrangler.jsonc` and deploy again:
  `"routes": [{ "pattern": "paper.brokerlens.in", "custom_domain": true }]`

Cloudflare creates the DNS record and certificate. brokerlens.in itself is a
different worker and is not touched.

## 8. Clerk webhook (Owner)

In Clerk: **Webhooks > Add endpoint** `https://paper.brokerlens.in/api/webhooks/clerk`,
events `user.created` and `user.deleted`. Copy its signing secret, then:

```bash
npx wrangler secret put CLERK_WEBHOOK_SIGNING_SECRET
```

## 9. Load price history (Agent; done 26 Nov 2026)

Done in step 3 with `scripts/eod-sync.mts --history 60` (82 sessions, 28 Jul
to 25 Nov 2026; practice market at 26 Oct 2026). To fetch more from GitHub
instead: **Actions > Virtual Trading EOD Price Sync > Run workflow**, with a
history count.

## 10. Daily price sync and CI deploys

The daily sync is live: `.github/workflows/virtual-trading-eod-sync.yml` runs
`scripts/eod-sync.mts` at 19:00 IST every day with the `VT_DATABASE_URL`
secret (set 26 Nov 2026). It does not call the website.

Optional, so CI deploys on every push to `main` (Owner):

```bash
gh secret set CLOUDFLARE_API_TOKEN              # a token scoped to Workers Scripts: Edit
```

Without it, `virtual-trading-ci.yml` tests but skips the deploy, and deploys
are run by hand (step 6).

## 11. Admin access (Owner)

Sign up on `https://paper.brokerlens.in`, find your user id in Clerk
(**Users**, starts with `user_`), then:

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

After step 7 (custom domain) set `"workers_dev": false` in `wrangler.jsonc`
and deploy again, so the app is reachable only at paper.brokerlens.in.

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
