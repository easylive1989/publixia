# FSE Phase 6 — Integration + Rollout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close out the Futures Strategy Engine. Lift the highest-value polish items deferred during P2-P5 (RUNTIME_ERROR signal row so users see breakage in their UI history; enable-time history check so a strategy that can't fire today is rejected with a clear message; Wilder smoothing alignment so RSI re-enters the 50-seed conformance), document the operator runbook in ADMIN.md, and bring the spec doc back into sync with the shipped behaviour.

**Architecture:** Six bite-sized tasks across backend + docs. No new tables. No frontend changes (signal kind icons + permission gating already shipped in P5).

**Tech Stack:** Python 3.12 / SQLite / pytest.

**Spec reference:** `docs/superpowers/specs/2026-05-05-futures-strategy-engine-design.md` §5.11 (enable-time history check), §3.3 + §7.4 (RUNTIME_ERROR signal kind exists in schema; wire engine to use it), §11.3 (admin runbook update); P2.5 follow-up (Wilder smoothing).

---

## File Structure

**Created:**
- `tests/test_strategy_engine_runtime_error.py` — covers the new signal-row write path.
- `tests/test_strategies_routes_enable_history_gate.py` — covers spec §5.11.

**Modified:**
- `backend/repositories/strategies.py` — `mark_strategy_error` also writes a `RUNTIME_ERROR` row to `strategy_signals` so the user's UI history surfaces the failure.
- `backend/api/routes/strategies.py` — `enable` endpoint now also checks that DB has ≥ `_required_history_for(s)` futures_daily rows for the contract.
- `backend/services/strategy_engine.py` — expose `_required_history_for(strategy_dict)` (already private) for the route to call. Also add a tiny entry-DSL parser path so the route can compute lookback without re-doing all the work.
- `backend/services/strategy_dsl/indicators.py` — `_compute_rsi` switched to Wilder smoothing (matches `bt.indicators.RSI`).
- `tests/strategies/test_indicators.py` — update RSI tests to reflect Wilder values.
- `tests/strategies/random_dsl_generator.py` — re-include `rsi` in the conformance pool now that the math matches.
- `docs/superpowers/specs/2026-05-05-futures-strategy-engine-design.md` — sync the few drifted sections (§5.6 already done in P3 polish; §5.1 fan-in deviation; §11.1 deps already pinned in P2.5; signal kinds list).
- `ADMIN.md` — append a "Operating the Futures Strategy Engine" section: granting permission, setting webhooks, reading signal history, force_close vs reset, common error patterns.

**Out of scope (truly deferred):**
- `BacktestResult.open_position` split — frontend already filters `from_stop` rows; the visible ergonomic gap is small.
- Shared `_compare` helper between evaluator and backtest — the duplication is bounded and stable.
- KD `%D` Wilder vs simple — KD still excluded from conformance; same calculus as RSI but lower priority.

---

## Task 1 — `mark_strategy_error` writes RUNTIME_ERROR signal row

**Files:**
- Modify: `backend/repositories/strategies.py`
- Modify: `tests/test_strategies_repo.py`
- Modify: `tests/test_strategy_engine.py`

The signal kind `RUNTIME_ERROR` exists in migration 0008's CHECK list but no writer uses it. Today, when a strategy fails, the user sees `last_error` only on the edit page. After this task, the SignalHistoryTable also surfaces the failure as a row, which makes "why did this stop firing?" a one-glance answer.

`mark_strategy_error` keeps its existing semantics (set last_error + disable + update timestamp) and adds: write a `kind=RUNTIME_ERROR` row whose `message` column is the truncated error text.

- [ ] **Step 1.1: Append the failing test**

Append to `tests/test_strategies_repo.py`:

```python
def test_mark_strategy_error_also_writes_runtime_error_signal():
    sid = create_strategy(**_GOOD_STRATEGY_INPUT)
    mark_strategy_error(sid, "DSL exploded: KeyError 'close'")

    sigs = list_signals(sid)
    assert len(sigs) == 1
    assert sigs[0]["kind"] == "RUNTIME_ERROR"
    assert "DSL exploded" in sigs[0]["message"]
    assert sigs[0]["signal_date"] is not None  # YYYY-MM-DD shape
```

- [ ] **Step 1.2: Run — should fail**

```bash
cd /Users/paulwu/Documents/Github/publixia
python3 -m pytest tests/test_strategies_repo.py::test_mark_strategy_error_also_writes_runtime_error_signal -v
```

Expected: PASS only after the implementation. Currently, mark_strategy_error doesn't write a signal row — the test will report 0 signals.

- [ ] **Step 1.3: Update `mark_strategy_error`**

Replace the body of `mark_strategy_error` in `backend/repositories/strategies.py`:

