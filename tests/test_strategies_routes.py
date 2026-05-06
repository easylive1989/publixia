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
