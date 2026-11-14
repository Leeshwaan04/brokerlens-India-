#!/usr/bin/env bash
# Vercel build: fetch live regulator/market data, publish site/data/.
#
# PUBLISH_MODE=production makes publish.build() drop anything still flagged
# provenance:"sample" instead of shipping it. Without this, the seed step
# below used to regenerate fake broker stats on every deploy and they went
# live with no gate at all - real fetched data and fabricated data merged
# together with no way for a visitor to tell them apart.
#
# Fetch is allowed to report gaps (exit 1) - we still publish whatever real
# data it did get, rather than fail the whole deploy over one flaky source.
set -euo pipefail

PY=python3
command -v "$PY" >/dev/null 2>&1 || PY=python

export SITE_URL="${SITE_URL:-https://www.brokerlens.in}"
# SEBI's own paginated registers currently need up to 83 pages (commodity
# broker) - a cap of 25 was silently truncating that category to ~30% of its
# real size (and dp_cdsl to ~83%), understating the live registry by roughly
# 660 real, already-indexable entities. 100 covers today's real page counts
# with headroom for organic growth in SEBI's own register.
export SEBI_MAX_PAGES="${SEBI_MAX_PAGES:-100}"
export PUBLISH_MODE=production

# xlrd is needed only by the report1c step below. It is installed into a
# local folder with --target rather than into the interpreter: PEP 668 lets
# an image mark its Python "externally managed", which makes a plain pip
# install fail, and under set -e that failed the whole deploy (3 Nov 2026).
# If even this fails, only report1c is skipped: it keeps the committed
# data/manual/active_clients.json, which the daily pipeline workflow
# refreshes and commits on its own.
DEPS="$PWD/.pydeps"
if "$PY" -m pip install -q --target "$DEPS" -r pipeline/requirements.txt; then
  export PYTHONPATH="$DEPS${PYTHONPATH:+:$PYTHONPATH}"
else
  echo "vercel-build: pipeline/requirements.txt not installed; report1c will keep the committed data"
fi
"$PY" -m pipeline.run fetch || true
# Crawls each configured broker's own SEBI Annexure-B disclosure page for
# real complaint counts (see pipeline/sources/complaints.py). This was built
# but never actually wired into a deploy until now, so data/manual/
# complaints.json stayed 100% sample data regardless of how many brokers'
# pages could genuinely be parsed. Same "never let one source kill the
# build" tolerance as fetch: a bad run here leaves the existing file
# untouched rather than failing the deploy.
"$PY" -m pipeline.run complaints || true
# NSE's own Report 1C (broker-wise active clients, UCCs, defaulter flag -
# see pipeline/sources/nse_report1c.py). Only updates ~monthly on NSE's own
# side, so running it on every deploy is harmless (the Fetcher's own 12h
# cache + idempotent same-month overwrite means repeat runs within a month
# just confirm the same figure, never duplicate it). Needs xlrd (the --target
# install above) - the one documented exception to this project's
# otherwise stdlib-only policy, since NSE only publishes this as legacy
# binary .xls.
"$PY" -m pipeline.run report1c || true
"$PY" -m pipeline.run holidays || true
# Clean stale unindexed comparisons and retired trade directories
rm -rf site/compare/stocks site/compare/mutual-funds site/broker/*/trade 2>/dev/null || true
"$PY" -m pipeline.run build
"$PY" scripts/export_gsc_live.py || true
"$PY" scripts/generate_cloudflare_config.py || true
