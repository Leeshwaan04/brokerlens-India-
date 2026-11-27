#!/bin/bash
# The daily NSE price job, run on the owner's Mac by launchd (see
# scripts/install-mac-job.sh). NSE refuses GitHub's runners but serves this
# Mac normally, so this is where new closes come from: the equity closes and
# the index closes, then the practice market moves forward and orders settle
# (lib/eod-sync.ts). Plain requests only, the same a browser's address bar
# would make; nothing here disguises itself.
#
# It works from its own clone of the repository, so whatever state the
# owner's working copy is in never affects it, and it always runs main.
set -uo pipefail

BASE="$HOME/.local/share/brokerlens-paper"
REPO="$BASE/repo"
ENV_FILE="$HOME/.config/brokerlens-paper/prod.env"
LOG="$HOME/Library/Logs/brokerlens-paper-daily.log"
export PATH="__NODE_BIN__:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"

mkdir -p "$BASE" "$(dirname "$LOG")"
exec >>"$LOG" 2>&1
echo "=== $(date '+%Y-%m-%d %H:%M:%S %Z') daily job start"

if [ ! -f "$ENV_FILE" ]; then echo "missing $ENV_FILE"; exit 1; fi

# launchd can fire while the Mac is still waking up: wait up to 10 minutes for
# the network rather than fail the day.
for i in $(seq 1 60); do
  curl -sf -o /dev/null --max-time 5 https://github.com && break
  [ "$i" = 60 ] && { echo "no network after 10 minutes"; exit 1; }
  sleep 10
done

if [ ! -d "$REPO/.git" ]; then
  git clone --depth 1 https://github.com/Leeshwaan04/brokerlens-India-.git "$REPO" || exit 1
else
  git -C "$REPO" fetch --depth 1 origin main && git -C "$REPO" reset --hard origin/main || exit 1
fi

cd "$REPO/virtual-trading" || exit 1
LOCK_HASH="$(shasum package-lock.json | cut -d' ' -f1)"
if [ ! -d node_modules ] || [ "$(cat "$BASE/lock.hash" 2>/dev/null)" != "$LOCK_HASH" ]; then
  npm ci --no-audit --no-fund || exit 1
  echo "$LOCK_HASH" > "$BASE/lock.hash"
fi

set -a; . "$ENV_FILE"; set +a
export DATABASE_URL="$SUPABASE_SESSION_URL" VT_PRICE_LAG_DAYS=30

# A window wider than the default, so a few days with the Mac off are caught up.
npx tsx scripts/eod-sync.mts --history 20
rc=$?
echo "=== $(date '+%Y-%m-%d %H:%M:%S %Z') daily job done, exit $rc"
exit $rc
