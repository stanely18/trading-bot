#!/usr/bin/env bash
# Weekly investor roundtable, invoked by launchd (see
# ~/Library/LaunchAgents/com.stanley.trading-bot-roundtable.plist).
#
# Runs claude -p non-interactively as Opus 5, following the playbook in
# investor_roundtable_prompt.md: fetch a market snapshot from the VM, get
# independent takes from Kimi K3 (via SSH), Claude Opus 5 (itself), and
# Codex's gpt-6-astra (local CLI), synthesize into one JSON briefing, and
# write it back onto the VM at state/roundtable_briefing.json. Never touches
# the trading ledgers, never places a trade, never modifies code.
#
# Runs unattended (no human present to approve tool calls), so this uses
# --permission-mode bypassPermissions -- explicitly confirmed with Stanley
# on 2026-09-12. Scoped by what the prompt actually instructs: SSH to one
# known host/repo, read-only market data, three model calls, one file write.

set -uo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROMPT_FILE="$REPO_DIR/scripts/investor_roundtable_prompt.md"

log() { printf '%s %s\n' "$(date -u +%FT%TZ)" "$*"; }

if [ ! -f "$PROMPT_FILE" ]; then
  log "ERROR prompt file missing: $PROMPT_FILE"
  exit 1
fi

log "starting weekly investor roundtable"
claude -p "$(cat "$PROMPT_FILE")" \
  --model opus \
  --permission-mode bypassPermissions \
  --allowedTools "Bash" \
  || log "WARN claude -p exited non-zero: $?"
log "done"
