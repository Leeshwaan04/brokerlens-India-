#!/bin/bash
# Installs (or updates) the daily price job on this Mac: a launchd agent that
# runs scripts/mac-daily.sh at 19:40 local time every day (NSE has published
# the day's files by then). If the Mac is asleep at that time, launchd runs
# it when the Mac wakes. Remove with: scripts/install-mac-job.sh --remove
set -euo pipefail
LABEL="in.brokerlens.paper-daily"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
BASE="$HOME/.local/share/brokerlens-paper"

if [ "${1:-}" = "--remove" ]; then
  launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
  rm -f "$PLIST"
  echo "removed $LABEL"
  exit 0
fi

mkdir -p "$BASE" "$HOME/Library/LaunchAgents"
NODE_BIN="$(dirname "$(command -v node)")"
sed "s#__NODE_BIN__#$NODE_BIN#" "$(dirname "$0")/mac-daily.sh" > "$BASE/mac-daily.sh"
chmod 700 "$BASE/mac-daily.sh"

cat > "$PLIST" <<PLISTEOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key><array><string>/bin/bash</string><string>$BASE/mac-daily.sh</string></array>
  <key>StartCalendarInterval</key><array>
    <dict><key>Hour</key><integer>19</integer><key>Minute</key><integer>40</integer></dict>
    <dict><key>Hour</key><integer>21</integer><key>Minute</key><integer>15</integer></dict>
  </array>
  <key>RunAtLoad</key><false/>
  <key>ProcessType</key><string>Background</string>
</dict>
</plist>
PLISTEOF

launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
echo "installed $LABEL: daily 19:40 and 21:15, log at ~/Library/Logs/brokerlens-paper-daily.log"
echo "run it now:   launchctl kickstart gui/$(id -u)/$LABEL"
