#!/usr/bin/env bash
# Fix brokerlens.in SSL_HOST_MISMATCH:
#   - Apex (brokerlens.in) redirects to www, but the cert only covers the apex.
#   - This script makes apex the primary host and adds www with a redirect + cert.
set -euo pipefail

: "${VERCEL_TOKEN:?Set VERCEL_TOKEN (https://vercel.com/account/tokens)}"

PROJECT="${VERCEL_PROJECT:-brokerlens-india}"
APEX="brokerlens.in"
WWW="www.brokerlens.in"

qs() {
  if [[ -n "${VERCEL_TEAM_ID:-}" ]]; then
    printf '?teamId=%s' "${VERCEL_TEAM_ID}"
  elif [[ -n "${VERCEL_TEAM_SLUG:-}" ]]; then
    printf '?slug=%s' "${VERCEL_TEAM_SLUG}"
  fi
}

Q="$(qs)"

api() {
  local method="$1" path="$2"
  shift 2
  curl -fsS -X "$method" \
    -H "Authorization: Bearer ${VERCEL_TOKEN}" \
    -H "Content-Type: application/json" \
    "https://api.vercel.com${path}${Q}" "$@"
}

echo "== Current domains on ${PROJECT} =="
api GET "/v9/projects/${PROJECT}/domains" | python3 -m json.tool

echo ""
echo "== 1. Stop apex → www redirect (serve on ${APEX}) =="
api PATCH "/v9/projects/${PROJECT}/domains/${APEX}" \
  -d '{"redirect":null,"redirectStatusCode":null}' | python3 -m json.tool

echo ""
echo "== 2. Add ${WWW} with redirect to apex (Vercel provisions www cert) =="
if api POST "/v10/projects/${PROJECT}/domains" \
  -d "{\"name\":\"${WWW}\",\"redirect\":\"https://${APEX}\",\"redirectStatusCode\":301}" \
  2>/tmp/vercel-add-www.err | python3 -m json.tool; then
  echo "Added ${WWW}"
else
  echo "(${WWW} may already exist — updating redirect)"
  cat /tmp/vercel-add-www.err >&2 || true
  api PATCH "/v9/projects/${PROJECT}/domains/${WWW}" \
    -d "{\"redirect\":\"https://${APEX}\",\"redirectStatusCode\":301}" | python3 -m json.tool
fi

echo ""
echo "== 3. Verify =="
sleep 5
echo -n "${APEX}: "
curl -sI --max-time 15 "https://${APEX}/" | head -1
echo -n "${WWW}: "
curl -sI --max-time 15 "https://${WWW}/" | head -1
echo ""
echo "Done. If ${WWW} still shows a cert error, wait 5–15 min for Let's Encrypt provisioning."
