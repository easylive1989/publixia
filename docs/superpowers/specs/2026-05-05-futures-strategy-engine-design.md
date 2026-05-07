# Futures Strategy Engine — Design

- 日期：2026-05-05
- 狀態：草案 (待 implementation plan)
- 影響範圍：`backend/`、`frontend/`、`admin/`、`docs/`、`tests/`

## 0. 摘要

在現有 stock-dashboard 之上新增一個受權限控管的子系統 **Futures Strategy Engine (FSE)**，讓「有權限」的使用者：

1. 用前端表單建立台指期策略（進場條件、停利條件、停損條件），條件用一份 declarative DSL 表達；
2. 啟用即時通知後，每天 14:00 期貨日線 fetcher 寫完 → 評估策略 → 訊號 push 到使用者個人 Discord webhook；
3. 對策略跑歷史回測，享 Backtrader 內建 analyzer（Sharpe、drawdown、勝率…）；
4. 系統不追蹤使用者實際買進價格，使用 hypothetical position state machine（idle → pending_entry → open → pending_exit → idle）；
5. 權限與 webhook 由 admin 透過既有 `admin/` 互動式 CLI 管理。

## 1. 設計決策快覽

| 主題 | 選擇 | 為什麼 |
|---|---|---|
| 評估模式 | hypothetical state machine（A） | 對應「不追使用者買價」+「假想持倉」需求；停利停損只在場內評估 |
| 回測引擎 | Backtrader（DSL → 動態組 Strategy class）（Y2） | 不重造 backtest engine、享內建 analyzer；DSL UI 仍可給非程式員使用者 |
| 條件範圍 | TX OHLCV + 衍生技術指標（B） | 涵蓋 80% 常見策略；單 datafeed 結構單純；未來可擴跨指標 |
| 方向 | 多 / 空（a2） | 策略宣告自身方向，PnL 反向乘 |
| 商品 | TX / MTX / TMF（b2） | 新增 fetcher（與 TX 同 FinMind dataset） |
| 部位 | 固定 N 口（c1） | 直觀；不引入 leverage / margin 計算 |
| 評估觸發 | fetcher 末尾，所有商品 fan-in（4a1） | 跟既有 `check_alerts` pattern 一致，daily-only 不違反 CLAUDE.md |
| 進出場成交價 | next-bar open（4c2） | 避免 lookahead bias；Backtrader 預設一致 |
| 進場當天不評估出場 | 是（4b2） | 避免同根 K 棒進出 |
| 同日停利停損衝突 | 都用 close 判斷 → 不會同時（9c1） | 跟 daily snapshot 一致 |
| 出場後 cooldown | 無（9b3） | 簡單；噪音由策略本身負責 |
| 策略擁有權 | per-user，互不共享（5a1） | 模型最乾淨；fork / 共享是 over-engineering |
| 通知通道 | per-user Discord webhook（5b2） | 避免訊號互擾；admin CLI 設定 |
| 沒設 webhook | 不能啟用即時通知（9a1） | 邊界最清楚 |
| 評估資料不足 | 跳過該日（9b1） | 保守，不誤觸發 |
| 修改策略 | 在場內時條件唯讀；元資料可改（9d3） | 條件變了 = 策略本質變了 |
| Runtime error | 自動停用 + 雙通道通知（user + ops）（9f） | 跟現有 alert 模式一致 |
| 刪除策略 | 硬刪 + cascade signals（9g1） | 使用者自己負責 |
| 啟用前是否強制回測 | 否（7e1） | 使用者自負策略品質 |
| 回測結果是否存 DB | 否（7d1） | 跑得快，存了反而吵 |

## 2. 架構

```
┌─────────────────────────────────────────────────────┐
│  Frontend (React)                                   │
│  /strategies (gated by can_use_strategy)            │
│  - List / Edit / Backtest pages                     │
│  - Condition builder (DSL UI)                       │
└──────────────────┬──────────────────────────────────┘
                   │ /api/strategies/* (token-gated + permission-gated)
┌──────────────────▼──────────────────────────────────┐
│  Backend (FastAPI)                                  │
│                                                     │
│  api/routes/strategies.py     ←  CRUD + backtest    │
│  services/strategy_engine.py  ←  state-machine eval │
│  services/strategy_dsl.py     ←  DSL parse / validate│
│  services/strategy_backtest.py ← DSL → BT Strategy  │
│  services/strategy_notifier.py ← per-user webhook   │
│  repositories/strategies.py   ←  SQLite access      │
│                                                     │
│  fetchers/futures.py (擴充)                         │
│   ├─ fetch_tw_futures() 抓 TX (既有)                │
│   ├─ fetch_tw_futures_mtx() 新增                    │
│   └─ fetch_tw_futures_tmf() 新增                    │
│   尾端呼叫 strategy_engine.on_futures_data_written()│
│                                                     │
│  admin/__main__.py (擴充權限 / webhook 指令)        │
└──────────────────┬──────────────────────────────────┘
                   │
┌──────────────────▼──────────────────────────────────┐
│  SQLite                                             │
│  + strategies                                       │
│  + strategy_signals                                 │
│  + futures_daily (TX/MTX/TMF 共用既有表)            │
│  + users.can_use_strategy                           │
│  + users.discord_webhook_url                        │
└─────────────────────────────────────────────────────┘
```

