# 美股全名冊正規化（US Stock Roster Normalization）

- 日期：2026-06-05
- 狀態：設計已確認，待寫 implementation plan

## 問題

追蹤帳號裡有美股玩家（如 Aoi）。一則貼文「我 intc 賣在 100」會：

1. AI 抽取正確：`{raw_symbol: "intc", direction: "sell", price: 100}`
2. `normalize("intc")` 查 `stock_reference` 失敗 → `(None, None)`，因為美股只有一份**手寫 10 檔靜態清單**（`_US_STATIC`：NVDA/TSLA/AAPL/MSFT/GOOGL/AMZN/META/TSM/AMD/PLTR），沒有 INTC。
3. 存進 `extracted_trades` 時 `ticker = NULL`、`market = NULL`。
4. `list_tracking_targets` 的 SQL 有 `WHERE et.ticker IS NOT NULL` → 這筆被排除，**不會建立價格追蹤列**。
5. 前端右側績效面板（最新 / 7日 / 1月）永遠停在「追蹤中」，chip 顯示小寫原文 `intc`、沒有公司名。

根因：**美股代號覆蓋率受限於那份 10 檔手寫清單**，不是抽取或價格抓取的問題。`price_history.py` 對 `market == "US"` 本來就是「代號直接丟 yfinance」，yfinance 抓得到 INTC——只要正規化能對到 `(INTC, US)`，整條價格追蹤就會自動正常。

## 目標

讓美股不再依賴手寫清單：改用免費的**全市場名冊**自動同步，與台股用 FinMind 的做法對齊。範圍外的中文暱稱（輝達、超微…）仍由別名 overlay 補上。

## 非目標

- 不做 hybrid 的「代號 passthrough 兜底」（使用者已選名冊方案）。SEC 名冊涵蓋不到的少數 ETF / 冷門 ADR 仍維持現狀 `(None, None)`，數量大幅減少即可，日後缺哪檔再補 overlay 或另議。
- 不處理另一條線：prompt 誤把「動能 / 下半年趨勢題材 / 核心部位」等資產配置抽象詞抓成交易（已 park，獨立處理）。
- 美股大盤（道瓊 / 那斯達克 / 標普）是否納入抓取範圍，本案不變動。

## 資料來源

SEC 官方 `https://www.sec.gov/files/company_tickers.json`

- 免 token、免金鑰；約 1 萬檔。
- 格式：`{"0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."}, "1": {...}, ...}`——含**代號 + 正式公司名**。
- SEC 的 fair-access 政策要求帶 `User-Agent` header，否則回 403。需設一個專案識別字串（如 `publixia-stock-tracker`）。
- 角色完全對應台股的 FinMind 名冊：差別只在台股是數字代號、美股是英文代號。

## 設計

### 1. `backend/core/sec.py`（新）

仿 `core/finmind.py` 的小型 fetch helper，把唯一的網路呼叫集中一處，方便測試 mock。

- `fetch_company_tickers() -> list[dict]`：帶 `User-Agent` GET 上述 JSON，把 `{"0": {...}, "1": {...}}` 攤平成 `[{"ticker": ..., "title": ...}, ...]` 回傳。
- 傳輸錯誤照 `requests` 慣例往上拋（與 finmind 一致）。

### 2. `backend/services/stock_reference_sync.py`

- `_US_STATIC`（ticker → (英文名, 中文別名)）**改名為 `_US_ALIAS_OVERLAY`**（ticker → 中文別名清單），與 `_TW_ALIAS_OVERLAY` 同構。英文公司名改由 SEC `title` 提供，overlay 只留中文暱稱：
  - `NVDA → [輝達, 黃仁勳]`、`TSLA → [特斯拉, 電動車]`、`AAPL → [蘋果]`、`MSFT → [微軟]`、`GOOGL → [谷歌, Google]`、`AMZN → [亞馬遜]`、`META → [臉書, Facebook]`、`TSM → [台積電ADR, 台積電 ADR]`、`AMD → [超微]`。（PLTR 無中文別名，可不列）
- 新增 `sync_us_from_sec() -> int`：
  1. `rows = fetch_company_tickers()`
  2. 以 ticker 去重（SEC 理論上唯一，仍 `setdefault` 防呆）
  3. 組 `{"ticker": t, "market": "US", "canonical_name": title, "aliases": _US_ALIAS_OVERLAY.get(t)}`
  4. `upsert_reference_batch(rows, source="sec")`，回傳筆數並 `logger.info`。
- `run_stock_reference_sync()`：把 `seed_us_static()` 換成 `sync_us_from_sec()`，回傳 dict 的 `us` 欄維持。
- 移除 `seed_us_static()`（已被取代）。

### 3. 測試 `tests/test_stock_reference_sync.py`（新）

stub `core.sec.fetch_company_tickers`（monkeypatch）回一小份含 INTC / NVDA 的 payload，搭配 conftest 的 in-memory DB：

- `normalize("intc") == ("INTC", "US")`（大小寫不敏感，名冊新檔可對到）
- `normalize("輝達") == ("NVDA", "US")`（中文別名 overlay 仍生效）
- INTC 的 `canonical_name` 來自 SEC `title`（如 "Intel Corp."）
- `sync_us_from_sec()` 回傳的筆數 == payload 檔數

## 影響的因果鏈（修好後）

`intc` → `normalize` → `(INTC, US)` → `extracted_trades.ticker = "INTC"` → 進入 `list_tracking_targets` → `compute_window` 用 `_yf_symbols("INTC","US") = ["INTC"]` → yfinance 取價 → 績效面板正常、chip 顯示公司名。

## 取捨與風險

- **離線保證消失**：移除靜態清單後，全新 DB 的美股列要等 `stock_ref_sync`（每日 07:00 或手動觸發）跑過才會有。屬 upsert，單次失敗下次自癒。台股本來就依賴 FinMind 網路，一致。
- **SEC 抓取失敗**：沿用既有慣例（finmind 也未逐步包 try）；交由 scheduler job 層記錄例外。`sync_us_from_sec` 失敗會中止該次 `run_stock_reference_sync`，但既有美股列仍留在 DB（upsert 不刪舊資料）。
- **名冊缺漏**：少數 ETF / 冷門 ADR 不在 SEC 名冊 → 維持 `(None, None)`，與現狀同，只是數量大減。
- **代號類別後綴**：SEC 用 `BRK-B` 形式，yfinance 亦同，無需轉換。
- **市場碰撞**：美股英文代號 vs 台股數字代號，`(market, ticker)` 不衝突。
