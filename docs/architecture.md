# 架構與實驗提案

## 目標與範圍

主 orchestrator 為 Claude Cowork cloud。先證實基礎設施能持續執行，再啟動 30 日 paper 實驗，初始 10,000 USDT 虛擬資金，UTC 每小時一次。POC 僅現貨 BTC、ETH、SOL；沒有槓桿、借貸或真錢。

```text
Cowork cloud scheduled session
  ├─ 取得唯讀 portfolio / market snapshot
  ├─ 可選遠端 research / strategy / risk-review tools
  └─ 僅提交符合 schema 的 proposal
                  ↓ HTTPS + authenticated narrow API
固定 Python RiskGateway（可信任服務）
  ├─ 自行抓 OKX public market
  ├─ 固定風控、版本檢查、idempotency
  ├─ paper fill（交易所下單尚未實作）
  └─ SQLite transaction → portfolio + runs（持久磁碟）
```

## 執行邊界

本機版已實作 CLI 與 HTTP bridge。雲端版是部署提案，尚無雲端主機／DNS／認證。若直接讓 Cowork 在自己的 sandbox 執行 Python，必須先證明程式與 SQLite 跨 session 保留；即使保留，LLM 有檔案寫入權也能改掉風控，因此只能視為基礎設施測試。

要讓「LLM 不能 override」成為權限上可強制的邊界，需把 gateway 放到獨立服務：模型只有 `/state` 與 `/proposals` 的 token，無 shell、程式／policy／DB 寫入權與交易所金鑰。當前 Python 固定 policy + strict input 能防止透過 proposal 覆寫，但無法防止同一 OS 使用者直接改程式。hash chain 是一致性檢查，不是防惡意管理員的不可竄改儲存。

SQLite 只支援單一可信任 host 的持久磁碟；不能靠不同 Cowork sandbox 各自複製 DB。多節點未實作，未來用具唯一鍵與 compare-and-swap 的 PostgreSQL transaction backend，保留相同資料契約。

## 30 日順序

1. 啟動前：四項驗收完成，確認雲端 session、時鐘、資料來源、模型版本及持久化 backend。測試帳本不計入正式實驗。
2. 第 1–3 日：HOLD + 公開行情 + 帳本，計算預定／成功／缺漏排程數；錯誤不重置本金。
3. 第 4–7 日：固定策略或單一 LLM proposal；所有執行經同一 gateway。策略改動另立實驗版本。
4. 第 8–30 日：只有前階段穩定才考慮多模型；每模型獨立帳本、相同 snapshot、相同 policy 和執行成本。
5. 期滿：停止買入、下一次有效行情時 paper 平倉；保存完整帳本再分析。

每小時 30 日理論 720 個 slot，分母須依實際 start/end 對齊。每 slot 使用固定 ID（experiment + UTC hour）；重試使用完全相同 proposal。失敗回報及缺漏由排程平台另存，不能只有成功 ledger。

## 後續模型介面

`interfaces.py` 與 model request/response schemas 定義 request ID、provider/model、snapshot hash、role、deadline、usage。模型只能產生建議，risk-review 也不能批准突破 Python 限制。固定時限，無回應就明確記錄 unavailable，再由主 orchestrator 提出 HOLD；不得暗中切換供應商。此版本未實作或呼叫任何付費模型 backend。

多模型比較需記錄各自 prompt/version、模型識別、延遲、tokens、拒絕率、換手及成本。後續分析器可加 return、max drawdown、benchmark-relative return；30 日樣本不能證明穩定超額報酬。報表／benchmark 計算尚非本版功能。