### 核心資料流

1. 每日 14:00 TST，TX/MTX/TMF 三個 fetcher 寫入 `futures_daily`；
2. 每個 fetcher 末尾 call `on_futures_data_written(contract, date)`；fan-in barrier 確保三者都寫好才呼叫一次 `evaluate_all(date)`；
3. `evaluate_all` 對每個 `notify_enabled=1` 策略 → 執行 state machine → 寫 `strategy_signals` + 更新 `strategies` 上的持倉欄位 → 呼叫 notifier；
4. notifier 取出 user webhook → 透過 `core.discord.send_to_discord(payload, webhook_url=...)` 推送；無 webhook 直接 skip + log；
5. 回測：使用者按按鈕 → backend 同步跑 Backtrader Cerebro → 回傳 `BacktestResult` JSON。

## 3. 資料模型

新 migration：`backend/db/migrations/0008_strategies.sql`

### 3.1 `users` 表擴充

```sql
ALTER TABLE users ADD COLUMN can_use_strategy INTEGER NOT NULL DEFAULT 0;
ALTER TABLE users ADD COLUMN discord_webhook_url TEXT;
```

`discord_webhook_url` 以 plaintext 儲存（與既有 `.env` 模型一致）。Admin CLI 顯示時遮罩中段。

### 3.2 `strategies` 表

```sql
CREATE TABLE strategies (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id                  INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name                     TEXT    NOT NULL,
    direction                TEXT    NOT NULL CHECK (direction IN ('long','short')),
    contract                 TEXT    NOT NULL CHECK (contract  IN ('TX','MTX','TMF')),
    contract_size            INTEGER NOT NULL DEFAULT 1,
    max_hold_days            INTEGER,
    entry_dsl                TEXT    NOT NULL,
    take_profit_dsl          TEXT    NOT NULL,
    stop_loss_dsl            TEXT    NOT NULL,
    notify_enabled           INTEGER NOT NULL DEFAULT 0,

    -- State machine
    state                    TEXT    NOT NULL DEFAULT 'idle'
                              CHECK (state IN ('idle','pending_entry','open','pending_exit')),
    entry_signal_date        TEXT,
    entry_fill_date          TEXT,
    entry_fill_price         REAL,
    pending_exit_kind        TEXT,        -- TAKE_PROFIT / STOP_LOSS / TIMEOUT
    pending_exit_signal_date TEXT,

    -- Runtime error
    last_error               TEXT,
    last_error_at            TEXT,

    created_at               TEXT NOT NULL,
    updated_at               TEXT NOT NULL,
    UNIQUE(user_id, name)
);

CREATE INDEX idx_strategies_user        ON strategies(user_id);
CREATE INDEX idx_strategies_notify_open ON strategies(notify_enabled, state)
                                            WHERE notify_enabled = 1;
```

持倉狀態內嵌；同一時間最多一個 hypothetical position。歷史持倉由 `strategy_signals` 中 `ENTRY_FILLED ↔ EXIT_FILLED` 配對重建。

### 3.3 `strategy_signals` 表

```sql
CREATE TABLE strategy_signals (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    strategy_id     INTEGER NOT NULL REFERENCES strategies(id) ON DELETE CASCADE,
    kind            TEXT    NOT NULL CHECK (kind IN (
                      'ENTRY_SIGNAL', 'ENTRY_FILLED',
                      'EXIT_SIGNAL',  'EXIT_FILLED',
                      'MANUAL_RESET', 'RUNTIME_ERROR'
                    )),
    signal_date     TEXT    NOT NULL,
    close_at_signal REAL,
    fill_price      REAL,
    exit_reason     TEXT,
    pnl_points      REAL,
    pnl_amount      REAL,
    message         TEXT,
    created_at      TEXT NOT NULL
);

CREATE INDEX idx_signals_strategy_date ON strategy_signals(strategy_id, signal_date DESC);
```

### 3.4 `futures_daily` 既有，無 schema 改動

`symbol` 欄位本來就支援多商品；新增 fetchers 用同表寫入 MTX / TMF 即可。`save_futures_daily_rows` 已是 upsert，安全。

### 3.5 持倉生命週期（state machine）

```
                  ┌─ 進場條件成立 (T)：寫 ENTRY_SIGNAL，state=pending_entry，發 Discord
                  │
                  ▼
[idle] ─────► [pending_entry]
                  │
                  │ T+1 fetcher 寫完當日日線 → 取 open
                  │ 寫 ENTRY_FILLED + entry_fill_price，不發 Discord
                  ▼
              [open]
                  │
                  │ 停利 / 停損 / 達 max-hold-days (E)
                  │ 寫 EXIT_SIGNAL + pending_exit_*，發 Discord
                  ▼
              [pending_exit]
                  │
                  │ E+1 fetcher 寫完 → 取 open → 算 PnL
                  │ 寫 EXIT_FILLED，不發 Discord
                  ▼
              [idle]   ← 持倉週期完成
```

Discord 通知時機：只在 `ENTRY_SIGNAL` 與 `EXIT_SIGNAL` 發送（兩則）；`*_FILLED` 只寫 DB。

## 4. DSL

DSL 為純 JSON，可序列化、即時 evaluator 直接執行、能無歧義翻譯到 Backtrader Strategy class。

