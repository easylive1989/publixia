"""Scoreboard standings: scoring rule + ranking + DNP."""
from db.connection import get_connection
from repositories import posts as posts_repo
from repositories import tracked_accounts as accounts_repo
from repositories import trades as trades_repo
from services.scoreboard import compute_standings


def _acc(person_key: str) -> int:
    return next(a["id"] for a in accounts_repo.list_accounts() if a["person_key"] == person_key)


_seq = [0]


def _call(person_key: str, direction: str, ticker: str, pct_latest, ts: str = "2026-06-01T00:00:00"):
    """Create a post + one trade for a person, optionally with a latest return."""
    _seq[0] += 1
    pid, _ = posts_repo.upsert_post(
        _acc(person_key), "threads", f"P{_seq[0]}", "u", "body", ts)
    trades_repo.save_trades(
        pid, [{"raw_symbol": ticker, "ticker": ticker, "market": "US",
               "direction": direction, "confidence": 0.9}],
        model="m", prompt_version="v5")
    if pct_latest is not None:
        with get_connection() as c:
            c.execute(
                "INSERT INTO trade_price_tracking (post_id, ticker, market, base_price, pct_latest, status) "
                "VALUES (?,?,?,?,?,?)", (pid, ticker, "US", 100.0, pct_latest, "partial"))
    return pid


def _by_key(standings):
    return {s["person_key"]: s for s in standings}


def test_win_loss_and_cum_return():
    # dadnini: long winner (+10%), long loser (-5%), sell winner (price -8% → +8% pnl)
    _call("dadnini", "buy", "AAA", 0.10)
    _call("dadnini", "buy", "BBB", -0.05)
    _call("dadnini", "sell", "CCC", -0.08)

    s = _by_key(compute_standings())["dadnini"]
    assert s["win_count"] == 2          # +10% long, sell that dropped
    assert s["loss_count"] == 1         # -5% long
    assert s["win_rate"] == 2 / 3
    assert round(s["cum_return"], 4) == round(0.10 - 0.05 + 0.08, 4)  # 0.13
    assert s["dnp"] is False


def test_hold_excluded_and_unevaluated_not_counted():
    _call("aoi", "hold", "HLD", 0.20)        # hold → not a call at all
    _call("aoi", "buy", "PEN", None)         # no pct yet → 追蹤中, not scored
    s = _by_key(compute_standings())["aoi"]
    assert s["signal_count"] == 1            # the buy counts as a signal
    assert s["win_count"] == 0 and s["loss_count"] == 0
    assert s["dnp"] is True                  # no evaluated call


def test_dnp_when_no_calls():
    s = _by_key(compute_standings())["banini"]
    assert s["dnp"] is True
    assert s["win_rate"] is None and s["cum_return"] is None and s["rank"] is None


def test_ranking_by_cum_return_dnp_last():
    _call("dadnini", "buy", "D1", 0.30)      # cum +0.30
    _call("aoi", "buy", "A1", 0.05)          # cum +0.05
    standings = compute_standings()
    scored = [s for s in standings if not s["dnp"]]
    assert scored[0]["person_key"] == "dadnini" and scored[0]["rank"] == 1
    assert scored[1]["person_key"] == "aoi" and scored[1]["rank"] == 2
    # DNP people come after all ranked ones
    assert all(s["dnp"] for s in standings[len(scored):])


def test_scoreboard_route_shape():
    from fastapi.testclient import TestClient
    import main
    _call("dadnini", "buy", "RT1", 0.12)
    r = TestClient(main.app).get("/api/scoreboard")
    assert r.status_code == 200
    standings = r.json()["standings"]
    dad = next(s for s in standings if s["person_key"] == "dadnini")
    assert dad["rank"] == 1 and dad["win_count"] == 1
    assert {"win_rate", "cum_return", "form", "dnp", "signal_count"} <= dad.keys()


def test_form_newest_first_max5():
    # 6 evaluated calls; form keeps the 5 newest (newest ts first)
    for i, pct in enumerate([0.1, -0.1, 0.1, 0.1, -0.1, 0.1]):
        _call("gooaye", "buy", f"F{i}", pct, ts=f"2026-06-{i+1:02d}T00:00:00")
    s = _by_key(compute_standings())["gooaye"]
    assert len(s["form"]) == 5
    # newest is 2026-06-06 (+0.1 → win)
    assert s["form"][0] == "w"
