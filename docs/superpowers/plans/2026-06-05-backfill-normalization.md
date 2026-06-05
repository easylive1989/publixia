# 既有未正規化交易 Backfill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 名冊更新後，回頭把 `extracted_trades` 裡 `ticker IS NULL` 的舊交易重跑 `normalize()` 補回 ticker/market，讓它們進入價格追蹤。

**Architecture:** 新增 backfill service 只負責「重新正規化未對到的交易」，回傳 `{scanned, filled}`；`run_stock_reference_sync` 在名冊同步後呼叫它，若有補到再跑 `run_price_tracking()`。trades repo 新增兩個方法支援查詢與更新。

**Tech Stack:** Python、SQLite、pytest（in-memory DB，每測試前重置）。

**測試指令：** 從 repo 根 `python3 -m pytest tests/...`。

**前置：** 在 `feat/backfill-normalization` 分支。延續美股名冊（已合併 master）的 follow-up。

---

## File Structure

- **Modify** `backend/repositories/trades.py` — 新增 `list_unnormalized_trades()`、`set_trade_normalization()`。
- **Create** `backend/services/backfill_normalization.py` — `backfill_unnormalized_trades() -> dict`，只做重新正規化。
- **Modify** `backend/services/stock_reference_sync.py` — `run_stock_reference_sync()` 末尾接 backfill +（有補到才）price_tracking。
- **Create** `tests/test_backfill_normalization.py` — repo 方法 + service + wiring 測試。

---

## Task 1: trades repo — 查詢未正規化 + 更新單筆

**Files:**
- Modify: `backend/repositories/trades.py`
- Test: `tests/test_backfill_normalization.py`

- [ ] **Step 1: Write the failing test**

`tests/test_backfill_normalization.py`：

```python
"""Re-normalize previously-unmatched trades after the roster grows."""
from repositories import posts as posts_repo
from repositories import tracked_accounts as accounts_repo
from repositories import trades as trades_repo
from repositories.stock_reference import upsert_reference_batch


def _unnormalized_trade(raw_symbol="intc"):
    """Insert a post + one trade with ticker NULL (normalize missed it)."""
    acc = accounts_repo.list_accounts()[0]
    pid, _ = posts_repo.upsert_post(
        acc["id"], "threads", f"P-{raw_symbol}", "u", "貼文", "2026-06-01T00:00:00"
    )
    trades_repo.save_trades(
        pid,
        [{"raw_symbol": raw_symbol, "direction": "sell", "confidence": 0.9}],
        model="m", prompt_version="v4",
    )
    return pid


def test_list_unnormalized_trades_returns_null_ticker_rows():
    _unnormalized_trade("intc")
    rows = trades_repo.list_unnormalized_trades()
    assert len(rows) == 1
    assert rows[0]["raw_symbol"] == "intc"
    assert "id" in rows[0]


def test_set_trade_normalization_fills_ticker_market():
    _unnormalized_trade("intc")
    tid = trades_repo.list_unnormalized_trades()[0]["id"]

    trades_repo.set_trade_normalization(tid, "INTC", "US")

    assert trades_repo.list_unnormalized_trades() == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_backfill_normalization.py -v`
Expected: FAIL — `AttributeError: module 'repositories.trades' has no attribute 'list_unnormalized_trades'`

- [ ] **Step 3: Write minimal implementation**

在 `backend/repositories/trades.py` 末尾新增：

```python
def list_unnormalized_trades() -> list[dict]:
    """Trades whose raw_symbol never resolved to a ticker — candidates for
    re-normalization once the reference roster grows."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, raw_symbol FROM extracted_trades WHERE ticker IS NULL"
        ).fetchall()
    return [dict(r) for r in rows]


def set_trade_normalization(trade_id: int, ticker: str, market: str) -> None:
    """Fill in a trade's resolved ticker/market after a successful re-normalize."""
    with get_connection() as conn:
        conn.execute(
            "UPDATE extracted_trades SET ticker=?, market=? WHERE id=?",
            (ticker, market, trade_id),
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_backfill_normalization.py -v`
Expected: PASS（2 個測試）

- [ ] **Step 5: Commit**

```bash
git add backend/repositories/trades.py tests/test_backfill_normalization.py
git commit -m "feat(trades): list_unnormalized_trades + set_trade_normalization"
```

---

## Task 2: backfill service

**Files:**
- Create: `backend/services/backfill_normalization.py`
- Test: `tests/test_backfill_normalization.py`（沿用 Task 1 檔案）

- [ ] **Step 1: Write the failing test**

在 `tests/test_backfill_normalization.py` 末尾追加：

```python
def test_backfill_renormalizes_now_matchable_trade():
    from services.backfill_normalization import backfill_unnormalized_trades

    pid = _unnormalized_trade("intc")
    # 名冊現在有 INTC 了（模擬 SEC 名冊已同步）
    upsert_reference_batch(
        [{"ticker": "INTC", "market": "US", "canonical_name": "Intel Corp."}],
        source="test",
    )

    result = backfill_unnormalized_trades()

    assert result == {"scanned": 1, "filled": 1}
    row = trades_repo.list_trades_for_posts([pid])[pid][0]
    assert (row["ticker"], row["market"]) == ("INTC", "US")


def test_backfill_leaves_still_unmatched_trade_untouched():
    from services.backfill_normalization import backfill_unnormalized_trades

    _unnormalized_trade("不存在的標的")  # roster 沒有 → 仍對不到

    result = backfill_unnormalized_trades()

    assert result == {"scanned": 1, "filled": 0}
    assert len(trades_repo.list_unnormalized_trades()) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_backfill_normalization.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'services.backfill_normalization'`

