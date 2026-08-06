#!/usr/bin/env bash
# Vercel build: seed sample broker metrics, fetch live market data, publish site/data/.
# Fetch is allowed to report gaps (exit 1) — we still publish what we got.
# MCX is retried separately: Akamai often blocks the first datacenter hit.
set -euo pipefail

PY=python3
command -v "$PY" >/dev/null 2>&1 || PY=python

export SITE_URL="${SITE_URL:-https://www.brokerlens.in}"
export SEBI_MAX_PAGES="${SEBI_MAX_PAGES:-25}"

"$PY" -m pipeline.run seed
"$PY" -m pipeline.run fetch || true

mcx_count() {
  "$PY" -c "
import os
from pipeline.common import DATA, read_json
ingest = read_json(os.path.join(DATA, '_ingest.json'), {}) or {}
q = ((ingest.get('mcx') or {}).get('quotes') or {}).get('quotes') or []
print(len(q))
"
}

for attempt in 1 2 3; do
  count="$(mcx_count)"
  if [ "${count:-0}" -gt 0 ]; then
    echo "MCX: ${count} instruments"
    break
  fi
  echo "MCX empty (attempt ${attempt}/3), refetching..."
  "$PY" -m pipeline.run refetch-mcx || true
  sleep $((attempt * 3))
done

"$PY" -m pipeline.run build
