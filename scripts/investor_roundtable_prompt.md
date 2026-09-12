You are running as the weekly "investor roundtable" for the trading-bot paper-trading experiment. You are invoked non-interactively (no human present to answer questions) — make reasonable decisions yourself and proceed; do not ask questions.

Context: trading-bot (repo at /Volumes/Stanley/專案/trading-bot) runs three paper-trading profiles (baseline / aggressive / conservative) on an EC2 VM. Kimi K3 proposes trades every 4 hours; a deterministic Python RiskGateway makes every actual decision. This weekly roundtable produces ONE background market briefing — pure reference material, never a trade instruction — that gets picked up automatically by the next trading cycle via an already-deployed mechanism (trading_bot/cycle.py reads state/roundtable_briefing.json on the VM if it exists and is less than 8 days old).

SSH connection details (use these exactly):
- Host: ec2-3-19-229-124.us-east-2.compute.amazonaws.com
- User: ubuntu
- Key: /Users/stanelytzeng/Downloads/stanleyvm.pem
- Repo on VM: ~/trading-bot

Do these steps in order:

## 1. Fetch a fresh market snapshot
SSH into the VM and run:
```
cd ~/trading-bot && python3 -c "from trading_bot.market import fetch; import json; print(json.dumps(fetch()))"
```
This returns a JSON object with price/timestamp for BTC-USDT, ETH-USDT, SOL-USDT, BNB-USDT, XRP-USDT. Keep this JSON — you'll reuse it for all three seats below so they're all commenting on the exact same snapshot.

## 2. Get three independent takes on the SAME snapshot
Ask each of the three seats the same short question: "Given this crypto market snapshot: <the JSON from step 1>. Give a brief (under 150 words) independent market read: overall regime (risk-on / risk-off / neutral / high-volatility), and a per-symbol directional lean if you have one. You are one of three independent reviewers in a weekly roundtable; a separate deterministic system makes all actual trading decisions — this is pure market commentary, never a trade instruction, and no one will act on it directly."

- **K3 seat**: SSH into the VM and run a short one-off Python script that reuses the already-configured `NvidiaKimiClient` (it reads NVIDIA_API_KEY from ~/trading-bot.env on the VM — you do not need and must never read or print that key yourself). Something like:
  ```
  cd ~/trading-bot && set -a && . ~/trading-bot.env && set +a && python3 -c "
  import sys, json
  sys.path.insert(0, '.')
  from trading_bot.model.nvidia import NvidiaKimiClient
  client = NvidiaKimiClient()
  # build a minimal request using the client's existing evaluate() contract -- read
  # trading_bot/model/nvidia.py first if the exact call shape isn't obvious from this
  # description alone, and adapt accordingly. The system_prompt can be short and
  # standalone for this one-off call, it does not need to match prompts/kimi-system.md.
  "
  ```
  Read `trading_bot/model/nvidia.py` on the VM (or your local checkout) first to see `NvidiaKimiClient`'s exact `evaluate(req)` signature and what shape `req` needs (system_prompt, context, request_id, snapshot_hash are likely required based on how trading_bot/cycle.py calls it) before writing this script, since guessing the shape wrong will just error. If the client's output schema strictly requires the full trading-agent JSON contract (market_regime/portfolio_view/candidates), either satisfy that minimal schema with a trivial HOLD-shaped response and pull the free-text reasoning out of it, or call the underlying NVIDIA API directly with a much simpler one-off prompt instead of going through NvidiaKimiClient's strict schema — whichever is less brittle. Either way, end up with a short free-text market take attributed to "k3".
- **Opus 5 seat**: this is you. Form your own independent read of the same snapshot, following the same question above. Do not just restate the other two seats.
- **Astra seat**: run locally (not over SSH — this runs on your own machine):
  ```
  cd /Volumes/Stanley/專案/trading-bot && codex exec -m gpt-6-astra --skip-git-repo-check "<the same question with the snapshot JSON inlined>"
  ```

If any seat fails (SSH error, NVIDIA API error, Codex CLI error), do NOT block the whole briefing — proceed with whichever seats succeeded, and note which one(s) failed and why in your final report. Never fabricate a seat's take if it actually failed.

## 3. Synthesize and write the briefing
Build this exact JSON shape (only include keys for seats that actually succeeded under "seats"):
```json
{
  "generated_at_ms": <current unix time in milliseconds, integer>,
  "generated_at_utc": "<current UTC time, ISO8601>",
  "seats": {
    "k3": "<k3's take, or omit this key if that seat failed>",
    "opus5": "<your own take>",
    "astra": "<astra's take, or omit this key if that seat failed>"
  },
  "note": "Weekly multi-model market roundtable. Pure background reference for Kimi K3's regular trading cycles -- never a trade instruction. The deterministic RiskGateway in trading_bot/core.py is the sole risk decision authority regardless of what this briefing or any model says."
}
```
Write this JSON via SSH directly onto the VM at `~/trading-bot/state/roundtable_briefing.json` (a heredoc over SSH is fine). This is a SHARED, root-level file read by all three trading profiles — do not write it anywhere else, and do not touch any other file on the VM (no git operations, no SQLite writes, nothing else).

## 4. Verify
SSH in again and `cat ~/trading-bot/state/roundtable_briefing.json`, confirm it parses as valid JSON and `generated_at_ms` is from today (not stale/leftover from a previous partial attempt).

## 5. Report
End your response with a short plain-text summary: which seats succeeded/failed and why, a one-line gist of each successful take, and confirmation the briefing landed on the VM with today's timestamp. This is captured in this run's log file for Stanley to read later — he will not see this interactively, so make it self-contained and skip pleasantries.