### 4.1 進場條件 — `entry_dsl`

```json
{
  "version": 1,
  "all": [
    { "left": <expr>, "op": <operator>, "right": <expr>, "n": <int?> }
  ]
}
```

只支援 AND；UI 至少要求 1 條。

### 4.2 表達式類型

| 類型 | JSON | 意義 |
|---|---|---|
| 欄位 | `{"field":"close"}` | OHLCV 之一：`close / open / high / low / volume` |
| 指標 | `{"indicator":"sma","n":20}` | 衍生指標（見下） |
| 常數 | `{"const": 17000}` | 數字字面值 |
| 進場價 | `{"var":"entry_price"}` | 持倉中的進場成交價（**僅停利/停損 advanced 模式可用**） |

**支援的指標**（B 範圍，全部對應 Backtrader 內建）：

| indicator | 參數 | output 選項 | Backtrader 對應 |
|---|---|---|---|
| `sma` | `n` | — | `bt.ind.SMA(period=n)` |
| `ema` | `n` | — | `bt.ind.EMA` |
| `rsi` | `n` | — | `bt.ind.RSI` |
| `macd` | `fast,slow,signal` | `macd / signal / hist` | `bt.ind.MACD` |
| `bbands` | `n,k` | `upper / middle / lower` | `bt.ind.BollingerBands` |
| `atr` | `n` | — | `bt.ind.ATR` |
| `kd` | `n` | `k / d` | `bt.ind.Stochastic` |
| `highest` | `n` | — (固定取 high) | `bt.ind.Highest` |
| `lowest` | `n` | — (固定取 low) | `bt.ind.Lowest` |
| `change_pct` | `n` | — | 自訂：`(close - close[-n]) / close[-n] * 100` |

預設值：`rsi.n=14`、`macd=(12,26,9)`、`bbands=(20,2)`、`atr=14`、`kd.n=9`。

### 4.3 運算子

| op | 意義 | 備註 |
|---|---|---|
| `gt / gte / lt / lte` | 數值比較 | 最常見 |
| `cross_above` | 今日 left > right、昨日 left ≤ right | 黃金交叉；Backtrader 用 `bt.ind.CrossOver` |
| `cross_below` | 今日 left < right、昨日 left ≥ right | 死亡交叉 |
| `streak_above` | 連 N 日 left ≥ right | 需 `n` 欄位 |
| `streak_below` | 連 N 日 left ≤ right | 需 `n` 欄位 |

### 4.4 停利 / 停損 — 三模式

`take_profit_dsl` / `stop_loss_dsl` 用 `type` tag 三選一：

```jsonc
// Simple 1 — 百分比 (UI 預設)
{ "version": 1, "type": "pct",    "value": 2.0 }    // +2%

// Simple 2 — 絕對點數
{ "version": 1, "type": "points", "value": 50 }     // +50 點

// Advanced — 跟進場條件相同的 DSL，可用 entry_price 變數
{ "version": 1, "type": "dsl",
  "all": [
    { "left": {"field":"close"}, "op": "lt", "right": {"indicator":"sma","n":20} }
  ]
}
```

`direction` 影響 simple 模式語意：long 策略 `pct: 2.0` = entry × 1.02、`points: 50` = entry + 50；short 反向。停損同理。

### 4.5 範例

**例 1：黃金交叉進場 + 2% 停利 + 1% 停損**

```jsonc
// entry_dsl
{ "version": 1, "all": [
  { "left": {"indicator":"sma","n":5}, "op": "cross_above",
    "right": {"indicator":"sma","n":20} }
]}
// take_profit_dsl
{ "version": 1, "type": "pct", "value": 2.0 }
// stop_loss_dsl
{ "version": 1, "type": "pct", "value": 1.0 }
```

**例 2：RSI 超賣 + 布林下軌反轉 + 跌破 SMA(20) 出場**

```jsonc
// entry_dsl
{ "version": 1, "all": [
  { "left": {"indicator":"rsi","n":14}, "op": "lt", "right": {"const": 30} },
  { "left": {"field":"close"}, "op": "lt",
    "right": {"indicator":"bbands","n":20,"k":2.0,"output":"lower"} }
]}
// stop_loss_dsl (advanced)
{ "version": 1, "type": "dsl", "all": [
  { "left": {"field":"close"}, "op": "lt", "right": {"indicator":"sma","n":20} }
]}
```

**例 3：突破前 20 日高 + 連 3 日量能放大**

```jsonc
{ "version": 1, "all": [
  { "left": {"field":"close"}, "op": "gt",
    "right": {"indicator":"highest","n":20} },
  { "left": {"field":"volume"}, "op": "streak_above", "n": 3,
    "right": {"indicator":"sma","n":10} }
]}
```

### 4.6 Validation

`services/strategy_dsl.py::validate(dsl)` 在寫入時做：

1. JSON schema 合法（pydantic model）；
2. 指標參數合理範圍（`n ≥ 1`、`bbands.k > 0`…）；
3. 停利停損 advanced 模式才能用 `{"var":"entry_price"}`；進場條件用 → 422；
4. `streak_*` 必有 `n`、其他 op 不能有 `n`；
5. **Backtrader-translatability check**：對 dummy datafeed 跑一次翻譯，翻不出來 → 422。

寫入失敗回 422，body 含具體錯誤欄位路徑，UI 高亮。

