#!/usr/bin/env bash
# Vercel build: seed sample broker metrics, fetch live market data, publish site/data/.
# Fetch is allowed to report gaps (exit 1) — we still publish what we got.
set -euo pipefail

PY=python3
command -v "$PY" >/dev/null 2>&1 || PY=python

export SITE_URL="${SITE_URL:-https://www.brokerlens.in}"
export SEBI_MAX_PAGES="${SEBI_MAX_PAGES:-25}"

"$PY" -m pipeline.run seed
"$PY" -m pipeline.run fetch || true
"$PY" -m pipeline.run build
