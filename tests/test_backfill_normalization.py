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