### 4.7 即時 vs 回測一致性

兩條路徑共用同一份 `compute_indicator()`（即時直接呼叫；回測 map 到 `bt.ind.*`）。Conformance test：對 50 個 randomized DSL，分別用即時 evaluator 與 Backtrader 跑同一段歷史資料，斷言訊號日完全一致。

## 5. 評估引擎

`services/strategy_engine.py`。

### 5.1 觸發 — fan-in barrier

每個期貨 fetcher 末尾呼叫：

```python
on_futures_data_written(contract: str, date: str)
```

內部維護一個 `(date, set_of_contracts_done)` 結構（記憶體 + 啟動時讀 `futures_daily` recover）；三商品都寫好才 call `evaluate_all(date)`。避免 race（fetcher 並行）造成重複觸發或 missed run。

**Implementation deviation from the barrier model:** P3 ships a simpler fan-out instead of a true fan-in barrier. Each fetcher's tail-call `on_futures_data_written(contract, date)` independently iterates only the strategies bound to that contract — strategy `s` with `s.contract = "TX"` won't fire from the MTX fetcher's hook, and a TX fetcher failure leaves MTX/TMF strategies untouched. Functionally equivalent to the barrier (each strategy still evaluates exactly once per day on its own contract's fresh bar) and avoids tracking which fetchers have completed.

### 5.2 `evaluate_all(date)`

```python
def evaluate_all(today: str) -> None:
    for s in list_enabled_strategies():
        try:
            evaluate_one(s, today)
        except Exception as e:
            mark_strategy_error(s.id, str(e))
            notify_runtime_error(s, e)
```

單一策略錯了不影響其他（try/except + `last_error` + 自動 disable）。

### 5.3 `evaluate_one(s, today)` 依 state 分支

```python
def evaluate_one(s: Strategy, today: str) -> None:
    today_bar = get_futures_bar(s.contract, today)
    if today_bar is None:           # fetcher 失敗或當日尚未寫入 → 跳過
        return

    if s.state == 'idle':
        _try_entry(s, today_bar)
    elif s.state == 'pending_entry':
        _fill_entry(s, today_bar)   # 進場當天不評估出場（4b2）
    elif s.state == 'open':
        _try_exit(s, today_bar)
    elif s.state == 'pending_exit':
        _fill_exit(s, today_bar)
        _try_entry(s, today_bar)    # 9b3 無 cooldown，同日可再進
```

### 5.4 `_try_entry`

歷史窗 = `_required_history_for(s)`（DSL 中最大 n + 警示前 1 根）。`run_dsl` 回傳 `True/False/None`，`None` 表資料不足 → log + skip。觸發 → 寫 `ENTRY_SIGNAL`、`state='pending_entry'`、發 Discord。

### 5.5 `_fill_entry`

寫 `ENTRY_FILLED + fill_price=today_bar.open`、`state='open'`、不發 Discord。

### 5.6 `_try_exit` — 順序：stop_loss → take_profit → max_hold_days

`held = count_trading_days(s.contract, s.entry_signal_date, today_bar.date)` 不含 entry_signal_date 當日（signal 日為 day 0、fill 當日 day 1、再下一日 day 2…）。`max_hold_days = N` 表示「進場 signal 後第 N 個交易日」當日就觸發 TIMEOUT。

> **為什麼用 entry_signal_date 而不是 entry_fill_date：** Backtrader 的 `_entry_bar_idx` 是設定在 signal 那一根 K 棒（fill 還沒發生），其 `held = len(self) - _entry_bar_idx` 因此也以 signal 為起點。為了讓 live 引擎與回測對相同 fixture 產生相同 trade timeline（spec §4.7 的 round-trip 一致性保證），live 評估也用 signal_date。P3 conformance 測試 (`tests/test_strategy_engine_conformance.py`) 對 50 個 random DSL 驗證了這個對齊。

```python
if dsl_check_exit(s.stop_loss_dsl,   ...): return _emit_exit(s, today, 'STOP_LOSS')
if dsl_check_exit(s.take_profit_dsl, ...): return _emit_exit(s, today, 'TAKE_PROFIT')
if s.max_hold_days is not None:
    held = count_trading_days(s.contract, s.entry_signal_date, today_bar.date)
    if held >= s.max_hold_days:
        return _emit_exit(s, today, 'TIMEOUT')
```

`max_hold_days` 用 trading days（從 `futures_daily` 數），不是 calendar days。`dsl_check_exit` 處理 pct / points / advanced 三模式。

### 5.7 `_fill_exit`

```python
fill = today_bar.open
pnl_points = (fill - s.entry_fill_price) if s.direction=='long' \
             else (s.entry_fill_price - fill)
pnl_amount = pnl_points * MULTIPLIER[s.contract] * s.contract_size
write_signal(s, kind='EXIT_FILLED', fill_price=fill,
             exit_reason=s.pending_exit_kind,
             pnl_points=pnl_points, pnl_amount=pnl_amount)
update_state(s, state='idle', ...)  # 清所有 entry/pending 欄位

MULTIPLIER = {'TX': 200, 'MTX': 50, 'TMF': 10}
```

### 5.8 `run_dsl(dsl, history)`