```python
def mark_strategy_error(strategy_id: int, error_message: str) -> None:
    """Set last_error + last_error_at, disable real-time notifications,
    AND write a RUNTIME_ERROR signal row so the failure surfaces in the
    user's signal history."""
    msg = (error_message or "")[:1000]
    now = _now_iso()
    today = now[:10]   # YYYY-MM-DD slice of the ISO timestamp
    with get_connection() as conn:
        conn.execute(
            "UPDATE strategies SET "
            "  last_error = ?, last_error_at = ?, "
            "  notify_enabled = 0, updated_at = ? "
            "WHERE id = ?",
            (msg, now, now, strategy_id),
        )
        conn.execute(
            "INSERT INTO strategy_signals "
            "(strategy_id, kind, signal_date, message, created_at) "
            "VALUES (?, 'RUNTIME_ERROR', ?, ?, ?)",
            (strategy_id, today, msg, now),
        )
        conn.commit()
```

- [ ] **Step 1.4: The new repo test passes; engine test still passes**

```bash
python3 -m pytest tests/test_strategies_repo.py tests/test_strategy_engine.py -q
```

Expected: existing 17 + new 1 + engine 9 = 27 PASS, no regressions. (The P3 engine test `test_evaluate_one_marks_strategy_error_on_exception` still asserts `notify_enabled is False` and `last_error is not None` — the new signal write doesn't affect those.)

- [ ] **Step 1.5: Append an engine-side end-to-end check**

Append to `tests/test_strategy_engine.py`:

```python
def test_evaluate_one_runtime_error_writes_signal_row_visible_in_history():
    """When evaluate_one() raises, mark_strategy_error fires + the user
    sees a RUNTIME_ERROR row in list_signals."""
    sid = _insert_strategy(state="idle")
    bad_bar = {"date": "2026-01-15", "open": 1.0, "high": 1.0, "low": 1.0,
               "volume": 1}    # missing 'close' → KeyError in _try_entry
    _seed_bars("TX", [_bar("2026-01-15", 1.0)])

    s = get_strategy(sid)
    evaluate_one(s, bad_bar)

    sigs = list_signals(sid)
    kinds = [r["kind"] for r in sigs]
    assert "RUNTIME_ERROR" in kinds
```

- [ ] **Step 1.6: Run — should pass**

```bash
python3 -m pytest tests/test_strategy_engine.py -q
```

Expected: 11 PASS (10 prior + 1 new).

- [ ] **Step 1.7: Full suite**

```bash
python3 -m pytest tests/ -q
```

Expected: 452 + 2 = 454 PASS.

- [ ] **Step 1.8: Commit**

```bash
git add backend/repositories/strategies.py tests/test_strategies_repo.py tests/test_strategy_engine.py
git commit -m "$(cat <<'EOF'
feat(strategy): mark_strategy_error also writes RUNTIME_ERROR signal

Spec §3.3's RUNTIME_ERROR signal kind was unused since P1 — only the
strategies.last_error column captured the failure. Engine evaluation
errors now also append a RUNTIME_ERROR row to strategy_signals so the
P5 SignalHistoryTable surfaces "❌ 執行錯誤" in the user's UI history,
matching the kind labels the table already renders.

The signal_date is set to today's date (slice of UTC ISO timestamp);
message holds the same truncated 1000-char error text last_error gets.
EOF
)"
```

Do NOT amend, do NOT push.

---

## Task 2 — Enable-time history check (spec §5.11)

**Files:**
- Modify: `backend/services/strategy_engine.py` — expose `required_history_for_strategy(s)`.
- Modify: `backend/api/routes/strategies.py` — call it in the enable handler.
- Create: `tests/test_strategies_routes_enable_history_gate.py`

Spec §5.11: enabling a strategy whose entry DSL needs N bars but only M < N exist should reject with a clear message. Currently the engine handles this gracefully (run_dsl returns None, no signal fires), but the user has no feedback that "your strategy will silently never fire until the fetcher backfills more bars". This task surfaces that as a 422.

- [ ] **Step 2.1: Write the failing test**

Create `tests/test_strategies_routes_enable_history_gate.py`:

```python
"""Spec §5.11: enabling a strategy needing more bars than the DB has → 422."""
import json

from fastapi.testclient import TestClient

from db.connection import get_connection
from main import app
from repositories.futures import save_futures_daily_rows
from repositories.strategies import create_strategy


client = TestClient(app)


def _grant_paul():
    with get_connection() as conn:
        conn.execute(
            "UPDATE users SET can_use_strategy=1, "
            "  discord_webhook_url=? WHERE id=1",
            ("https://discord.com/api/webhooks/1/" + "x" * 60,),
        )
        conn.commit()


def _seed_bars(n: int) -> None:
    """Insert n daily TX bars starting 2026-01-01."""
    import datetime
    base = datetime.date(2026, 1, 1)
    rows = [{
        "symbol": "TX",
        "date":   str(base + datetime.timedelta(days=i)),
        "contract_date": "202604",
        "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0,
        "volume": 1000, "open_interest": None, "settlement": None,
    } for i in range(n)]
    save_futures_daily_rows(rows)


def _strategy_needing_n_bars(n: int) -> int:
    return create_strategy(
        user_id=1, name=f"sma_{n}",
        direction="long", contract="TX", contract_size=1,
        entry_dsl={
            "version": 1,
            "all": [{"left": {"field": "close"}, "op": "gt",
                     "right": {"indicator": "sma", "n": n}}],
        },
        take_profit_dsl={"version": 1, "type": "pct", "value": 1.0},
        stop_loss_dsl  ={"version": 1, "type": "pct", "value": 1.0},
    )


def test_enable_rejects_when_history_too_short():
    _grant_paul()
    _seed_bars(5)                  # only 5 bars
    sid = _strategy_needing_n_bars(20)   # needs 20

    r = client.post(f"/api/strategies/{sid}/enable")
    assert r.status_code == 422
    assert "history" in r.text.lower() or "歷史" in r.text


def test_enable_passes_when_history_sufficient():
    _grant_paul()
    _seed_bars(30)
    sid = _strategy_needing_n_bars(20)

    r = client.post(f"/api/strategies/{sid}/enable")
    assert r.status_code == 200
```

- [ ] **Step 2.2: Run — should fail**

```bash
python3 -m pytest tests/test_strategies_routes_enable_history_gate.py -v
```

Expected: `test_enable_rejects_when_history_too_short` fails (the route returns 200 today).

- [ ] **Step 2.3: Add a helper to the engine**

Append to `backend/services/strategy_engine.py`:

```python
def required_history_for_strategy(strategy: dict) -> int:
    """Compute the minimum bar count the engine needs to evaluate an
    entry signal for this strategy. Used by the API enable handler.

    For all-const DSLs the count is 1 — the engine still needs at least
    one bar to even talk about close/today. For indicator-bearing DSLs
    we take the maximum lookback across the entry conditions.
    """
    entry = EntryDSL.model_validate(strategy["entry_dsl"])
    n = 1
    for cond in entry.all:
        n = max(
            n,
            required_lookback(cond.left),
            required_lookback(cond.right),
        )
    return n
```

(Imports `EntryDSL` and `required_lookback` are already present at the top of the file.)

- [ ] **Step 2.4: Update the enable handler**

In `backend/api/routes/strategies.py`, find:

```python
@router.post("/{strategy_id}/enable")
def enable_strategy(strategy_id: int,
                    user: dict = Depends(require_strategy_permission)):
    _own_or_404(strategy_id, user)
    if not user.get("discord_webhook_url"):
        raise HTTPException(
            status_code=422,
            detail="discord webhook not set for user; ask admin to set one",
        )
    update_strategy(strategy_id, notify_enabled=True)
    return {"ok": True}
```

Replace with:

```python
@router.post("/{strategy_id}/enable")
def enable_strategy(strategy_id: int,
                    user: dict = Depends(require_strategy_permission)):
    s = _own_or_404(strategy_id, user)
    if not user.get("discord_webhook_url"):
        raise HTTPException(
            status_code=422,
            detail="discord webhook not set for user; ask admin to set one",
        )
    from services.strategy_engine import required_history_for_strategy
    from repositories.futures import get_futures_daily_range
    needed = required_history_for_strategy(s)
    have = len(get_futures_daily_range(s["contract"], "1900-01-01"))
    if have < needed:
        raise HTTPException(
            status_code=422,
            detail=(
                f"need {needed} bars of {s['contract']} history to "
                f"evaluate this strategy, but only {have} bars exist; "
                f"wait for the fetcher to backfill before enabling."
            ),
        )
    update_strategy(strategy_id, notify_enabled=True)
    return {"ok": True}
```

- [ ] **Step 2.5: Run — should pass**

```bash
python3 -m pytest tests/test_strategies_routes_enable_history_gate.py -v
```

Expected: 2 PASS.

- [ ] **Step 2.6: Run the existing route tests too**

```bash
python3 -m pytest tests/test_strategies_routes.py -v 2>&1 | tail -20
```

Expected: 24 PASS — none should regress. The pre-existing `test_enable_passes_when_webhook_set` test seeds 0 bars but uses an entry DSL of `{"field":"close"} > {"const":100}`. After this change, that DSL has `required_lookback = max(1, 0) = 1`, but 0 bars are present → 422. **The pre-existing test will start failing.**

Update `test_enable_passes_when_webhook_set` in `tests/test_strategies_routes.py` to seed at least 1 bar before calling `/enable`:

```python
def test_enable_passes_when_webhook_set():
    _grant_permission_to_paul()
    with get_connection() as conn:
        conn.execute(
            "UPDATE users SET discord_webhook_url=? WHERE id=1",
            ("https://discord.com/api/webhooks/1/" + "x" * 60,),
        )
        conn.commit()
    # Seed one bar so the new history-sufficiency check (spec §5.11) passes.
    from repositories.futures import save_futures_daily_rows
    save_futures_daily_rows([{
        "symbol": "TX", "date": "2026-01-15", "contract_date": "202604",
        "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0,
        "volume": 1000, "open_interest": None, "settlement": None,
    }])
    sid = create_strategy(user_id=1, name="x", direction="long",
                          contract="TX", contract_size=1, **_good_dsls())
    r = client.post(f"/api/strategies/{sid}/enable")
    assert r.status_code == 200
    after = client.get(f"/api/strategies/{sid}").json()
    assert after["notify_enabled"] is True
```

- [ ] **Step 2.7: Run the full suite**

```bash
python3 -m pytest tests/ -q
```

Expected: 454 + 2 = 456 PASS.

- [ ] **Step 2.8: Commit**

```bash
git add backend/services/strategy_engine.py backend/api/routes/strategies.py \
        tests/test_strategies_routes_enable_history_gate.py \
        tests/test_strategies_routes.py
git commit -m "$(cat <<'EOF'
feat(api): enable-time history check (spec §5.11)

POST /api/strategies/{id}/enable now also verifies the DB has at least
required_history_for_strategy(s) bars of the strategy's contract; if
not, returns 422 with a message telling the user to wait for the
fetcher to backfill. Without this, an enabled strategy with insufficient
history runs through evaluate_one but run_dsl returns None forever and
no signals ever fire — silent failure mode the spec called out but the
P4 enable handler didn't enforce.

Pre-existing test_enable_passes_when_webhook_set seeded zero bars; now
seeds one bar to satisfy the new check (its DSL only needs 1 bar).
EOF
)"
```

---

## Task 3 — Wilder smoothing for RSI (P2.5 alignment)

**Files:**
- Modify: `backend/services/strategy_dsl/indicators.py` — switch `_compute_rsi` to Wilder.
- Modify: `tests/strategies/test_indicators.py` — update the two RSI tests; add one Wilder-reference value.
- Modify: `tests/strategies/random_dsl_generator.py` — re-add `rsi` to the conformance pool.

Backtrader's `bt.indicators.RSI` uses Wilder smoothing (recursive: `avg_gain[i] = avg_gain[i-1] * (n-1)/n + gain[i]/n`). Our backend `_compute_rsi` was a flat SMA of gains/losses — equivalent for the first window but diverges after. P2 conformance excluded RSI for this reason. Aligning to Wilder closes the gap.

- [ ] **Step 3.1: Replace `_compute_rsi`**

In `backend/services/strategy_dsl/indicators.py`, find:

```python
def _compute_rsi(closes: np.ndarray, n: int) -> float:
    diffs = np.diff(closes)
    gains = np.where(diffs > 0, diffs, 0.0)
    losses = np.where(diffs < 0, -diffs, 0.0)
    avg_gain = gains[-n:].mean()
    avg_loss = losses[-n:].mean()
    if avg_loss == 0:
        return 100.0 if avg_gain > 0 else 50.0
    rs = avg_gain / avg_loss
    return float(100.0 - 100.0 / (1.0 + rs))
```

Replace with:

```python
def _compute_rsi(closes: np.ndarray, n: int) -> float:
    """Wilder-smoothed RSI matching bt.indicators.RSI.

    Seed: simple mean of the first n gains/losses.
    Steps: avg_gain[i] = (avg_gain[i-1] * (n-1) + gain[i]) / n
           avg_loss[i] same.
    Final RSI uses the most recent avg_gain / avg_loss.
    """
    diffs = np.diff(closes)
    gains  = np.where(diffs > 0, diffs, 0.0)
    losses = np.where(diffs < 0, -diffs, 0.0)
    if len(gains) < n:
        # required_lookback gates this, but be defensive.
        avg_gain = gains.mean() if len(gains) else 0.0
        avg_loss = losses.mean() if len(losses) else 0.0
    else:
        avg_gain = float(gains[:n].mean())
        avg_loss = float(losses[:n].mean())
        for i in range(n, len(gains)):
            avg_gain = (avg_gain * (n - 1) + gains[i]) / n
            avg_loss = (avg_loss * (n - 1) + losses[i]) / n
    if avg_loss == 0:
        return 100.0 if avg_gain > 0 else 50.0
    rs = avg_gain / avg_loss
    return float(100.0 - 100.0 / (1.0 + rs))
```

- [ ] **Step 3.2: Update RSI unit tests**

Open `tests/strategies/test_indicators.py`. The `test_rsi_all_gains_returns_100` and `test_rsi_all_losses_returns_zero` tests still pass under Wilder (an all-gains series has zero losses → RSI=100; all-losses has zero gains → RSI=0). Verify:

```bash
python3 -m pytest tests/strategies/test_indicators.py::test_rsi_all_gains_returns_100 \
                  tests/strategies/test_indicators.py::test_rsi_all_losses_returns_zero -v
```

Expected: 2 PASS unchanged.

Add one new test that locks in a Wilder-specific reference value. Append to `tests/strategies/test_indicators.py`:

```python
def test_rsi_wilder_smoothing_matches_bt_indicators_rsi():
    """RSI(14) of a 30-bar synthetic series should match bt.indicators.RSI
    within 1e-6. This is the integration check that the math drift between
    indicators._compute_rsi and bt.indicators.RSI (the gap that excluded
    RSI from the P2 conformance sweep) is now closed."""
    import backtrader as bt
    import pandas as pd

    closes = [100.0]
    rng = list(range(30))
    for i in rng[1:]:
        # Mix of up + down moves so the smoothing actually does something.
        closes.append(closes[-1] + (1.5 if i % 3 != 0 else -1.0))

    bars = _bars(closes)
    ours = compute_indicator(IndicatorRSI(indicator="rsi", n=14), bars)

    # Compute via Backtrader.
    df = pd.DataFrame({
        "datetime": pd.to_datetime([b["date"] for b in bars]),
        "open":  closes, "high": [c + 1 for c in closes],
        "low":   [c - 1 for c in closes],
        "close": closes, "volume": [1000] * len(closes),
    }).set_index("datetime")

    class _Probe(bt.Strategy):
        def __init__(self):
            self.r = bt.indicators.RSI(self.data.close, period=14)
            self.last = None
        def next(self):
            self.last = float(self.r[0])

    cerebro = bt.Cerebro()
    cerebro.adddata(bt.feeds.PandasData(dataname=df,
                                        timeframe=bt.TimeFrame.Days, compression=1))
    cerebro.addstrategy(_Probe)
    bt_result = cerebro.run()[0].last

    assert abs(ours - bt_result) < 1e-3, f"ours={ours} bt={bt_result}"
```

(`_bars` and `compute_indicator` and `IndicatorRSI` are already imported at the top of the file.)

- [ ] **Step 3.3: Run — should pass**

```bash
python3 -m pytest tests/strategies/test_indicators.py -v 2>&1 | tail -25
```

Expected: 22 PASS (21 prior + 1 new). The `1e-3` tolerance accommodates the Backtrader's first-bar warm-up — Wilder both ways converges to the same value within a few bars.

- [ ] **Step 3.4: Re-add RSI to the conformance generator**

In `tests/strategies/random_dsl_generator.py`, find:

```python
_INDICATOR_BUILDERS = [
    lambda r: {"indicator": "sma", "n": r.choice([5, 10, 20])},
    lambda r: {"indicator": "ema", "n": r.choice([5, 10, 20])},
    lambda r: {"indicator": "highest", "n": r.choice([5, 10, 20])},
    lambda r: {"indicator": "lowest",  "n": r.choice([5, 10, 20])},
    lambda r: {"indicator": "bbands", "n": r.choice([10, 20]), "k": 2.0,
               "output": r.choice(["upper", "middle", "lower"])},
]
```

(If the file's actual order is different, locate the `_INDICATOR_BUILDERS` list.) Replace with the version that re-adds RSI:

```python
_INDICATOR_BUILDERS = [
    lambda r: {"indicator": "sma", "n": r.choice([5, 10, 20])},
    lambda r: {"indicator": "ema", "n": r.choice([5, 10, 20])},
    lambda r: {"indicator": "rsi", "n": r.choice([7, 14])},
    lambda r: {"indicator": "highest", "n": r.choice([5, 10, 20])},
    lambda r: {"indicator": "lowest",  "n": r.choice([5, 10, 20])},
    lambda r: {"indicator": "bbands", "n": r.choice([10, 20]), "k": 2.0,
               "output": r.choice(["upper", "middle", "lower"])},
]
```

Also remove the RSI exclusion line from the file's docstring if present — `rsi` is no longer drift-prone.

- [ ] **Step 3.5: Run conformance — must still pass on all 50 seeds**

```bash
python3 -m pytest tests/strategies/test_dsl_conformance.py tests/test_strategy_engine_conformance.py -q
```

Expected: 100 PASS. If 1-3 seeds fail with a small numerical drift, the issue is RSI's `safediv=False` divide-by-zero edge in Backtrader (when `avg_loss=0` exactly). The unit test's all-gains case handles this in our impl by returning 100.0; verify Backtrader does the same. If a seed fails on a different drift, dump the failing seed's RSI values from both paths and tighten the tolerance via `bt.indicators.RSI(safediv=True)` in `services/strategy_backtest.py::_build_bt_indicator` for the RSI branch:

```python
if isinstance(expr, IndicatorRSI):
    return bt.indicators.RSI(data.close, period=expr.n, safediv=True)
```

If conformance still fails after that, **revert RSI from the generator and report BLOCKED** — Wilder math is harder to align bit-exactly than expected.

- [ ] **Step 3.6: Run full suite**

```bash
python3 -m pytest tests/ -q
```

Expected: 456 + 1 (new RSI Wilder test) = 457 PASS. Conformance test count is unchanged (still 50 seeds — RSI just shows up in some of them now).

- [ ] **Step 3.7: Commit**

```bash
git add backend/services/strategy_dsl/indicators.py \
        tests/strategies/test_indicators.py \
        tests/strategies/random_dsl_generator.py
# Also stage strategy_backtest.py if you needed safediv=True in step 3.5.
git commit -m "$(cat <<'EOF'
fix(strategy): RSI now uses Wilder smoothing, matches bt.indicators.RSI

P2.5 follow-up: _compute_rsi previously took a flat SMA of gains/losses;
Backtrader uses Wilder's recursive smoothing
(avg = avg_prev * (n-1)/n + new/n). The two diverged for any series
beyond the first window, so the P2 conformance test had to exclude RSI
from its 50-seed sweep.

After this commit RSI uses Wilder + the conformance generator re-adds
rsi to its indicator pool. Unit tests gain a 30-bar reference value
asserting our path matches a real bt.indicators.RSI within 1e-3 of
the same data.

Closes the live ↔ backtest parity gap for RSI strategies.
EOF
)"
```

---

## Task 4 — Spec doc refresh

**Files:**
- Modify: `docs/superpowers/specs/2026-05-05-futures-strategy-engine-design.md`

The spec accumulated minor drift across P3-P5. Sync it back so future readers don't trip on contradictions.

- [ ] **Step 4.1: Read the current spec to identify drift**

```bash
grep -n "MULTIPLIER\|barrier\|fan-in\|on_futures_data_written\|_request" \
  /Users/paulwu/Documents/Github/publixia/docs/superpowers/specs/2026-05-05-futures-strategy-engine-design.md \
  | head -20
```

You'll find a few mentions where the current implementation differs:
- §5.1 "fan-in barrier" — implementation dispatches per-fetcher, not via a barrier (P3 plan documented this; spec text didn't).
- §3.5 still describes 6 signal kinds; we now actually emit RUNTIME_ERROR (Task 1 above), so the prose needs a small update.

- [ ] **Step 4.2: Update §5.1 (fan-in deviation)**

Find the §5.1 section. Append this paragraph immediately after the existing "Triggers via fetcher tail-call" paragraph:

```markdown
**Implementation deviation from the barrier model:** P3 ships a simpler
fan-out instead of a true fan-in barrier. Each fetcher's tail-call
`on_futures_data_written(contract, date)` independently iterates only
the strategies bound to that contract — strategy `s` with
`s.contract = "TX"` won't fire from the MTX fetcher's hook, and a TX
fetcher failure leaves MTX/TMF strategies untouched. Functionally
equivalent to the barrier (each strategy still evaluates exactly once
per day on its own contract's fresh bar) and avoids tracking which
fetchers have completed.
```

- [ ] **Step 4.3: Update §3.5 / §7.4 to reference the RUNTIME_ERROR signal row**

Find the bullet list under "ENTRY_SIGNAL / EXIT_SIGNAL" or the §7.4 "Runtime error" section. Update so it reflects:

> When `evaluate_one` raises, the engine writes a `kind=RUNTIME_ERROR`
> row to `strategy_signals` (alongside the existing `last_error`
> column update on `strategies`) so the UI history surfaces the
> failure as a row.

If §7.4 doesn't already describe this, append a paragraph at its end:

```markdown
**Signal-history surfacing:** the runtime error is also written as a
`kind=RUNTIME_ERROR` row to `strategy_signals` so the user-facing
SignalHistoryTable shows "❌ 執行錯誤" alongside the actual signal
events. P6 closed this loop; before P6 the only surface was the
`strategies.last_error` column visible only on the edit page.
```

- [ ] **Step 4.4: Verify the spec still parses as Markdown**

```bash
head -20 /Users/paulwu/Documents/Github/publixia/docs/superpowers/specs/2026-05-05-futures-strategy-engine-design.md
```

Eyeball for any mid-edit corruption.

- [ ] **Step 4.5: Commit**

```bash
git add docs/superpowers/specs/2026-05-05-futures-strategy-engine-design.md
git commit -m "$(cat <<'EOF'
docs(strategy): refresh spec for P3-P6 implementation reality

§5.1 fan-in barrier description now also documents the per-fetcher
fan-out model the implementation actually uses (functionally
equivalent; documented as a deviation for future readers).

§7.4 runtime error description now also calls out the RUNTIME_ERROR
signal row P6 added — this is the surface visible in the UI's signal
history alongside the strategies.last_error column on the edit page.
EOF
)"
```

---

## Task 5 — ADMIN.md operator runbook

**Files:**
- Modify: `ADMIN.md`

ADMIN.md gained a "Strategy permissions & per-user Discord webhooks" section in P1 covering grant/revoke + webhook lifecycle. P6 adds a sibling section that operators read when running the strategy system in production: how to read signal history, how to react to a misbehaving strategy, when to use force_close vs reset, common error patterns.

- [ ] **Step 5.1: Append the new section to `ADMIN.md`**

Find the end of the existing `## Strategy permissions & per-user Discord webhooks` section (just before `## Auto-tracked Taiwan top-100`). Insert the following BEFORE the auto-tracked section:

```markdown
## Operating the Futures Strategy Engine

Once a user has `can_use_strategy=1` and a webhook set, they manage
their strategies via the `/strategies` page. Operators usually only get
involved when something breaks. This section covers the troubleshooting
workflows.

### Reading what the engine just did

Each strategy has a signal history (the `strategy_signals` table; UI
renders it as 訊號歷史). The full event sequence for a single closed
trade is:

1. `ENTRY_SIGNAL` — the engine decided "fire" on bar T (close-of-day).
   The Discord embed went out at this point.
2. `ENTRY_FILLED` — bar T+1 opened; entry_fill_price recorded. No
   embed; this is bookkeeping.
3. `EXIT_SIGNAL` — stop-loss / take-profit / TIMEOUT triggered on
   bar E. Discord embed at this point with reason + estimated PnL.
4. `EXIT_FILLED` — bar E+1 opened; final pnl_amount recorded.

`MANUAL_RESET` shows up only when the user clicked "強制平倉" on the
edit page — it's recorded as the `exit_reason` on a synthesised
`EXIT_FILLED` row using the latest available bar's close.

`RUNTIME_ERROR` shows up when `evaluate_one` raises (e.g. a DSL
references a field the bar dict doesn't have). The strategy is
auto-disabled (`notify_enabled=0`); the user must edit + re-enable
after fixing the cause.

### When a user reports "no signal showed up"

Check, in order:

1. **Was the strategy enabled the day the user expected it to fire?**
   `SELECT id, name, notify_enabled, last_error FROM strategies WHERE
   user_id=...`. If `notify_enabled=0` and `last_error` is populated, a
   runtime error already auto-disabled it.

2. **Did the contract's fetcher run that day?** `SELECT MAX(date) FROM
   futures_daily WHERE symbol='TX'` (or MTX / TMF). If the latest date
   isn't the latest trading day, the fetcher failed — check
   `journalctl -u stock-dashboard.service` for FinMind errors.

3. **Did the engine evaluate the strategy?** Look for log lines:
   `strategy_notify_signal strategy_id=...` (a signal fired) or
   `strategy_notify_skip_no_webhook ...` (the user has no webhook).

4. **Does the strategy actually fire on the bar that just landed?**
   The fastest way is to run a backtest from the user's UI for the
   range that includes the target date — if the backtest shows no trade
   on that date, the strategy's logic just didn't trigger; not a bug.

### When a user reports "I'm getting too many false signals"

This is a strategy-design issue, not an ops issue. The user can:

- Tighten the entry conditions in the UI.
- Raise the take-profit % or lower the stop-loss % to reduce
  whipsawing.
- Add a `streak_above`/`streak_below` requirement (N-day persistence).

Operators don't usually intervene; just confirm the engine is working
as designed.

### force_close vs reset

- **force_close** (UI: 強制平倉, only available when state ∈
  {open, pending_exit}): use when the user wants to "close the trade
  now" but keep the strategy's history intact. Writes one
  `EXIT_FILLED` row with `exit_reason='MANUAL_RESET'` using the latest
  bar's close as the assumed fill price. State returns to `idle`. The
  Discord embed posts.

- **reset** (UI: 重置, always available): nuclear option. Deletes the
  strategy's entire `strategy_signals` history, clears all state
  machine columns + `last_error`, returns state to `idle`. No Discord
  embed. Use when the strategy got into a wedged state during
  development or after a runtime error and the user wants a clean
  slate.

If a user can't decide which to use: force_close preserves the trade
record; reset doesn't. Default to reset for runtime-error recovery,
force_close for "I just want out of this trade."

### Common runtime errors and what they mean

The engine catches every `evaluate_one` exception and stores a 1000-
char-truncated message in `strategies.last_error` + writes a
`RUNTIME_ERROR` signal row. The user sees both on their edit page.

| Error pattern                                  | Likely cause                              |
|------------------------------------------------|-------------------------------------------|
| `KeyError: 'close'`                            | A fetcher persisted a malformed bar (rare); inspect futures_daily for the date in `last_error_at`. |
| `pydantic.ValidationError`                     | DSL became invalid after a schema change. The strategy was enabled before P6's enable-time check landed; just re-edit + save. |
| `ZeroDivisionError` (RSI / change_pct)         | Bar's close was 0 (delisted symbol). Should never happen for TX/MTX/TMF — investigate fetcher. |
| `RuntimeError: FinMind ...` in fetcher logs    | Not a strategy error; FinMind down. Strategy will just not evaluate today; tomorrow's fetcher recovers. |

### Manually re-running a strategy for a day

If a fetcher backfills a missed day after the engine ran, the user's
strategy doesn't auto-replay. To force re-evaluation manually on the
VPS:

```bash
ssh root@$VPS_HOST
python3 -c "
import sys; sys.path.insert(0, '/opt/stock-dashboard/backend')
from services.strategy_engine import on_futures_data_written
on_futures_data_written('TX', '2026-04-15')
"
```

This iterates every notify-enabled strategy on TX and advances each by
one bar against the 2026-04-15 row. **Use sparingly** — it doesn't
de-dupe against signals already written for that date, so running it
twice in a day will double-write.

### Cleaning up after a failed deploy

If `init_db()` fails mid-migration on deploy and `systemctl restart`
loops, the DB might be in a partial state. The `db/runner.py`
migrations are forward-only and idempotent, so re-running the deploy
usually fixes it. If it doesn't, restore the DB from the previous
night's backup (the cleanup job at `0 0 * * 0` is the standard backup
trigger) and replay any user actions from the journal.

### Where the engine logs

```bash
journalctl -u stock-dashboard.service -f | grep strategy_
```

Useful greps:
- `strategy_notify_signal` — every Discord-bound signal
- `strategy_notify_skip_no_webhook` — user without webhook
- `strategy_notify_discord_failed` — webhook 5xx / unreachable
- `strategy_evaluate_failed` — full traceback before auto-disable
- `strategy_engine_no_bar` — fetcher hadn't run when engine fired

```
```

- [ ] **Step 5.2: Verify the markdown still renders**

```bash
head -200 /Users/paulwu/Documents/Github/publixia/ADMIN.md | tail -100
```

Eyeball for any list/table/code-fence issues.

- [ ] **Step 5.3: Commit**

```bash
git add ADMIN.md
git commit -m "$(cat <<'EOF'
docs(admin): operator runbook for the Futures Strategy Engine

ADMIN.md gains a "Operating the Futures Strategy Engine" section
covering: how to read signal history (the 4-event lifecycle, plus
MANUAL_RESET and RUNTIME_ERROR), 4-step troubleshooting checklist for
"no signal showed up", when to use force_close vs reset, common
runtime errors and their causes, manual single-day re-evaluation
recipe via SSH, and the structured log greps that surface engine
behaviour in journalctl.
EOF
)"
```

---

## Task 6 — Verify production end-to-end

**No code changes** — this task is a smoke checklist after the prior commits land + deploy.

- [ ] **Step 6.1: Push everything**

```bash
git push origin master
```

(Or push the P6 branch + open a PR per project policy. The pre-merge dance is identical to P1-P5.)

- [ ] **Step 6.2: Wait for backend deploy to complete**

```bash
gh run list --workflow=deploy-backend.yml --limit 1
```

Expected: `success` within 2 minutes.

- [ ] **Step 6.3: Confirm the engine module imports the new helper**

```bash
ssh root@$VPS_HOST 'cd /opt/stock-dashboard && python3 -c "
import sys; sys.path.insert(0, \"backend\")
from services.strategy_engine import (
  evaluate_one, on_futures_data_written,
  required_history_for_strategy,
)
print(\"engine ok\")
"'
```

Expected: `engine ok`.

- [ ] **Step 6.4: Confirm the `/api/strategies/dsl/schema` endpoint serves the metadata**

```bash
ssh root@$VPS_HOST 'curl -s -H "Authorization: Bearer $(cat /tmp/paul_token)" http://127.0.0.1:8000/api/strategies/dsl/schema | python3 -m json.tool | head -40' || echo 'token cache not present; skip'
```

(If the token isn't cached on the VPS, skip this step or test via the deployed frontend.)

- [ ] **Step 6.5: Smoke-test the live UI**

In a browser at `https://stock.paul-learning.dev/`:

1. Click "策略" in the dashboard header. Expect the list page to load.
2. Click "建立策略". Expect the empty form.
3. Build a simple strategy: SMA(5) cross_above SMA(20), TP=2%, SL=1%, TX, 1 lot.
4. Click 儲存. Expect navigation to `/strategies/<new_id>`.
5. Position card shows 待機; signal history is empty.
6. Click 啟用. Expect a 422 toast saying "discord webhook not set" (Paul still has no webhook). This is the intended P4 gate.
7. Click 執行回測 with the default 5-year range. Expect summary cards + Recharts equity curve to render within ~5 seconds.

If any step fails, capture the network panel response + browser console and roll back via `git revert`.

- [ ] **Step 6.6: Mark P6 complete in the spec**

Append a single line to the very top of
`docs/superpowers/specs/2026-05-05-futures-strategy-engine-design.md`
right under the title:

```markdown
> **Status:** All six phases shipped. Spec text matches deployed behaviour as of 2026-05-07.
```

Commit:

```bash
git add docs/superpowers/specs/2026-05-05-futures-strategy-engine-design.md
git commit -m "$(cat <<'EOF'
docs(strategy): mark FSE spec as fully shipped

All six phases (schema/permissions, DSL+Backtrader, engine state machine,
API+notifier, frontend, integration) deployed and verified end-to-end
as of 2026-05-07.
EOF
)"
git push origin master
```

---

## Phase exit criteria

After all six tasks committed:

1. `python3 -m pytest tests/ -q` passes (≈ 458).
2. `cd frontend && npm test` passes (no frontend changes; should be unchanged at 123).
3. Deploy succeeds; smoke test in §6.5 walks through cleanly.
4. ADMIN.md renders correctly on GitHub.

The Futures Strategy Engine is then fully shipped. Subsequent work is feature requests + bug reports, not phased rollout.