- [ ] **Step 3: Write minimal implementation**

`backend/services/backfill_normalization.py`：

```python
"""Re-normalize previously-unmatched trades.

A trade is stored with ``ticker = NULL`` whenever ``normalize()`` couldn't
resolve its raw symbol at extraction time. When the reference roster later
grows (e.g. the US SEC sync adds a ticker), those old rows can finally
resolve — this re-runs normalize over them and fills in ticker/market so
they enter price tracking. Run right after the reference sync.
"""
import logging

from repositories import trades as trades_repo
from services.normalization import normalize

logger = logging.getLogger(__name__)


def backfill_unnormalized_trades() -> dict:
    """Re-normalize every ticker-less trade; fill the ones that now resolve.

    Returns ``{"scanned": N, "filled": M}``. Does not compute price windows —
    the caller runs price tracking after, only when something was filled.
    """
    rows = trades_repo.list_unnormalized_trades()
    filled = 0
    for r in rows:
        ticker, market = normalize(r["raw_symbol"])
        if ticker:
            trades_repo.set_trade_normalization(r["id"], ticker, market)
            filled += 1
    logger.info("backfill_normalization scanned=%d filled=%d", len(rows), filled)
    return {"scanned": len(rows), "filled": filled}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_backfill_normalization.py -v`
Expected: PASS（4 個測試）

- [ ] **Step 5: Commit**

```bash
git add backend/services/backfill_normalization.py tests/test_backfill_normalization.py
git commit -m "feat(ref): backfill_unnormalized_trades 重跑 normalize"
```

---

## Task 3: 接進 `run_stock_reference_sync`

**Files:**
- Modify: `backend/services/stock_reference_sync.py`
- Test: `tests/test_backfill_normalization.py`（沿用）

- [ ] **Step 1: Write the failing test**

在 `tests/test_backfill_normalization.py` 末尾追加（用 monkeypatch 隔開外部依賴）：

```python
def test_run_stock_reference_sync_backfills_and_tracks(monkeypatch):
    from services import stock_reference_sync as svc

    pid = _unnormalized_trade("intc")

    # 外部全 stub：TW finmind / US SEC / yfinance 價格追蹤都不打網路
    monkeypatch.setattr(svc, "sync_tw_from_finmind", lambda: 0)
    # SEC 名冊這次帶進 INTC
    monkeypatch.setattr(
        svc, "fetch_company_tickers",
        lambda: [{"cik_str": 1, "ticker": "INTC", "title": "Intel Corp."}],
    )
    tracked = {"called": False}
    monkeypatch.setattr(
        svc, "run_price_tracking",
        lambda: tracked.__setitem__("called", True),
    )

    result = svc.run_stock_reference_sync()

    assert result["backfill"] == {"scanned": 1, "filled": 1}
    assert tracked["called"] is True  # 有補到 → 觸發價格追蹤
    row = trades_repo.list_trades_for_posts([pid])[pid][0]
    assert (row["ticker"], row["market"]) == ("INTC", "US")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_backfill_normalization.py::test_run_stock_reference_sync_backfills_and_tracks -v`
Expected: FAIL — `result` 沒有 `"backfill"` 鍵（且 `svc` 沒有 `run_price_tracking` 屬性可 patch → AttributeError）

- [ ] **Step 3: Write minimal implementation**

在 `backend/services/stock_reference_sync.py`：

(a) 新增 import（接在現有 import 區）：

```python
from services.backfill_normalization import backfill_unnormalized_trades
from services.price_tracking_runner import run_price_tracking
```

(b) 把 `run_stock_reference_sync` 改成：

```python
def run_stock_reference_sync() -> dict:
    """Scheduler entry point: refresh TW + US rosters + indices, then
    re-normalize trades the bigger roster can now resolve."""
    tw = sync_tw_from_finmind()
    us = sync_us_from_sec()
    idx = seed_indices()
    backfill = backfill_unnormalized_trades()
    if backfill["filled"]:
        run_price_tracking()  # newly-resolved trades get their price windows
    return {"tw": tw, "us": us, "index": idx, "backfill": backfill}
```

- [ ] **Step 4: Run整套相關測試**

Run: `python3 -m pytest tests/test_backfill_normalization.py tests/test_stock_reference_sync.py tests/test_normalization.py -v`
Expected: 全部 PASS。

注意：`tests/test_stock_reference_sync.py::test_run_stock_reference_sync_includes_us` 先前只 stub `sync_tw_from_finmind` 與 `fetch_company_tickers`，未 stub `run_price_tracking`。本次因 INTC payload 無對應的未正規化交易，`backfill["filled"]` 為 0、不會觸發 `run_price_tracking`，該測試不需改動仍會過。執行時務必確認它仍綠；若變紅，於該測試補 `monkeypatch.setattr(svc, "run_price_tracking", lambda: None)`。

- [ ] **Step 5: Commit**

```bash
git add backend/services/stock_reference_sync.py tests/test_backfill_normalization.py
git commit -m "feat(ref): stock_ref_sync 同步後 backfill + 價格追蹤"
```

---

## 驗收

- [ ] `python3 -m pytest tests/test_backfill_normalization.py tests/test_stock_reference_sync.py tests/test_normalization.py tests/test_sec.py` 全綠。
- [ ] 部署 + 手動觸發 `stock_ref_sync` 後：圖上 `intc` 那筆的 `ticker` 由 NULL 變 `INTC`、`market=US`，進入價格追蹤，前端績效面板不再卡「追蹤中」。