純函式；對每個 condition 用 `compute_expr(expr, history)` 取得 left / right 當日值（或 `streak_*` 的歷史 list），照 op 比較。`compute_expr` 對 indicator 用 lazy cache（同一次 `evaluate_one` call 內 SMA(20) 算過就 reuse）。

### 5.9 手動操作

- `POST /api/strategies/:id/force_close`：state ∈ {open, pending_exit} 才允許；用最新 close 當假想成交、寫 `EXIT_FILLED + reason='MANUAL_RESET'`、state→idle、發通知。
- `POST /api/strategies/:id/reset`：刪所有 signals + state→idle + 清所有 entry/pending 欄位 + 清 `last_error`。不發通知。

### 5.10 Concurrency

策略全寫進 SQLite，`evaluate_all` 在單一 worker 執行，無 race。每個 `evaluate_one` 內所有 DB 寫入用單一 transaction 保證原子。

### 5.11 啟用前資料量檢查

`POST /api/strategies/:id/enable` 內檢查：DB 內該 contract `futures_daily` 數 ≥ `_required_history_for(s)`。否則 422 + 訊息「需更多歷史，請等明天 fetcher 補完」。

## 6. Backtrader 整合

`services/strategy_backtest.py`。

### 6.1 公開介面

```python
def run_backtest(
    strategy: Strategy,
    start_date: str,
    end_date: str,
    contract_override: str | None = None,
    contract_size_override: int | None = None,
) -> BacktestResult: ...
```

### 6.2 Datafeed

從 `futures_daily` 讀指定 contract / 區間，轉 pandas DataFrame，餵 `bt.feeds.PandasData`。

### 6.3 動態組 Strategy class

```python
def _build_bt_strategy_class(s: Strategy) -> type[bt.Strategy]:
    class _GeneratedStrategy(bt.Strategy):
        params = (('direction', s.direction),
                  ('contract_size', s.contract_size),
                  ('max_hold_days', s.max_hold_days))

        def __init__(self):
            self._ind = _materialize_indicators(s, self.data)
            self._entry_bar_idx = None
            self._last_exit_reason = None

        def next(self):
            if self.position:
                self._maybe_exit()
            else:
                self._maybe_entry()

        def _maybe_entry(self):
            if _eval_dsl_bt(s.entry_dsl, self.data, self._ind):
                size = s.contract_size
                if s.direction == 'long':
                    self.buy(size=size, exectype=bt.Order.Market)
                else:
                    self.sell(size=size, exectype=bt.Order.Market)
                self._entry_bar_idx = len(self)

        def _maybe_exit(self):
            entry_price = self.position.price
            for kind, dsl in (('STOP_LOSS', s.stop_loss_dsl),
                              ('TAKE_PROFIT', s.take_profit_dsl)):
                if _eval_exit_bt(dsl, entry_price, self.data, self._ind, s.direction):
                    self._last_exit_reason = kind
                    return self.close(exectype=bt.Order.Market)
            if s.max_hold_days is not None:
                held = len(self) - self._entry_bar_idx
                if held >= s.max_hold_days:
                    self._last_exit_reason = 'TIMEOUT'
                    return self.close(exectype=bt.Order.Market)

        def notify_trade(self, trade):
            if trade.isclosed:
                self._trade_log.append({
                    'entry_date': bt.num2date(trade.dtopen).date(),
                    'exit_date':  bt.num2date(trade.dtclose).date(),
                    'pnl':        trade.pnlcomm,
                    'reason':     self._last_exit_reason,
                })
    return _GeneratedStrategy
```

`_materialize_indicators` 走訪 DSL 的所有 `expr` 節點，把 unique indicator 註冊成 bt indicator；`cross_above` 用 `bt.ind.CrossOver` 預先建好；`streak_above(n)` 在 `next()` 內用 `all(left[-i] >= right[-i] for i in range(n))` 檢查。

### 6.4 Cerebro 設定

```python
cerebro = bt.Cerebro()
cerebro.adddata(datafeed)
cerebro.addstrategy(strategy_class)
cerebro.broker.set_cash(10_000_000)
cerebro.broker.setcommission(commission=0.0, margin=False,
                             mult=MULTIPLIER[contract])
cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name='trades')
cerebro.addanalyzer(bt.analyzers.DrawDown,      _name='dd')
cerebro.addanalyzer(bt.analyzers.SharpeRatio,   _name='sharpe',
                    timeframe=bt.TimeFrame.Days, riskfreerate=0.0)
cerebro.addanalyzer(bt.analyzers.Returns,       _name='returns')
```

預設 Market order 在 next-bar open 成交（對應 4c2）。手續費 / 滑價暫留 0。

### 6.5 結果格式

```python
@dataclass
class Trade:
    entry_signal_date: date
    entry_fill_date:   date
    entry_fill_price:  float
    exit_signal_date:  date
    exit_fill_date:    date
    exit_fill_price:   float
    exit_reason:       Literal['TAKE_PROFIT','STOP_LOSS','TIMEOUT']
    held_days:         int
    pnl_points:        float
    pnl_amount:        float

@dataclass
class Summary:
    total_pnl_amount:  float
    win_rate:          float
    avg_win_points:    float
    avg_loss_points:   float
    profit_factor:     float
    max_drawdown_amt:  float
    max_drawdown_pct:  float
    sharpe:            float | None
    n_trades:          int
    avg_hold_days:     float

@dataclass
class BacktestResult:
    trades:       list[Trade]
    summary:      Summary
    equity_curve: list[EquityPoint]   # [(date, cumulative_pnl_amount), ...]
    benchmark:    list[EquityPoint]   # buy & hold 同期間
    warnings:     list[str]
```

