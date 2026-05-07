"""Spec §5.11: enabling a strategy needing more bars than the DB has → 422."""
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
