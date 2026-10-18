#!/usr/bin/env bash
# Daily wrapper: start Mac-lane, take a single-run lock, refresh, commit/push on change.
# INACTIVE until the owner approves creating the public repo and enabling the timer.
# Failure at any step exits nonzero and leaves the committed snapshot untouched.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MAC_LANE="${MAC_LANE:-/home/agent/projects/cairn-gate-labs/lab/infra/browser-bridge/bin/mac-lane.sh}"
LOG_DIR="$REPO/var/logs"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/daily-$(date +%F).log"
exec >>"$LOG" 2>&1
echo "== $(date -Iseconds) start"

fail() { echo "FAILED: $1 (snapshot not published)"; exit 1; }

exec 9>"$REPO/var/run.lock"
flock -n 9 || fail "another run holds the lock"

cd "$REPO"
"$MAC_LANE" up || fail "mac-lane up"
"$REPO/.venv/bin/python" scripts/daily_refresh.py || fail "daily_refresh.py"

if git diff --quiet -- site/leads.json; then
  echo "no change; nothing to publish"
  exit 0
fi
git add site/leads.json
git commit -m "data: daily refresh $(date +%F)" || fail "git commit"
# Uses the service user's existing gh/git credentials; nothing is printed.
git push origin main || fail "git push (local commit kept; next run retries)"
echo "== $(date -Iseconds) published"