### 6.6 性能

5 年 TX 日線 ≈ 1250 根，Cerebro 跑通常 < 1 秒；同步呼叫 OK。20 年 ≈ 5000 根，仍 < 5 秒。

### 6.7 Failure mode

| 失敗 | 行為 |
|---|---|
| DSL validate 失敗 | API 拒絕儲存（422） |
| 區間內資料不足 | `BacktestResult.warnings` 加一條，回測仍跑（trim 到實際範圍） |
| Cerebro runtime exception | API 回 500 + log + Discord ops alert |

## 7. 通知

`services/strategy_notifier.py`。

### 7.1 `core/discord.py` 擴充

```python
def send_to_discord(payload: dict, *, webhook_url: str | None = None) -> bool:
    url = webhook_url or settings.discord_webhook_url.get_secret_value().strip()
    if not url:
        return False
    ...
```

向下相容；現有 `alert_notifier` / `token_service` 不變。

### 7.2 通知時機

只在 `ENTRY_SIGNAL` 與 `EXIT_SIGNAL` 發 Discord；`*_FILLED` 只寫 DB（前端訊號歷史看得到）。

### 7.3 Embed payload

#### `ENTRY_SIGNAL`

```jsonc
{
  "embeds": [{
    "title": "📈 進場訊號 — [策略名]",
    "description": "**[user 名]** 的策略觸發進場條件，**明日 open 假想進場**。",
    "color": 0xE74C3C,
    "fields": [
      { "name": "方向 / 商品 / 口數", "value": "多 / TX / 1", "inline": true },
      { "name": "訊號當日 close",     "value": "17,250",    "inline": true },
      { "name": "進場條件",
        "value": "SMA(5) cross_above SMA(20)", "inline": false }
    ],
    "footer": { "text": "Strategy #42 · 2026-05-05" },
    "timestamp": "2026-05-05T05:45:00Z"
  }]
}
```

進場條件文字由 `dsl_to_text(dsl)` 產生。

#### `EXIT_SIGNAL`

依 `exit_reason` 改 title icon / color：

| reason | icon | color | 文字 |
|---|---|---|---|
| `TAKE_PROFIT` | 💰 | 0x2ECC71 | 停利訊號 |
| `STOP_LOSS` | 🛑 | 0xE67E22 | 停損訊號 |
| `TIMEOUT` | ⏰ | 0x95A5A6 | 持倉到期 |

Fields：方向 / 商品 / 口數、訊號當日 close、進場價 + 進場日、預估 PnL（標註「以當日 close 估算，實際以明日 open 結算」）、已持倉 N 個交易日、出場條件文字。

### 7.4 Runtime error — 雙通道

```python
def notify_runtime_error(s: Strategy, e: Exception) -> None:
    user = get_user(s.user_id)
    if user.discord_webhook_url:
        send_to_discord(_user_err_embed(s, e),
                        webhook_url=user.discord_webhook_url)
    send_to_discord(_ops_err_embed(s, e))   # 系統全域 webhook
```

User-facing：簡短錯誤訊息 + 「即時通知已暫停，請編輯後重新啟用」。
Ops-facing：完整 traceback + user_id + strategy_id。

**Signal-history surfacing (P6):** the runtime error is also written as a `kind=RUNTIME_ERROR` row to `strategy_signals` so the user-facing SignalHistoryTable shows "❌ 執行錯誤" alongside the actual signal events. P6 closed this loop; before P6 the only surface was the `strategies.last_error` column visible only on the edit page.

### 7.5 啟用前 webhook 檢查

`POST /api/strategies/:id/enable` 內：

```python
if not user.can_use_strategy:    raise HTTPException(403, "...")
if not user.discord_webhook_url: raise HTTPException(422, "請聯繫 admin 設定 Discord webhook 後再啟用")
# 加上 5.11 的歷史資料量檢查
```

UI 在前端先用 `/api/me` disable toggle，避免使用者點到才知道；422 是 belt-and-suspenders。

### 7.6 訊號歷史保留

策略刪除 → cascade 刪 signals。實作上把 `strategy_signals` 加進既有 `purge_old_data`（Sunday 00:00 job），保留 3 年（與 indicator/stocks 同政策）。

## 8. API + Admin CLI

### 8.1 API endpoints

`backend/api/routes/strategies.py`。Token 走既有 `require_user` dependency；策略相關再疊一層：

```python
def require_strategy_permission(user = Depends(require_user)) -> User:
    if not user.can_use_strategy:
        raise HTTPException(403, "no strategy permission")
    return user
```

