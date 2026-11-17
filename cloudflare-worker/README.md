# Draft. Not deployed. Do not `wrangler deploy` from this directory.

This is a design sketch for a possible future edge router (proxying `/api/*` to a
Cloud Run backend, with custom caching and security headers), not the live site.

Checked on 16 Nov 2026 with `wrangler deployments list --name brokerlens-edge-router`:
this Worker (named in `wrangler.toml`) does not exist on the Cloudflare account. The
live site is served by a separate, unrelated Worker, "brokerlens-india" (the root
`wrangler.jsonc`), which is plain static-asset serving with no Worker script at all.

Before this is ever deployed:

- Confirm `CLOUD_RUN_ORIGIN` (`brokerlens-web-649203501892.asia-south1.run.app`) is a
  real backend this project owns and intends to use. It has not been verified to exist.
  (A *different*, already-live Cloud Run service, `brokerlens-stream-...`, is used today
  for the site's price ticker stream - see `site/assets/js/app.js`. Don't confuse the two.)
- Review what forwarding every request header, and the raw `cf-connecting-ip`, to that
  backend actually exposes to it.
- Decide whether this site needs a Worker script at all, given the static-asset
  deployment already works; adding one is a bigger change to how the site runs, not a
  drop-in extra.

If this direction is abandoned, delete this directory instead of leaving it to look
like live infrastructure.
