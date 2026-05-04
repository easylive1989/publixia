"""Alert evaluation logic — registry-driven dispatch.

Each indicator's value-fetching lives in services/indicators/<group>.py.
This module wires conditions to the right provider and handles formatting.
"""
import logging

from services.alert_notifier import notify_triggered

logger = logging.getLogger(__name__)


# --- Backward-compat shims (test_alerts.py still imports these private helpers
#     by name; delegate to new locations under services/indicators/).
def _check_streak(values: list, condition: str, threshold: float,
                  expected_n: int | None = None) -> bool:
    """檢查 values 是否全部達門檻(streak_above 全 >= threshold,streak_below 全 <= threshold)。"""
    if condition not in ('streak_above', 'streak_below'):
        return False
    if not values or any(v is None for v in values):
        return False
    if expected_n is not None and len(values) < expected_n:
        return False
    if condition == 'streak_above':
        return all(v >= threshold for v in values)
    return all(v <= threshold for v in values)


def _get_stock_indicator_history(ticker: str, indicator_key: str, n: int) -> list[float]:
    """Compat shim: dispatch via registry to indicator's get_history."""
    from services.alert_registry import get_indicator
    from services import indicators  # noqa: F401
    spec = get_indicator("stock_indicator", indicator_key)
    if spec is None or spec.get_history is None:
        return []
    return spec.get_history(ticker, n)


def _pct_rank(value: float | None, history: list[float]) -> float | None:
    """Compat shim: delegates to services.indicators._helpers.percentile_rank."""
    from services.indicators._helpers import percentile_rank
    return percentile_rank(value, history)


def _get_stock_revenue_yoy(ticker: str) -> float | None:
    """Compat shim: delegates to services.indicators.stock_revenue."""
    from services.indicators.stock_revenue import _get_revenue_yoy
    return _get_revenue_yoy(ticker)


def _get_stock_quarterly_yoy(ticker: str, indicator_key: str) -> float | None:
    """Compat shim: delegates to services.indicators.stock_quarterly."""
    from services.indicators.stock_quarterly import _get_quarterly_yoy
    return _get_quarterly_yoy(ticker, key=indicator_key)


def _get_stock_yearly_yoy(ticker: str, indicator_key: str) -> float | None:
    """Compat shim: delegates to services.indicators.stock_yearly."""
    from services.indicators.stock_yearly import _get_yearly_yoy
    return _get_yearly_yoy(ticker, key=indicator_key)


def _format_value(target_type: str, target: str, value: float, spec) -> str:
    """Display formatting for the alert payload."""
    if target_type == "indicator" and spec is not None:
        unit = spec.unit
        if target == "fx":
            return f"{value:.4f} {unit}".strip()
        return f"{value:,.2f} {unit}".strip()
    return f"{value:,.4f}" if value < 100 else f"{value:,.2f}"


def _alert_display_name(target_type: str, target: str, indicator_key: str | None, spec) -> str:
    if spec is not None:
        if target_type == "indicator":
            return spec.label
        if target_type == "stock_indicator":
            return f"{target} {spec.label}"
    return target  # stock or unknown


