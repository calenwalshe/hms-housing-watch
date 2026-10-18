#!/usr/bin/env bash
# Daily Mac-lane browser-bridge pass (prototype): brief-style lead table to the
# tailnet-only Pixel prototype page. Read-only browsing; nothing goes to the
# public site. Failure exits nonzero and leaves the previous prototype page up.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MAC_LANE="${MAC_LANE:-/home/agent/projects/cairn-gate-labs/lab/infra/browser-bridge/bin/mac-lane.sh}"
LOG_DIR="$REPO/var/logs"
mkdir -p "$LOG_DIR" "$REPO/var/prototype"
exec >>"$LOG_DIR/prototype-$(date +%F).log" 2>&1
echo "== $(date -Iseconds) start"

fail() { echo "FAILED: $1 (prototype page unchanged)"; exit 1; }

exec 9>"$REPO/var/prototype.lock"
flock -n 9 || fail "another prototype run holds the lock"

cd "$REPO"
"$MAC_LANE" up || fail "mac-lane up"
"$REPO/.venv/bin/python" scripts/browser_pass.py --out "$REPO/var/prototype/index.html" || fail "browser_pass.py"

set -a; . /home/agent/projects/pixelcloud/.env; set +a
pixel update hms-housing-prototype "$REPO/var/prototype/index.html" --title "Prototype — browser-bridge daily pass" || fail "pixel update"
echo "== $(date -Iseconds) published"
