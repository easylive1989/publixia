"""Tests for /api/strategies/* — read endpoints only (Task 4)."""
import json

import pytest
from fastapi.testclient import TestClient

from db.connection import get_connection
from main import app
from repositories.strategies import create_strategy, write_signal


client = TestClient(app)


def _grant_permission_to_paul():
    with get_connection() as conn:
        conn.execute("UPDATE users SET can_use_strategy=1 WHERE id=1")
        conn.commit()


def _good_dsls():
    return dict(
        entry_dsl={"version": 1,
                   "all": [{"left": {"field": "close"}, "op": "gt",
                            "right": {"const": 100}}]},
        take_profit_dsl={"version": 1, "type": "pct", "value": 2.0},
        stop_loss_dsl  ={"version": 1, "type": "pct", "value": 1.0},
    )


def test_list_strategies_403_without_permission():
    r = client.get("/api/strategies")
    assert r.status_code == 403


def test_list_strategies_returns_user_rows():
    _grant_permission_to_paul()
    sid = create_strategy(user_id=1, name="s1", direction="long",
                          contract="TX", contract_size=1, **_good_dsls())
    r = client.get("/api/strategies")
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, list)
    names = [s["name"] for s in body]
    assert "s1" in names


def test_list_strategies_excludes_other_users():
    _grant_permission_to_paul()
    with get_connection() as conn:
        conn.execute("INSERT INTO users (name) VALUES ('alice')")
        conn.commit()
    create_strategy(user_id=2, name="alice_strategy", direction="long",
                    contract="TX", contract_size=1, **_good_dsls())

    create_strategy(user_id=1, name="paul_strategy",
                    direction="long", contract="TX",
                    contract_size=1, **_good_dsls())

    body = client.get("/api/strategies").json()
    names = [s["name"] for s in body]
    assert "paul_strategy" in names
    assert "alice_strategy" not in names


def test_get_one_strategy():
    _grant_permission_to_paul()
    sid = create_strategy(user_id=1, name="x", direction="short",
                          contract="MTX", contract_size=2, **_good_dsls())
    r = client.get(f"/api/strategies/{sid}")
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == sid
    assert body["direction"] == "short"
    assert body["contract"] == "MTX"
    assert body["entry_dsl"]["all"][0]["op"] == "gt"


def test_get_one_strategy_404_when_not_owned():
    _grant_permission_to_paul()
    with get_connection() as conn:
        conn.execute("INSERT INTO users (name) VALUES ('alice')")
        conn.commit()
    other = create_strategy(user_id=2, name="alice_only", direction="long",
                            contract="TX", contract_size=1, **_good_dsls())
    r = client.get(f"/api/strategies/{other}")
    assert r.status_code == 404


def test_get_signals_returns_newest_first():
    _grant_permission_to_paul()
    sid = create_strategy(user_id=1, name="s", direction="long",
                          contract="TX", contract_size=1, **_good_dsls())
    write_signal(sid, kind="ENTRY_SIGNAL", signal_date="2026-01-15",
                 close_at_signal=100.0)
    write_signal(sid, kind="EXIT_SIGNAL", signal_date="2026-01-22",
                 close_at_signal=120.0, exit_reason="TAKE_PROFIT")

    r = client.get(f"/api/strategies/{sid}/signals")
    assert r.status_code == 200
    body = r.json()
    assert [s["kind"] for s in body] == ["EXIT_SIGNAL", "ENTRY_SIGNAL"]


def test_get_dsl_schema_lists_all_indicators():
    _grant_permission_to_paul()
    r = client.get("/api/strategies/dsl/schema")
    assert r.status_code == 200
    body = r.json()
    indicator_names = [i["name"] for i in body["indicators"]]
    assert set(indicator_names) == {
        "sma", "ema", "rsi", "macd", "bbands", "atr", "kd",
        "highest", "lowest", "change_pct",
    }
    assert "cross_above" in body["operators"]
    assert "close" in body["fields"]


def test_dsl_schema_indicators_match_runtime_models():
    """Drift guard: every indicator in DSL_SCHEMA must round-trip through
    the Pydantic models."""
    _grant_permission_to_paul()
    body = client.get("/api/strategies/dsl/schema").json()
    from services.strategy_dsl.models import ExprNode
    for ind in body["indicators"]:
        d = {"indicator": ind["name"]}
        for p in ind["params"]:
            if "default" in p:
                d[p["name"]] = p["default"]
            elif p["type"] == "int":
                d[p["name"]] = p["min"]
            elif p["type"] == "float":
                d[p["name"]] = p["min"] or 1.0
        ExprNode.validate_python(d)


def test_create_strategy_happy_path():
    _grant_permission_to_paul()
    body = {
        "name": "rsi_long",
        "direction": "long",
        "contract": "TX",
        "contract_size": 1,
        "max_hold_days": 10,
        **_good_dsls(),
    }
    r = client.post("/api/strategies", json=body)
    assert r.status_code == 200, r.text
    new_id = r.json()["id"]
    assert new_id > 0
    r2 = client.get(f"/api/strategies/{new_id}")
    assert r2.json()["name"] == "rsi_long"
    assert r2.json()["state"] == "idle"


def test_create_strategy_rejects_invalid_dsl():
    _grant_permission_to_paul()
    bad = {
        "name": "bad",
        "direction": "long",
        "contract": "TX",
        "contract_size": 1,
        "entry_dsl": {"version": 1, "all": [{"left": {"var": "entry_price"},
                                              "op": "gt", "right": {"const": 0}}]},
        "take_profit_dsl": {"version": 1, "type": "pct", "value": 2.0},
        "stop_loss_dsl":   {"version": 1, "type": "pct", "value": 1.0},
    }
    r = client.post("/api/strategies", json=bad)
    assert r.status_code == 422
    assert "entry_price" in r.text