def _build_payload(alert: dict, value: float | None, display_name: str, spec) -> dict:
    cond = alert["condition"]
    threshold = alert["threshold"]
    window_n = alert.get("window_n")
    target_type = alert["target_type"]

    def _fmt(v: float) -> str:
        if v is None:
            return "—"
        if target_type == "indicator":
            return _format_value(target_type, alert["target"], v, spec)
        if target_type == "stock_indicator":
            ik = alert.get("indicator_key")
            if ik in ("per", "pbr"):
                return f"{v:.2f}"
            if ik == "dividend_yield":
                return f"{v:.2f}%"
            if ik == "revenue":
                return f"{v:.2f}%"
            return f"{v:,.0f}"
        # stock
        return f"{v:,.4f}" if v < 100 else f"{v:,.2f}"

    value_str = _fmt(value) if value is not None else "—"
    threshold_str = _fmt(threshold)

    if cond == "above":
        crossed = "突破"
        color = 0xE74C3C
    elif cond == "below":
        crossed = "跌破"
        color = 0x3498DB
    elif cond == "streak_above":
        crossed = f"連 {window_n} 日突破"
        color = 0xE74C3C
    elif cond == "streak_below":
        crossed = f"連 {window_n} 日跌破"
        color = 0x3498DB
    elif cond == "percentile_above":
        crossed = "5y 百分位突破"
        color = 0xE74C3C
    elif cond == "percentile_below":
        crossed = "5y 百分位跌破"
        color = 0x3498DB
    elif cond == "yoy_above":
        crossed = "YoY 突破"
        color = 0xE74C3C
    elif cond == "yoy_below":
        crossed = "YoY 跌破"
        color = 0x3498DB
    else:
        crossed = cond
        color = 0x95A5A6

    embed = {
        "title": f"🚨 警示:{display_name}",
        "description": (
            f"**{display_name}** 目前 **{value_str}**,已{crossed}門檻 **{threshold_str}**。\n"
            f"_警示已自動停用,請至 Dashboard 重新啟用。_"
        ),
        "color": color,
    }
    return {"embeds": [embed]}


def _resolve_value(spec, alert, target, value, cond, indicator_key):
    """Return the current value to compare against threshold."""
    if spec is None:
        # target_type == "stock"; uses passed-in value directly
        return value
    if cond in ("above", "below"):
        if spec.target_type == "indicator" and value is not None:
            return value
        return spec.get_latest_value(target)
    if cond in ("streak_above", "streak_below"):
        if spec.get_history is None:
            return None
        n = alert.get("window_n") or 5
        history = spec.get_history(target, n)
        return history[-1] if history else None
    if cond in ("percentile_above", "percentile_below"):
        return spec.get_percentile(target) if spec.get_percentile else None
    if cond in ("yoy_above", "yoy_below"):
        return spec.get_yoy(target) if spec.get_yoy else None
    return None


def _compare(value: float, threshold: float, cond: str, window_n: int | None,
             spec, target: str) -> bool:
    """Return whether the alert should trigger."""
    if cond in ("above", "percentile_above", "yoy_above"):
        return value >= threshold
    if cond in ("below", "percentile_below", "yoy_below"):
        return value <= threshold
    if cond in ("streak_above", "streak_below"):
        n = window_n or 5
        if spec is None or spec.get_history is None:
            return False
        history = spec.get_history(target, n)
        if not history or any(v is None for v in history) or len(history) < n:
            return False
        if cond == "streak_above":
            return all(v >= threshold for v in history)
        return all(v <= threshold for v in history)
    return False


def check_alerts(target_type: str, target: str, value: float | None = None,
                 *, indicator_key: str | None = None, display_name: str | None = None) -> None:
    """Evaluate alerts and notify on trigger.

    Dispatch via services.alert_registry: looks up IndicatorSpec by
    (target_type, indicator_key_or_target) and uses spec's value providers.
    """
    from repositories.alerts import get_active_alerts, mark_alert_triggered
    from services.alert_registry import get_indicator
    from services import indicators  # noqa: F401  ← trigger auto-register

    all_active = get_active_alerts(target_type, target)
    if target_type == "stock_indicator":
        active_alerts = [a for a in all_active if a.get("indicator_key") == indicator_key]
    else:
        active_alerts = all_active

    if target_type == "indicator":
        spec = get_indicator("indicator", target)
    elif target_type == "stock_indicator":
        spec = get_indicator("stock_indicator", indicator_key) if indicator_key else None
    else:
        spec = None  # target_type == "stock"

    name = display_name or _alert_display_name(target_type, target, indicator_key, spec)

    for alert in active_alerts:
        cond = alert["condition"]
        threshold = alert["threshold"]
        if spec is not None and not spec.supports(cond):
            continue
        cur_value = _resolve_value(spec, alert, target, value, cond, indicator_key)
        if cur_value is None:
            continue
        triggered = _compare(cur_value, threshold, cond, alert.get("window_n"), spec, target)
        if triggered:
            payload = _build_payload(alert, cur_value, name, spec)
            notify_triggered(payload, alert_id=alert["id"])
            mark_alert_triggered(alert["id"], cur_value)
