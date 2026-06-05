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
