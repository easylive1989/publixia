"""Alert registry unit tests."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../backend"))

import pytest
import importlib

import services.alert_registry as registry_mod
from services.alert_registry import (
    IndicatorSpec, register_indicator, get_indicator, list_indicators, all_indicators,
)


@pytest.fixture(autouse=True)
def reset_registry():
    """Snapshot and restore registry state between tests."""
    importlib.reload(registry_mod)
    yield
    importlib.reload(registry_mod)


def _make_spec(key: str = "test_a", target_type: str = "indicator", **kw) -> IndicatorSpec:
    return IndicatorSpec(
        key=key,
        label=kw.get("label", "Test"),
        unit=kw.get("unit", ""),
        target_type=target_type,
        supported_conditions=kw.get("supported_conditions", {"above"}),
        get_latest_value=lambda _t: 0.0,
    )


def test_register_and_get_indicator():
    spec = _make_spec(key="taiex", target_type="indicator")
    registry_mod.register_indicator(spec)
    assert registry_mod.get_indicator("indicator", "taiex") is spec


def test_register_and_get_stock_indicator():
    spec = _make_spec(key="per", target_type="stock_indicator")
    registry_mod.register_indicator(spec)
    assert registry_mod.get_indicator("stock_indicator", "per") is spec


def test_same_key_in_both_registries_does_not_collide():
    """`margin_balance` exists at both indicator-level (chip_total) and stock-level (chip_stock)."""
    indicator_spec = _make_spec(key="margin_balance", target_type="indicator", label="台股融資餘額")
    stock_spec = _make_spec(key="margin_balance", target_type="stock_indicator", label="融資餘額")
    registry_mod.register_indicator(indicator_spec)
    registry_mod.register_indicator(stock_spec)

    assert registry_mod.get_indicator("indicator", "margin_balance") is indicator_spec
    assert registry_mod.get_indicator("stock_indicator", "margin_balance") is stock_spec


def test_unknown_target_type_raises():
    spec = _make_spec()
    spec.target_type = "weather"
    with pytest.raises(ValueError, match="Unsupported target_type"):
        registry_mod.register_indicator(spec)


def test_get_indicator_unknown_returns_none():
    assert registry_mod.get_indicator("indicator", "nonexistent") is None
    assert registry_mod.get_indicator("stock_indicator", "nonexistent") is None
    assert registry_mod.get_indicator("weather", "anything") is None


def test_list_indicators_sorted_by_key():
    registry_mod.register_indicator(_make_spec(key="zeta", target_type="indicator"))
    registry_mod.register_indicator(_make_spec(key="alpha", target_type="indicator"))
    registry_mod.register_indicator(_make_spec(key="middle", target_type="indicator"))
    keys = [s.key for s in registry_mod.list_indicators("indicator")]
    assert keys == ["alpha", "middle", "zeta"]


def test_all_indicators_returns_both_buckets():
    registry_mod.register_indicator(_make_spec(key="taiex", target_type="indicator"))
    registry_mod.register_indicator(_make_spec(key="per", target_type="stock_indicator"))
    out = registry_mod.all_indicators()
    assert [s.key for s in out["indicator"]] == ["taiex"]
    assert [s.key for s in out["stock_indicator"]] == ["per"]


def test_supports_returns_membership():
    spec = _make_spec(supported_conditions={"above", "streak_above"})
    assert spec.supports("above") is True
    assert spec.supports("streak_above") is True
    assert spec.supports("below") is False
