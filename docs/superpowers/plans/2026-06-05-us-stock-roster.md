# 美股全名冊正規化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 讓不在手寫清單裡的美股（如 INTC）能被正規化成 `(ticker, US)`，進而進入價格追蹤、顯示績效。

**Architecture:** 用 SEC 官方 `company_tickers.json` 全名冊取代手寫的 10 檔靜態美股清單，與台股用 FinMind 的做法對齊。網路抓取集中在新的 `core/sec.py`，sync 邏輯放在既有的 `stock_reference_sync.py`，中文暱稱由別名 overlay 補上。

**Tech Stack:** Python / FastAPI、SQLite、`requests`、pytest（in-memory DB via conftest）。

**測試指令前綴：** 從 repo 根目錄執行 `cd backend && python3 -m pytest`（conftest 設 `DB_PATH=:memory:` 並跑 migrations）。實際路徑以 repo 慣例為準——既有測試在 `tests/`，從 repo 根 `python3 -m pytest tests/`。

**前置：** 已在 `feat/us-stock-roster` 分支，spec 在 `docs/superpowers/specs/2026-06-05-us-stock-roster-normalization-design.md`。

---

## File Structure

- **Create** `backend/core/sec.py` — 唯一一支 SEC HTTP 抓取 helper（仿 `core/finmind.py`）；把 dict-of-dicts 攤平成 list。單一職責：對外抓名冊。
- **Create** `tests/test_sec.py` — `fetch_company_tickers` 的攤平 + User-Agent 測試（mock `requests`）。
- **Modify** `backend/services/stock_reference_sync.py` — `_US_STATIC` → `_US_ALIAS_OVERLAY`；新增 `sync_us_from_sec()`；`run_stock_reference_sync()` 改呼叫它；移除 `seed_us_static()`。
- **Create** `tests/test_stock_reference_sync.py` — sync + 別名 overlay + 公司名 + 進入點 wiring 的測試（stub `fetch_company_tickers`）。

---

## Task 1: SEC 抓取 helper `core/sec.py`

**Files:**
- Create: `backend/core/sec.py`
- Test: `tests/test_sec.py`

- [ ] **Step 1: Write the failing test**

`tests/test_sec.py`：

```python
"""SEC company_tickers.json fetch helper."""
import core.sec as sec


class _Resp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def test_fetch_company_tickers_flattens_and_sets_user_agent(monkeypatch):
    captured = {}

    def _fake_get(url, headers=None, timeout=None):
        captured["url"] = url
        captured["headers"] = headers or {}
        return _Resp({
            "0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."},
            "1": {"cik_str": 50863, "ticker": "INTC", "title": "Intel Corp."},
        })

    monkeypatch.setattr(sec.requests, "get", _fake_get)

    rows = sec.fetch_company_tickers()

    # SEC 的 fair-access 政策要求帶 User-Agent，否則 403
    assert "User-Agent" in captured["headers"]
    assert {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."} in rows
    assert len(rows) == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_sec.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'core.sec'`

- [ ] **Step 3: Write minimal implementation**

`backend/core/sec.py`：

```python
"""SEC company_tickers.json helper.

The US analogue of FinMind's TW stock list: SEC's full ticker→company-name
roster for every filer. SEC's fair-access policy requires a declared
``User-Agent`` header or it returns 403. The single network call lives here
so the sync logic can be unit-tested with a stubbed roster.
"""
import requests

URL = "https://www.sec.gov/files/company_tickers.json"
_USER_AGENT = "publixia-stock-tracker (https://stock.paul-learning.dev)"


def fetch_company_tickers() -> list[dict]:
    """Return ``[{"cik_str": ..., "ticker": ..., "title": ...}, ...]``.

    SEC returns a dict keyed by row index (``{"0": {...}, "1": {...}}``);
    this flattens it to a list. Transport errors propagate as the underlying
    ``requests`` exception.
    """
    r = requests.get(URL, headers={"User-Agent": _USER_AGENT}, timeout=20)
    r.raise_for_status()
    payload = r.json()
    return list(payload.values()) if isinstance(payload, dict) else []
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_sec.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/core/sec.py tests/test_sec.py
git commit -m "feat(ref): SEC company_tickers 抓取 helper"
```

---

## Task 2: 美股名冊 sync `sync_us_from_sec` + 中文別名 overlay

**Files:**
- Modify: `backend/services/stock_reference_sync.py`
- Test: `tests/test_stock_reference_sync.py`

- [ ] **Step 1: Write the failing test**

`tests/test_stock_reference_sync.py`：

```python
"""US roster sync from SEC + Chinese-alias overlay."""
from db.connection import get_connection
from services import stock_reference_sync as svc
from services.normalization import normalize

_SEC_PAYLOAD = [
    {"cik_str": 50863, "ticker": "INTC", "title": "Intel Corp."},
    {"cik_str": 1045810, "ticker": "NVDA", "title": "NVIDIA Corp"},
    {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."},
]


def test_sync_us_from_sec_normalizes_roster_tickers(monkeypatch):
    monkeypatch.setattr(svc, "fetch_company_tickers", lambda: _SEC_PAYLOAD)
    count = svc.sync_us_from_sec()
    assert count == 3
    # 不在舊手寫清單裡的 INTC 現在對得到；大小寫不敏感
    assert normalize("intc") == ("INTC", "US")


def test_sync_us_from_sec_keeps_chinese_alias_overlay(monkeypatch):
    monkeypatch.setattr(svc, "fetch_company_tickers", lambda: _SEC_PAYLOAD)
    svc.sync_us_from_sec()
    assert normalize("輝達") == ("NVDA", "US")


def test_sync_us_from_sec_uses_sec_company_name(monkeypatch):
    monkeypatch.setattr(svc, "fetch_company_tickers", lambda: _SEC_PAYLOAD)
    svc.sync_us_from_sec()
    with get_connection() as conn:
        row = conn.execute(
            "SELECT canonical_name FROM stock_reference "
            "WHERE ticker='INTC' AND market='US'"
        ).fetchone()
    assert row["canonical_name"] == "Intel Corp."
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_stock_reference_sync.py -v`
Expected: FAIL — `AttributeError: module 'services.stock_reference_sync' has no attribute 'sync_us_from_sec'`（且 `fetch_company_tickers` 尚未被 import 進該模組）

