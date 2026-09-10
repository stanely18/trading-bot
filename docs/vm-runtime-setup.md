# 常開 VM 作為排程 runtime（Azure 為主）

GitHub Actions 的 `schedule:` trigger 實測會延遲、甚至整個丟掉 tick（某夜 risk-monitor
9 個 hourly tick 只跑 3 個；trading-cycle 2 個排程點跑 1 個）。被觸發到的 run 本身都
成功 —— 爛的只有 GitHub 自己的排程器。

這份 runbook 把排程搬到一台**常開的 Azure B1s VM**（免費帳號含前 12 個月每月 750
小時的 B1s，等於一台機器整月常開，涵蓋整個 30 天實驗），用系統 `cron` 觸發：cron
準時、Mac 不用開、**不改任何交易邏輯**（只多一支 `scripts/run_on_vm.sh` wrapper）。

VM 成為帳本的**唯一寫入者**；GitHub Actions 兩個 workflow 上線後 disable，留著當手動
fallback。Cowork 的 daily reviewer 不受影響（它只 push `reports/`）。

> 為什麼不用 Oracle Always Free：A1 ARM 幾乎永遠 "out of capacity"、帳號驗證常卡。
> Azure B1s 沒有這個容量抽獎。其他等效選項見文末。

---

## 1. 開 Azure B1s VM

1. 註冊 <https://azure.microsoft.com/free/>（信用卡做身分驗證，free 額度內不扣款；需手機驗證）。
2. Portal → **Create a resource → Virtual machine**：
   - Image：**Ubuntu Server 24.04 LTS**
   - Size：**B1s**（1 vCPU / 1 GB）——一定要選這個，free benefit 只認 B1s
   - Region：挑有 free 額度的（多數主要 region 都可；建立時若不符 free 會提示）
   - Authentication：**SSH public key**（貼你的 key）
   - Disk：**Standard SSD**，OS disk ≤ 64 GB（free 上限）
   - Networking：預設即可（只需對外 443 出站；SSH 22 入站限你的 IP）
3. 建好後記下 Public IP。預設使用者是 **`azureuser`**（不是 `ubuntu`）：
   `ssh azureuser@<IP>`

## 2. 首次登入設定

```bash
sudo timedatectl set-timezone UTC          # cron 欄位以 UTC 解讀
sudo apt update && sudo apt install -y git python3 python3-venv util-linux
python3 --version                           # 需 >= 3.11；24.04 是 3.12，OK
```

（若 image 只有 3.10：`sudo add-apt-repository ppa:deadsnakes/ppa && sudo apt install -y python3.11`，
再把 `PYTHON_BIN=python3.11` 寫進第 4 步的 env 檔。）

## 3. 取得 repo（deploy key，只給這個 repo 寫入權）

```bash
ssh-keygen -t ed25519 -C "trading-bot-vm" -f ~/.ssh/trading_bot_deploy -N ""
cat ~/.ssh/trading_bot_deploy.pub
```

GitHub → repo **Settings → Deploy keys → Add deploy key**：貼上該 public key，
**勾 Allow write access**。然後：

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
cat > ~/trading-bot.env <<EOF
TRADING_MODEL=none
# NVIDIA_API_KEY=nvapi-xxxxxxxx      # 之後接 Kimi 時取消註解並填；建議用跟翻譯工作分開的 key
PYTHON_BIN=python3
REPO_DIR=$HOME/trading-bot
EOF
chmod 600 ~/trading-bot.env
```

## 5. 測試（不啟排程，先手動跑一次）

帳本已在 `origin/main`（`state/experiment.sqlite3`，實驗計時從 2026-09-09 20:50 UTC 起算）。
先跑一次 risk-check 確認整條鏈通：

```bash
cd ~/trading-bot
./scripts/run_on_vm.sh risk-check
tail -n 20 ~/trading-bot-cron.log
git -C ~/trading-bot log --oneline -2       # 應看到新的 "risk-check risk-...Z [skip ci]" 已 push
```

失敗的話 log 會寫原因（缺 python、deploy key 沒寫入權、ledger 不存在…）。

## 6. 裝 crontab

```bash
crontab scripts/crontab.example             # 或 crontab -e 貼上內容
crontab -l
```

`scripts/crontab.example`：`0 */4 * * *` 跑 `cycle`、`0 * * * *` 跑 `risk-check`，
外面用 `flock` 序列化（4h 與 1h 在整點會撞在一起，flock 保證一次只跑一個、不會同時
寫 SQLite 或同時 push）。輸出都進 `~/trading-bot-cron.log`。

## 7. 關掉 GitHub Actions 排程（VM 上線後）

```bash
gh workflow disable trading-cycle.yml --repo stanely18/trading-bot
gh workflow disable risk-monitor.yml  --repo stanely18/trading-bot
```

workflow 檔案留著 —— 要手動補跑一輪仍可 `gh workflow run ...`（`workflow_dispatch`），
`[skip ci]` + 無 `push` trigger 保證不跟 VM 打架（同 `run_id` 會被 RiskGateway 當
idempotent replay）。

## 8. 之後接 Kimi

1. 把 `~/trading-bot.env` 的 `NVIDIA_API_KEY` 填好、`TRADING_MODEL=nvidia`。
2. 手動驗證一次：`./scripts/run_on_vm.sh cycle`，看 `logs/decisions/` 最新一筆的
   `agent.status` 是否 `ok`、`agent.request_id` 有值。
3. 記一筆到 `CHANGELOG.md`（把 model 從 none 換成 nvidia = 「開始正式跑」，值得記但
   不算改策略，`experiment_version` 不 bump）。

## 9. 監控 / 回退

- 日常：`tail -f ~/trading-bot-cron.log`；或 `git log --oneline` 看有沒有每小時／每 4h 的 commit。
- Cowork daily reviewer 會自動抓 `experiment-` / `risk-` slot 缺口並回報。
- **回退到 GitHub Actions**：`crontab -r` → `gh workflow enable trading-cycle.yml` +
  `gh workflow enable risk-monitor.yml`。
- VM 掉了（Azure free B1s 用完 750 hr/月、或帳號問題）：重跑第 1–6 步即可，帳本在
  git 上不會掉。B1s 750 hr ≈ 整月，正常單台常開不會超。

---

## 等效替代方案（Azure 也不行時）

| 方案 | 說明 |
|---|---|
| **GCP `e2-micro` Always Free** | us-west1／central1／east1，沒有 Oracle 的容量抽獎。第 1 步換成 GCP Console 建 VM（Ubuntu 24.04、e2-micro），其餘完全一樣 |
| **Hetzner CX22（~€4/月）／ DigitalOcean $4** | 最無腦。30 天實驗總花費 ≈ 一杯咖啡。`run_on_vm.sh` 原封不動 |
| **外部 cron → `workflow_dispatch`** | 不要 VM：cron-job.org 或 Cloudflare Worker Cron Trigger 每 4h／1h 打 GitHub API `POST /repos/stanely18/trading-bot/actions/workflows/{trading-cycle,risk-monitor}.yml/dispatches`（body `{"ref":"main"}`，header `Authorization: Bearer <fine-grained PAT，Actions: write>`）。GitHub Actions 照樣做事，只是換準時的觸發源。零程式改動、零 VM |
| **Oracle Cloud Always Free** | 若哪天 A1 有容量：Ubuntu 24.04、`VM.Standard.A1.Flex` 1 OCPU/6 GB 或 `VM.Standard.E2.1.Micro`，預設使用者 `ubuntu`，其餘同上 |