def test_update_strategy_partial():
    _grant_permission_to_paul()
    sid = create_strategy(user_id=1, name="orig", direction="long",
                          contract="TX", contract_size=1, **_good_dsls())
    r = client.patch(f"/api/strategies/{sid}",
                     json={"name": "renamed", "contract_size": 3})
    assert r.status_code == 200
    after = client.get(f"/api/strategies/{sid}").json()
    assert after["name"] == "renamed"
    assert after["contract_size"] == 3


def test_update_strategy_in_position_freezes_dsl_fields():
    """Spec §9d3: when in position (state != idle), only metadata can be edited."""
    _grant_permission_to_paul()
    sid = create_strategy(user_id=1, name="in_pos", direction="long",
                          contract="TX", contract_size=1, **_good_dsls())
    from repositories.strategies import update_strategy_state
    update_strategy_state(sid, state="open",
                          entry_signal_date="2026-01-15",
                          entry_fill_date="2026-01-16",
                          entry_fill_price=200.0)

    r = client.patch(f"/api/strategies/{sid}",
                     json={"entry_dsl": _good_dsls()["entry_dsl"]})
    assert r.status_code == 422
    assert "in_position" in r.text or "in position" in r.text

    r2 = client.patch(f"/api/strategies/{sid}",
                      json={"name": "still_renamable"})
    assert r2.status_code == 200


def test_delete_strategy_cascades_signals():
    _grant_permission_to_paul()
    sid = create_strategy(user_id=1, name="del_me", direction="long",
                          contract="TX", contract_size=1, **_good_dsls())
    write_signal(sid, kind="ENTRY_SIGNAL", signal_date="2026-01-15",
                 close_at_signal=100.0)

    r = client.delete(f"/api/strategies/{sid}")
    assert r.status_code == 200
    r2 = client.get(f"/api/strategies/{sid}")
    assert r2.status_code == 404


def test_enable_requires_webhook_set():
    _grant_permission_to_paul()
    sid = create_strategy(user_id=1, name="x", direction="long",
                          contract="TX", contract_size=1, **_good_dsls())
    r = client.post(f"/api/strategies/{sid}/enable")
    assert r.status_code == 422
    assert "webhook" in r.text


def test_enable_passes_when_webhook_set():
    _grant_permission_to_paul()
    with get_connection() as conn:
        conn.execute(
            "UPDATE users SET discord_webhook_url=? WHERE id=1",
            ("https://discord.com/api/webhooks/1/" + "x" * 60,),
        )
        conn.commit()
    sid = create_strategy(user_id=1, name="x", direction="long",
                          contract="TX", contract_size=1, **_good_dsls())
    r = client.post(f"/api/strategies/{sid}/enable")
    assert r.status_code == 200
    after = client.get(f"/api/strategies/{sid}").json()
    assert after["notify_enabled"] is True


def test_disable_route():
    _grant_permission_to_paul()
    sid = create_strategy(user_id=1, name="x", direction="long",
                          contract="TX", contract_size=1,
                          notify_enabled=True, **_good_dsls())
    r = client.post(f"/api/strategies/{sid}/disable")
    assert r.status_code == 200
    after = client.get(f"/api/strategies/{sid}").json()
    assert after["notify_enabled"] is False


def test_force_close_only_when_in_position():
    _grant_permission_to_paul()
    sid = create_strategy(user_id=1, name="x", direction="long",
                          contract="TX", contract_size=1, **_good_dsls())
    r = client.post(f"/api/strategies/{sid}/force_close")
    assert r.status_code == 422
    assert "not in position" in r.text or "state" in r.text


def test_force_close_writes_exit_filled_manual_reset():
    _grant_permission_to_paul()
    sid = create_strategy(user_id=1, name="x", direction="long",
                          contract="TX", contract_size=1, **_good_dsls())
    from repositories.strategies import update_strategy_state
    from repositories.futures import save_futures_daily_rows
    update_strategy_state(sid, state="open",
                          entry_signal_date="2026-01-15",
                          entry_fill_date="2026-01-16",
                          entry_fill_price=200.0)
    save_futures_daily_rows([{
        "symbol": "TX", "date": "2026-01-25", "contract_date": "202604",
        "open": 210.0, "high": 215.0, "low": 209.0, "close": 212.0,
        "volume": 1000, "open_interest": None, "settlement": None,
    }])

    r = client.post(f"/api/strategies/{sid}/force_close")
    assert r.status_code == 200

    after = client.get(f"/api/strategies/{sid}").json()
    assert after["state"] == "idle"

    sigs = client.get(f"/api/strategies/{sid}/signals").json()
    assert sigs[0]["kind"] == "EXIT_FILLED"
    assert sigs[0]["exit_reason"] == "MANUAL_RESET"


def test_reset_strategy_clears_all():
    _grant_permission_to_paul()
    sid = create_strategy(user_id=1, name="x", direction="long",
                          contract="TX", contract_size=1, **_good_dsls())
    write_signal(sid, kind="ENTRY_SIGNAL", signal_date="2026-01-15",
                 close_at_signal=200.0)
    from repositories.strategies import mark_strategy_error
    mark_strategy_error(sid, "boom")

    r = client.post(f"/api/strategies/{sid}/reset")
    assert r.status_code == 200

    after = client.get(f"/api/strategies/{sid}").json()
    assert after["state"] == "idle"
    assert after["last_error"] is None
    sigs = client.get(f"/api/strategies/{sid}/signals").json()
    assert sigs == []
