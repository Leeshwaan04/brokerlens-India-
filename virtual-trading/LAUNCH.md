# Launching BrokerLens Virtual Trading

The app runs on Cloudflare Workers as the worker `brokerlens-paper`, built by
[`@opennextjs/cloudflare`](https://opennext.js.org/cloudflare), with Postgres
on Neon and sign-in by Clerk. Production address: `https://paper.brokerlens.in`.

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
2. **Workers Paid plan** (USD 5 a month) on the Cloudflare account. The worker
   is 2.62 MiB gzipped, just under the Free plan's 3 MiB limit, but the Free
   plan allows 10 ms of CPU per request, which server-rendered pages and the
   daily price sync exceed. Paid allows 30 s by default.

## 1. Create the database (Owner)

1. Sign up at <https://console.neon.tech> and create a project named
   `brokerlens-paper` on the free tier, region **AWS Asia Pacific
   (Singapore) `ap-southeast-1`** or the nearest to India the console offers.
2. From **Connection details** copy two strings and keep them private:
   - the **pooled** connection string (host contains `-pooler`): the app uses this;
   - the **direct** connection string: migrations use this.

## 2. Create the sign-in service (Owner)

1. Sign up at <https://dashboard.clerk.com>, create an application
   (email sign-in; Google is optional) and create its **production instance**
   for the domain `paper.brokerlens.in`.
2. Clerk lists DNS records (CNAMEs) for the production instance. Add them in
   Cloudflare DNS for `brokerlens.in` exactly as Clerk shows them (DNS only,
   grey cloud, if Clerk says so) and wait for Clerk to verify them.
3. From **API keys** keep the production publishable key (`pk_live_...`,
   public) and secret key (`sk_live_...`, private).

## 3. Set up the database (Agent, with the direct string from step 1)

Run in a shell where you set the variable yourself:

```bash
export DATABASE_URL='<direct Neon connection string>'
npx drizzle-kit migrate            # applies every migration in drizzle/
npm run sync:broker-rates          # broker fee schedules from seed/broker-rates.json
npm run seed:market-holidays       # NSE trading holidays
npm run sync:stock-universe        # Nifty 100 constituents from NSE
unset DATABASE_URL
```

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
npx wrangler secret put DATABASE_URL                 # pooled Neon string (step 1)
npx wrangler secret put CLERK_SECRET_KEY             # sk_live_... (step 2)
openssl rand -hex 32                                 # make a cron secret, keep it
npx wrangler secret put CRON_SECRET                  # paste that value
```

`CLERK_WEBHOOK_SIGNING_SECRET` comes in step 8 and `ADMIN_USER_IDS` in step 11.

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

## 9. Load price history (Agent)

The practice market runs 30 days behind, so it needs about three months of
closes before its first session. Two runs fetch them from NSE's public
archive (each run fetches up to 60 missing days, one at a time):

```bash
curl -H "Authorization: Bearer $CRON_SECRET" "https://paper.brokerlens.in/api/cron/sync-eod-prices?history=60"
curl -H "Authorization: Bearer $CRON_SECRET" "https://paper.brokerlens.in/api/cron/sync-eod-prices?history=60"
```

Each returns JSON; `marketDate` should be the practice market's date (about
30 days ago) and `historyFetched` should be empty on the second run.

## 10. Daily price sync and CI deploys (Owner)

```bash
gh secret set VT_APP_URL --body 'https://paper.brokerlens.in'
gh secret set CRON_SECRET                       # same value as the worker's
gh secret set CLOUDFLARE_API_TOKEN              # optional: lets CI deploy on push to main
```

`.github/workflows/virtual-trading-eod-sync.yml` then calls the sync at 19:00
IST every day. With `CLOUDFLARE_API_TOKEN` set (a token scoped to
**Workers Scripts: Edit** on this account), `virtual-trading-ci.yml` builds
and deploys after the tests pass on `main`; without it the deploy job skips.

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
  creates one client per request there (keyed by OpenNext's request context).
- Next.js lists Cloudflare's integration as not yet built on its verified
  adapter API, so check OpenNext's release notes before upgrading Next.js.