| Method | Path | 用途 | 權限 |
|---|---|---|---|
| GET  | `/api/me` | `{user_id, name, can_use_strategy, has_webhook}` | token |
| GET  | `/api/strategies` | 列當前 user 的策略 | strategy |
| GET  | `/api/strategies/dsl/schema` | DSL metadata | strategy |
| POST | `/api/strategies` | 建策略 | strategy |
| GET  | `/api/strategies/{id}` | 單一策略 | strategy + ownership |
| PATCH| `/api/strategies/{id}` | 更新（場內時 DSL 唯讀） | strategy + ownership |
| DELETE | `/api/strategies/{id}` | 硬刪 + cascade | strategy + ownership |
| POST | `/api/strategies/{id}/enable` | 啟用即時通知 | strategy + ownership |
| POST | `/api/strategies/{id}/disable` | 停用 | strategy + ownership |
| POST | `/api/strategies/{id}/force_close` | 強制平倉 | strategy + ownership |
| POST | `/api/strategies/{id}/reset` | 重置策略 | strategy + ownership |
| GET  | `/api/strategies/{id}/signals?limit=50` | 訊號歷史 | strategy + ownership |
| POST | `/api/strategies/{id}/backtest` | 同步跑回測 | strategy + ownership |

`ownership` 失敗 → 404（避免 id enumeration）。

### 8.2 Pydantic schemas（節錄）

```python
class DSLCondition(BaseModel):
    left:  ExprNode
    op:    Literal['gt','gte','lt','lte','cross_above','cross_below',
                   'streak_above','streak_below']
    right: ExprNode
    n:     int | None = None

class EntryDSL(BaseModel):
    version: Literal[1] = 1
    all:     list[DSLCondition] = Field(min_items=1)

class ExitDSL_Pct(BaseModel):
    version: Literal[1] = 1
    type:    Literal['pct']
    value:   float = Field(gt=0)

class ExitDSL_Points(BaseModel):
    version: Literal[1] = 1
    type:    Literal['points']
    value:   float = Field(gt=0)

class ExitDSL_Advanced(BaseModel):
    version: Literal[1] = 1
    type:    Literal['dsl']
    all:     list[DSLCondition] = Field(min_items=1)

ExitDSL = Annotated[Union[ExitDSL_Pct, ExitDSL_Points, ExitDSL_Advanced],
                    Field(discriminator='type')]

class StrategyCreate(BaseModel):
    name:            str = Field(min_length=1, max_length=80)
    direction:       Literal['long','short']
    contract:        Literal['TX','MTX','TMF']
    contract_size:   int = Field(ge=1, le=1000)
    max_hold_days:   int | None = Field(default=None, ge=1)
    entry_dsl:       EntryDSL
    take_profit_dsl: ExitDSL
    stop_loss_dsl:   ExitDSL
```

### 8.3 Admin CLI 改動

`admin/__main__.py` 主畫面 `List users` 表格新增兩欄：`Strategy` (✓/✗)、`Webhook` (set/—，set 時遮罩中段)。

`Manage user` 子選單新增三個動作：

```
Manage user: paul
  1) Refresh token
  2) Revoke active token
  3) Toggle strategy permission       ← 新
  4) Set Discord webhook URL          ← 新
  5) Clear Discord webhook URL        ← 新
  6) Back
```

- **Toggle**：翻 boolean，CLI 在 terminal 印出操作紀錄（與既有 token-revoke 同風格，無專門 audit log 表）。
- **Set webhook**：驗證格式（`https://discord(?:app)?.com/api/webhooks/.+/.+`）→ 寫入 → 立即發 test message；失敗 rollback。
- **Clear**：set NULL；若該 user 有 `notify_enabled=1` 策略，先警示「會 disable N 個策略，繼續？(y/N)」。

`admin/ops.py` 新增：

```python
def set_strategy_permission(user_id: int, granted: bool) -> None
def set_user_webhook(user_id: int, url: str | None) -> None
def revoke_user_webhook_with_disable(user_id: int) -> int
```

## 9. 前端

### 9.1 組件樹

```
src/
├── pages/
│   ├── StrategiesListPage.tsx
│   ├── StrategyEditPage.tsx
│   └── StrategyBacktestPanel.tsx        # 編輯頁的 tab
├── components/strategy/
│   ├── ConditionBuilder.tsx
│   ├── ExitConditionEditor.tsx
│   ├── ExpressionPicker.tsx
│   ├── OperatorSelect.tsx
│   ├── PositionStatusCard.tsx
│   ├── SignalHistoryTable.tsx
│   ├── BacktestForm.tsx
│   ├── BacktestSummaryCards.tsx
│   ├── BacktestTradesTable.tsx
│   └── EquityCurveChart.tsx
├── lib/
│   ├── strategyApi.ts
│   └── strategyDsl.ts
├── hooks/
│   ├── useMe.ts
│   └── useStrategy.ts
└── router.tsx (擴充 /strategies/*)
```

### 9.2 Gating

`useMe()` 在 app 啟動拉一次 `/api/me`：

- header 導覽列：`{me?.can_use_strategy && <Link to="/strategies">策略</Link>}`
- `/strategies/*` route 自身 gate：未授權 render `<NotAuthorized/>`，不打後續 API
- 啟用通知 toggle：`disabled={!me.has_webhook}` + tooltip

### 9.3 Condition builder 互動

- 每行：`<ExpressionPicker /> <OperatorSelect /> <ExpressionPicker />`，運算子是 `streak_*` 時旁邊出現 `n` 欄
- 「+ 新增條件」按鈕加一行（最多 5 行；超過警示但不擋）
- 即時前端 validate（zod schema 鏡像後端 pydantic）
- 後端 422 帶 `detail.field_path` → 前端高亮對應行

### 9.4 圖表

