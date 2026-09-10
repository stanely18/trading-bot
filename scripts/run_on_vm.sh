#!/usr/bin/env bash
# Run one trading-bot slot from an always-on VM cron, then commit + push the
# updated experiment records. This is the shell port of the two GitHub Actions
# workflows' "run + commit" steps, for when GitHub's `schedule:` trigger proves
# too unreliable (see docs/oracle-vm-setup.md).
#
# Usage:  run_on_vm.sh cycle        # 4-hour Kimi trading cycle
#         run_on_vm.sh risk-check   # hourly deterministic risk check
#
# Both crontab lines call this script; flock serialises them so the 4h and 1h
# jobs can never write the SQLite ledger or push at the same moment (same role
# as the GitHub `concurrency: group` setting).
#
# Config (optional) is read from $ENV_FILE (default ~/trading-bot.env, chmod 600),
# which is NOT in git:
#   TRADING_MODEL=none            # or: nvidia   (only used by `cycle`)
#   NVIDIA_API_KEY=...            # only needed when TRADING_MODEL=nvidia
#   PYTHON_BIN=python3            # interpreter (must be 3.11+)
#   REPO_DIR=/home/ubuntu/trading-bot
#   GIT_NAME="trading-bot[bot]"
#   GIT_EMAIL="trading-bot@users.noreply.github.com"

set -uo pipefail

MODE="${1:-}"
case "$MODE" in
  cycle|risk-check) ;;
  *) echo "usage: $0 {cycle|risk-check}" >&2; exit 2 ;;
esac

ENV_FILE="${ENV_FILE:-$HOME/trading-bot.env}"
# shellcheck disable=SC1090
[ -f "$ENV_FILE" ] && . "$ENV_FILE"

SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="${REPO_DIR:-$(cd "$SELF_DIR/.." && pwd)}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
TRADING_MODEL="${TRADING_MODEL:-none}"
GIT_NAME="${GIT_NAME:-trading-bot[bot]}"
GIT_EMAIL="${GIT_EMAIL:-trading-bot@users.noreply.github.com}"
DB="state/experiment.sqlite3"
LOCK="/tmp/trading-bot.lock"

log() { printf '%s [%s] %s\n' "$(date -u +%FT%TZ)" "$MODE" "$*"; }

# ---- single-flight across both cron lines --------------------------------------
exec 9>"$LOCK"
if ! flock -w 600 9; then
  log "could not acquire $LOCK within 600s; another slot is still running. skipping."
  exit 0
fi

cd "$REPO_DIR" || { log "REPO_DIR $REPO_DIR missing"; exit 1; }

if [ ! -f "$DB" ]; then
  log "ERROR $DB missing. Bootstrap once: $PYTHON_BIN -m trading_bot --db $DB init ; then commit it."
  exit 1
fi

RID="$( [ "$MODE" = cycle ] && echo "experiment-$(date -u +%Y-%m-%dT%H)Z" || echo "risk-$(date -u +%Y-%m-%dT%H)Z" )"
log "slot $RID  (repo $REPO_DIR, python $PYTHON_BIN, model $TRADING_MODEL)"

# ---- get latest, then run ----------------------------------------------------
git fetch --quiet origin main || { log "git fetch failed"; exit 1; }
if ! git merge --ff-only --quiet origin/main; then
  log "local main is not fast-forwardable to origin/main; resetting (VM is a follower)"
  git reset --hard origin/main >/dev/null
fi

rc=0
if [ "$MODE" = cycle ]; then
  "$PYTHON_BIN" -m trading_bot --db "$DB" --root . --model "$TRADING_MODEL" cycle --run-id "$RID" || rc=$?
else
  "$PYTHON_BIN" -m trading_bot --db "$DB" --root . risk-check --run-id "$RID" || rc=$?
fi
# rc 3 (cycle only) = model errored but a safe HOLD + logs were still written.
if [ "$rc" -eq 3 ]; then
  log "WARN model error this slot; committed HOLD + error log. check logs/errors/$RID.json"
elif [ "$rc" -ne 0 ]; then
  log "ERROR run exited $rc; committing whatever was written, then failing"
fi

# ---- commit + push (retry once on a concurrent reviewer push) ---------------
git add state logs trades reports 2>/dev/null || true
if git diff --cached --quiet; then
  log "no changes to commit"
else
  git -c user.name="$GIT_NAME" -c user.email="$GIT_EMAIL" commit -q -m "$MODE $RID [skip ci]"
  if ! git push --quiet origin main; then
    log "push rejected; rebasing on origin/main and retrying"
    git pull --rebase --autostash --quiet origin main || { log "rebase failed"; exit 1; }
    git push --quiet origin main || { log "push failed after rebase"; exit 1; }
  fi
  log "pushed $(git rev-parse --short HEAD)"
fi

[ "$rc" -eq 0 ] || [ "$rc" -eq 3 ] || exit "$rc"
log "done"
