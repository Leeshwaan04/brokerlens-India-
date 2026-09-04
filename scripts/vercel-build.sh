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
export SEBI_MAX_PAGES="${SEBI_MAX_PAGES:-25}"
export PUBLISH_MODE=production

"$PY" -m pipeline.run fetch || true
"$PY" -m pipeline.run build
