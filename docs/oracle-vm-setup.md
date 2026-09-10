# Oracle Cloud Always Free VM 作為排程 runtime

GitHub Actions 的 `schedule:` trigger 實測會延遲、甚至整個丟掉 tick（見對話記錄：
某夜 risk-monitor 9 個 hourly tick 只跑 3 個）。這份 runbook 把排程搬到一台
**永久免費、常開**的 Oracle Cloud VM 上，用系統 `cron` 觸發 —— cron 100% 準時、
Mac 不用開、**不改任何交易邏輯**（只多一支 `scripts/run_on_vm.sh` wrapper）。

VM 成為帳本的**唯一寫入者**；GitHub Actions 的兩個 workflow 上線後 disable，留著當
手動 fallback。Cowork 的 daily reviewer 不受影響（它只 push `reports/`）。

---

## 1. 開 VM

1. 註冊 <https://www.oracle.com/cloud/free/>（需信用卡驗證，Always Free 資源不扣款）。
2. Compute → Instances → **Create instance**：
   - Image：**Canonical Ubuntu 24.04**（內建 Python 3.12，省事）
   - Shape：`VM.Standard.A1.Flex`（Ampere ARM，Always Free 額度內給 1 OCPU / 6 GB 即足夠）
     ——若 A1 容量不足，改 `VM.Standard.E2.1.Micro`（AMD，也是 Always Free）
   - 下載或貼上你的 SSH public key
3. 建好後記下 Public IP。`ssh ubuntu@<IP>`。

## 2. 首次登入設定

```bash
sudo timedatectl set-timezone UTC          # cron 欄位以 UTC 解讀
sudo apt update && sudo apt install -y git python3 python3-venv util-linux
python3 --version                           # 需 >= 3.11；24.04 是 3.12，OK
```

（若 image 只有 3.10：`sudo add-apt-repository ppa:deadsnakes/ppa && sudo apt install -y python3.11`，
之後把 `PYTHON_BIN=python3.11` 寫進第 4 步的 env 檔。）

## 3. 取得 repo（deploy key，只給這個 repo 寫入權）

```bash
ssh-keygen -t ed25519 -C "trading-bot-vm" -f ~/.ssh/trading_bot_deploy -N ""
cat ~/.ssh/trading_bot_deploy.pub
```

到 GitHub → repo **Settings → Deploy keys → Add deploy key**：貼上上面那把 public key，
**勾選 Allow write access**。然後：

```bash
cat >> ~/.ssh/config <<'EOF'
Host github.com
  IdentityFile ~/.ssh/trading_bot_deploy
  IdentitiesOnly yes
EOF
chmod 600 ~/.ssh/config
ssh -T git@github.com                        # 應看到 "Hi stanely18/trading-bot! ..."
git clone git@github.com:stanely18/trading-bot.git ~/trading-bot
```

## 4. 密鑰 / 設定檔（不進 git）

```bash
cat > ~/trading-bot.env <<'EOF'
TRADING_MODEL=none
# NVIDIA_API_KEY=nvapi-xxxxxxxx      # 之後接 Kimi 時再取消註解並填；建議用一把跟翻譯工作分開的 key
PYTHON_BIN=python3
REPO_DIR=/home/ubuntu/trading-bot
EOF
chmod 600 ~/trading-bot.env
```

## 5. 測試（不啟排程，先手動跑一次）

帳本已經在 `origin/main` 上（`state/experiment.sqlite3`，實驗計時從 2026-09-09 起算）。
先跑一次 risk-check 確認整條鏈通：

```bash
cd ~/trading-bot
./scripts/run_on_vm.sh risk-check
tail -n 20 ~/trading-bot-cron.log
git -C ~/trading-bot log --oneline -2       # 應看到新的 "risk-check risk-...Z [skip ci]" 已 push
```

若失敗，log 會寫原因（缺 python、deploy key 沒寫入權、ledger 不存在…）。

## 6. 裝 crontab

```bash
crontab scripts/crontab.example             # 或 crontab -e 貼上內容
crontab -l
```

`scripts/crontab.example` 內容：`0 */4 * * *` 跑 `cycle`、`0 * * * *` 跑 `risk-check`，
外面用 `flock` 序列化（4h 與 1h 在整點會撞在一起，flock 保證一次只跑一個、不會同時
寫 SQLite 或同時 push）。輸出都進 `~/trading-bot-cron.log`。

## 7. 關掉 GitHub Actions 排程（VM 上線後）

```bash
gh workflow disable trading-cycle.yml --repo stanely18/trading-bot
gh workflow disable risk-monitor.yml  --repo stanely18/trading-bot
```

workflow 檔案留著 —— 之後要手動補跑一輪仍可 `gh workflow run ...`（用 `workflow_dispatch`），
它們的 `[skip ci]` + 無 `push` trigger 保證不會跟 VM 打架（同 `run_id` 會被 RiskGateway
當 idempotent replay）。

## 8. 之後接 Kimi

1. GitHub 那把 key 不需要了；把 `~/trading-bot.env` 的 `NVIDIA_API_KEY` 填好、
   `TRADING_MODEL=nvidia`。
2. 手動驗證一次：`./scripts/run_on_vm.sh cycle`，看 `logs/decisions/` 最新一筆的
   `agent.status` 是不是 `ok`、`agent.request_id` 有值。
3. 記進 `CHANGELOG.md`（`experiment_version` 動到策略條件才 bump；只是把 model 從 none
   換成 nvidia 屬於「開始正式跑」，值得記一筆但不算改策略）。

## 9. 監控 / 回退

- 日常：`tail -f ~/trading-bot-cron.log`；或看 `git log --oneline` 有沒有每小時／每 4h 的 commit。
- Cowork daily reviewer 會自動抓 `experiment-` / `risk-` slot 的缺口並回報。
- **回退到 GitHub Actions**：`crontab -r`（清空 VM 排程）→
  `gh workflow enable trading-cycle.yml` + `gh workflow enable risk-monitor.yml`。
- VM 被 Oracle 回收（Always Free 閒置實例偶爾會）：重跑第 1–6 步即可，帳本在 git 上不會掉。