`EquityCurveChart` 與 buy & hold 疊兩條線；用 Recharts（既有 sparkline 同 lib，`recharts ^3.8.1` 已在 `package.json` 中），不新增 dep。

## 10. 測試策略

`tests/strategies/`：

| 檔案 | 範圍 |
|---|---|
| `test_routes.py` | CRUD、enable/disable 422、ownership 404 |
| `test_engine.py` | state machine 各 transition + max_hold_days + 失敗策略隔離 |
| `test_dsl.py` | DSL validate edge cases（streak_* 沒 n、advanced 模式 entry_price 在 entry_dsl） |
| `test_dsl_conformance.py` | 50 randomized DSL 即時 vs Backtrader 一致性（property-based） |
| `test_backtest.py` | fixture data + 預期 trade list snapshot |
| `test_admin_cli.py` | 權限 toggle、webhook set/clear、cascade-disable |

前端：`frontend/src/components/strategy/__tests__/` vitest，至少測 ConditionBuilder add/remove row、ExitConditionEditor 三模式切換、useMe gating。

## 11. 部署

### 11.1 Backend dependencies

`backend/requirements.txt` 新增：

```
backtrader>=1.9.78.123
pandas>=2.0
numpy>=1.24
```

注意事項：

- Backtrader 已多年無新 release（最後 1.9.78.123, 2023）；Python 3.10+ 可跑，新版 numpy 出 deprecation warning 時 pin 即可。
- Backtrader import matplotlib，但只有畫圖才會用；伺服器只跑 cerebro 不畫圖，理論上不需要 runtime；視 Python 版本決定要不要裝 matplotlib。
- Phase 6 第一步先驗證 `python -c "import backtrader"` 在 VPS Python 版本能成功。

### 11.2 Migration 與 service restart

VPS 既有 deploy-backend.yml 流程：rsync 後 VPS 端執行 `.venv/bin/pip install -q -r requirements.txt` → `systemctl restart stock-dashboard.service` → `init_db()` 跑 migration 0008 → 自動建表。新增 dep 會自動安裝，不需改 workflow。

### 11.3 文件

- 更新 `ADMIN.md` 加「策略系統權限管理」章節（grant/revoke、webhook 設定、cascade 行為）
- `admin/README.md` 加新指令的使用範例

## 12. 開發階段拆分

切成 6 個 phase，每個 phase 完成後可獨立合 PR、可獨立 deploy：

| Phase | 範圍 | 完成標準 |
|---|---|---|
| **P1: Schema + 權限** | migration 0008、admin CLI toggle/set-webhook、`/api/me` 擴充 | admin CLI 能 grant 權限 + 設 webhook；migration 在乾淨 / 既有 DB 都跑 |
| **P2: DSL + Backtrader 翻譯** | DSL pydantic + validate、即時 evaluator（純函式）、Backtrader Strategy 動態組、conformance test | 50 randomized DSL 即時 vs Backtrader 一致；fixture backtest 跑得出 trade list |
| **P3: 即時 evaluator + state machine** | strategy_engine.py、fetcher fan-in、MTX/TMF fetcher、自動停用 + last_error | 用人造 OHLCV mock fetcher 跑通 entry → fill → exit → fill 週期 |
| **P4: API + Notifier** | api/routes/strategies.py、core/discord webhook_url 擴充、notifier、enable 422 | curl 全 endpoint 跑；真實 Discord webhook 收到 ENTRY/EXIT embed |
| **P5: Frontend** | 三頁 + 所有 components、condition builder、回測 panel、useMe gating | dev server 全功能可用，對 Phase 4 後端通過整合測試 |
| **P6: 整合 + 上線** | E2E test fixture、生產 deploy、ADMIN.md 加策略章節 | VPS 跑通真實策略一個交易日週期 |

每 phase 都跟 master 合，不需 feature flag（`can_use_strategy=0` 本身就是 flag — 預設關閉）。

## 13. YAGNI 暫不做的項目

寫進這裡保留決策軌跡，未來若要加可以直接接：

- 跨指標 DSL（C 範圍，VIX / 外資期貨淨額…）— 預留 schema：`expr` 已是 tagged union，加新 type 不影響舊 DSL。
- OR / nesting 條件 — 同上。
- 算術節點（`entry_price * 1.02`）— 用 simple `pct` / `points` 模式繞掉。
- Trailing stop — Backtrader 有現成 `bt.ind.TrailingStop`，未來作為 `take_profit_dsl` 的第四種 `type`。
- 多商品同策略（同一 DSL 訊號跑在 TX + MTX + TMF）。
- Shared / fork 策略（admin 建 template、user fork）。
- 回測歷史保存。
- 盤中即時評估（CLAUDE.md 明文禁止 intraday fetch）。
- Webhook 加密儲存（KMS / fernet）— 與 `.env` 模型一致即可。

## 14. 開放問題（待 implementation 階段確認）

- VPS 的 Python 版本與 Backtrader 1.9.78.123 相容性實測（Phase 6 第一步：在 VPS 上 `import backtrader` 跑通；若 numpy deprecation 出現再 pin numpy 版本）。
- Backtrader import matplotlib 在無 GUI VPS 上是否需要先 `pip install matplotlib` 才能 import 成功（依 Backtrader 版本與 Python 版本而定，需在 P2 開頭驗）。