- [ ] **Step 3: Write minimal implementation**

在 `backend/services/stock_reference_sync.py`：

(a) import（接在 `from repositories.stock_reference import upsert_reference_batch` 後）：

```python
from core.sec import fetch_company_tickers
```

(b) 把 `_US_STATIC`（含英文名的 tuple）整段換成中文別名 overlay：

```python
# Common US nicknames the posts use (Chinese). ticker → aliases.
# Canonical English names come from the SEC roster, not here.
_US_ALIAS_OVERLAY: dict[str, list[str]] = {
    "NVDA": ["輝達", "黃仁勳"],
    "TSLA": ["特斯拉", "電動車"],
    "AAPL": ["蘋果"],
    "MSFT": ["微軟"],
    "GOOGL": ["谷歌", "Google"],
    "AMZN": ["亞馬遜"],
    "META": ["臉書", "Facebook"],
    "TSM": ["台積電ADR", "台積電 ADR"],
    "AMD": ["超微"],
}
```

(c) 把 `seed_us_static()` 整個函式換成：

```python
def sync_us_from_sec() -> int:
    """Upsert the full US roster from SEC (ticker → company name)."""
    rows_raw = fetch_company_tickers()
    # dedupe on ticker (SEC should be unique; setdefault guards anyway).
    seen: dict[str, dict] = {}
    for r in rows_raw:
        ticker = r.get("ticker")
        title = r.get("title")
        if not ticker or not title:
            continue
        seen.setdefault(
            ticker,
            {
                "ticker": ticker,
                "market": "US",
                "canonical_name": title,
                "aliases": _US_ALIAS_OVERLAY.get(ticker),
            },
        )
    count = upsert_reference_batch(list(seen.values()), source="sec")
    logger.info("stock_ref_us_synced count=%d", count)
    return count
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_stock_reference_sync.py -v`
Expected: PASS（3 個測試）

- [ ] **Step 5: Commit**

```bash
git add backend/services/stock_reference_sync.py tests/test_stock_reference_sync.py
git commit -m "feat(ref): 美股改用 SEC 全名冊 sync_us_from_sec + 中文別名 overlay"
```

---

## Task 3: 接進 `run_stock_reference_sync` 進入點

**Files:**
- Modify: `backend/services/stock_reference_sync.py:90-95`（`run_stock_reference_sync`）
- Test: `tests/test_stock_reference_sync.py`（沿用 Task 2 檔案）

- [ ] **Step 1: Write the failing test**

在 `tests/test_stock_reference_sync.py` 末尾追加：

```python
def test_run_stock_reference_sync_includes_us(monkeypatch):
    # TW 與 SEC 都 stub 掉，只驗證 us 欄走 sync_us_from_sec
    monkeypatch.setattr(svc, "sync_tw_from_finmind", lambda: 0)
    monkeypatch.setattr(svc, "fetch_company_tickers", lambda: _SEC_PAYLOAD)
    result = svc.run_stock_reference_sync()
    assert result["us"] == 3
    assert "tw" in result and "index" in result
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_stock_reference_sync.py::test_run_stock_reference_sync_includes_us -v`
Expected: FAIL — `run_stock_reference_sync` 仍呼叫已不存在的 `seed_us_static` → `NameError`（或 us 數不符）

- [ ] **Step 3: Write minimal implementation**

在 `backend/services/stock_reference_sync.py` 把 `run_stock_reference_sync` 內的 `us = seed_us_static()` 改成：

```python
def run_stock_reference_sync() -> dict:
    """Scheduler entry point: refresh TW roster + US roster + indices."""
    tw = sync_tw_from_finmind()
    us = sync_us_from_sec()
    idx = seed_indices()
    return {"tw": tw, "us": us, "index": idx}
```

- [ ] **Step 4: Run整套測試確認沒有殘留引用**

Run: `python3 -m pytest tests/ -v`
Expected: 全部 PASS（含既有 `test_normalization.py`）。若有 `NameError: seed_us_static`，表示有殘留引用沒清掉。

並確認沒有其他檔案引用舊符號：

Run: `grep -rn "seed_us_static\|_US_STATIC" backend/ tests/`
Expected: 無輸出（已完全移除）。

- [ ] **Step 5: Commit**

```bash
git add backend/services/stock_reference_sync.py tests/test_stock_reference_sync.py
git commit -m "feat(ref): run_stock_reference_sync 改用美股 SEC 名冊"
```

---

## 驗收

- [ ] `python3 -m pytest tests/` 全綠。
- [ ] `grep -rn "seed_us_static\|_US_STATIC" backend/ tests/` 無輸出。
- [ ] （部署後／手動觸發 `stock_ref_sync` 後）`normalize("intc")` 回 `("INTC","US")`；該筆 `extracted_trades.ticker` 不再是 NULL，會進入 `list_tracking_targets`，前端績效面板不再卡「追蹤中」。
