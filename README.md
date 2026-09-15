# Publixia — 大盤成交量能冷熱判讀

Publixia 用「目前指數位階下，今天的市場量能是否異常」描述台股市場環境，並把
同日三大法人買賣金額放在同一條時間軸上。它不是交易訊號，也不預測漲跌；它提供
一個可觀察、可回溯的 market regime，供人工判讀或其他研究工具分組分析。

- **台股**：加權指數收盤 + TWSE 成交金額（億元）
- **情緒**：固定公開公式的 0～100 台股恐懼貪婪代理指數，與加權指數以雙軸折線比較
- **法人**：TWSE BFI82U 外資、投信、自營商每日買進／賣出／差額
- **後端**：FastAPI + APScheduler + SQLite，部署於 VPS
- **前端**：Vite + React + Tailwind，部署於 GitHub Pages
- **網址**：<https://stock.paul-learning.dev>
- **API**：<https://api.paul-learning.dev>

> Repo 曾先後實作股市指標儀表板、期貨策略引擎與跟單追蹤器。現行產品只有
> 大盤量能冷熱判讀；舊 migration 與設計文件保留作為歷史，並非現行功能。

## 判讀方法

1. 以全歷史資料擬合 `ln(量能) = a + b × ln(指數)`，估計目前指數位階下的常態量能。
2. 計算 `殘差 = ln(實際量能 / 常態量能)`。
3. 將殘差放進近 241 個交易日（約一年）計算百分位。
4. 分成明顯偏冷、偏冷、正常、偏熱、明顯偏熱五級。

冷熱判讀的衍生值都在讀取時重新計算，資料庫保存日期、指數收盤、量能，以及法人
買賣的整數元原始值。法人金額在 API 轉為億元；法人成交比重以
`(法人買進 + 法人賣出) / (市場成交金額 × 2)` 計算。
因此歷史判讀可能隨
新資料加入而小幅漂移；需要可重現研究時，應保存 API 快照。

另有 `tw_fear_greed_proxy_v1` 自算情緒指數：動能 25%、距高點回撤 20%、反向
波動率 20%、上市股票市場寬度 25%、60 日均線偏離 10%。價格因子只使用當天以前
最多 1,260 個交易日的歷史百分位；市場寬度來自 TWSE MI_INDEX 的股票漲跌家數。
這是可重現的代理指數，不是財經 M 平方的專有數值。

## API

```text
GET  /health
GET  /api/market/volume-heat?market=TW&days=120
GET  /api/market/regimes?market=TW
POST /api/market/volume-heat/refresh?market=TW
```

`volume-heat` 提供畫面使用的完整數值，每個交易日另帶可為 `null` 的
`sentiment` 情緒指數與 `institutional` 法人資料；`regimes` 是給研究工具使用的
穩定、版本化薄介面，只包含：

```json
{
  "schema_version": 1,
  "market": "TW",
  "method": "volume_heat_v1",
  "regimes": [{
    "date": "2026-09-01",
    "percentile": 0.82,
    "level": "very_hot",
    "label": "明顯偏熱"
  }]
}
```

`level` 的穩定值為 `very_cold`、`cold`、`normal`、`hot`、`very_hot`。消費端應
檢查 `schema_version`，不要解析中文 `label`。

## 專案結構

```text
backend/
  api/routes/market.py       市場 API
  core/                      TWSE、Discord 與設定
  repositories/             SQLite 存取
  services/market_heat.py    OLS、百分位與五級判讀
  services/market_sentiment.py  五因子情緒代理指數
  services/market_breadth_sync.py  MI_INDEX 漲跌家數回補與每日同步
  services/institutional_flow_sync.py  BFI82U 法人資料回補與每日同步
  services/intraday_heat.py  台股盤中估算與通知
  jobs/ + scheduler.py       DB-driven 排程
  db/migrations/             forward-only migrations
frontend/                    React 總覽、冷熱明細與方法說明
tests/                       後端 pytest
frontend/tests/              Vitest + Testing Library
```

## 本機開發與測試

```bash
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn main:app --reload --port 8000
```

另一個 terminal：

```bash
cd frontend
npm install
npm run dev
```

測試：

```bash
python3 -m pytest tests/
cd frontend && npm test
```

測試不需要連外；fetcher 以 fixture 與 mock 驗證。

## 排程

Cron 儲存在 `scheduler_jobs`，時區為 `Asia/Taipei`，字串採 POSIX 星期語義：

| Job | 預設 cron | 用途 |
|---|---|---|
| `intraday_heat_signal` | `0 13 * * 1-5` | 台股 13:00 盤中估算並推 Discord |
| `market_volume_sync` | `0 16 * * 1-5` | 同步 TWSE 收盤資料 |
| `institutional_flow_sync_early` | `10 16 * * 1-5` | 同步 TWSE 三大法人第一版資料並推 Discord |
| `market_breadth_sync` | `20 16 * * 1-5` | 同步 TWSE 上市股票漲跌家數供情緒指數 |
| `institutional_flow_sync` | `0 20 * * 1-5` | 同步 TWSE 三大法人最終版買賣金額，有更新或尚未送出時推 Discord |
| `backup_db` | `0 3 * * *` | SQLite 備份到 R2 |

排程失敗會透過維運 webhook 告警；休市使用 `MarketClosed` 回報，不會靜默略過。

法人通知沿用大盤 Discord webhook，列出當日外資及陸資、投信、自營商與合計的
買進、賣出及買賣超（億元）。16:10 取得當日資料後立即推送；20:00 金額有修訂才
另送「更新」，早場未送達則補送。成功送出後才將金額指紋記入 DB，重跑或重啟後
相同金額不重複通知。手動 refresh 與歷史回補不推播；當日抓取失敗不使用已存資料
代替，若大盤交易日仍停在過去則通報可能休市或收盤資料未同步。

## 部署與設定

- Push 到 `master` 後，backend/frontend 依 path filter 各自部署。
- Backend 位於 VPS `/opt/stock-dashboard/backend`，沿用舊 service 名
  `stock-dashboard.service`。
- Frontend 從自訂子網域根路徑 `/` 提供。
- Backend 啟動時自動套用尚未執行的 migration。
- 已部署 migration 不可修改；schema 修正一律新增下一支 migration。

主要 secrets：

- `R2_ACCESS_KEY_ID`、`R2_SECRET_ACCESS_KEY`、`R2_ENDPOINT_URL`、`R2_BUCKET`
- `DISCORD_STOCK_WEBHOOK_URL`（部署時映射成 market webhook）
- `DISCORD_OPS_WEBHOOK_URL`（可選；未設時維運告警退回 market webhook）

不要提交 `.env`、webhook、VPS hostname、SSH key 或 API token。

## 與 futures_analyzer 的邊界

Publixia 只發布市場 regime，不執行期貨策略、不提供下單建議。`futures_analyzer`
可以把 `/api/market/regimes` 保存成快照，再依交易進場日分組檢查策略在不同 regime
下的績效。兩個 repo 刻意分離，避免 production dashboard 與研究環境共享依賴、
部署週期及故障範圍。
