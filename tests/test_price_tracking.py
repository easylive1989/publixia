"""Price-tracking runner + join into the trades payload (compute stubbed)."""
import services.price_tracking_runner as runner
from repositories import posts as posts_repo
from repositories import trades as trades_repo
from repositories import tracked_accounts as accounts_repo

WINDOW = {
    "base_date": "2026-05-01", "base_price": 100.0,
    "price_7d": 107.0, "price_1m": 130.0,
    "pct_7d": 0.07, "pct_1m": 0.30, "status": "done",
}


def _seed_trade():
    acc = accounts_repo.list_accounts()[0]
    pid, _ = posts_repo.upsert_post(
        acc["id"], "threads", "PX", "https://t/p/PX", "加碼台積電", "2026-05-01T03:00:00"
    )
    trades_repo.save_trades(
        pid,
        [{"raw_symbol": "台積電", "ticker": "2330", "market": "TW", "direction": "buy", "confidence": 0.8}],
        model="m", prompt_version="v1",
    )
    return pid


def test_runner_computes_and_join_exposes_pct(monkeypatch):
    pid = _seed_trade()
    monkeypatch.setattr(runner, "compute_window", lambda t, m, dt: dict(WINDOW))

    summary = runner.run_price_tracking()
    assert summary == {"updated": 1, "errors": 0}

    trade = trades_repo.list_trades_for_posts([pid])[pid][0]
    assert trade["ticker"] == "2330"
    assert round(trade["pct_7d"], 4) == 0.07
    assert round(trade["pct_1m"], 4) == 0.30
    assert trade["price_status"] == "done"
    assert trade["base_price"] == 100.0


def test_done_rows_not_recomputed(monkeypatch):
    _seed_trade()
    monkeypatch.setattr(runner, "compute_window", lambda t, m, dt: dict(WINDOW))
    runner.run_price_tracking()
    # second run: the done row is excluded from targets → nothing to update
    summary = runner.run_price_tracking()
    assert summary == {"updated": 0, "errors": 0}
