"""DEPRECATED module path. Kept for backward compat with existing imports.

New code should import from services.alert_engine / services.alert_notifier.
"""
from services.alert_engine import (  # noqa: F401
    check_alerts,
    _check_streak, _get_stock_indicator_history, _pct_rank,
    _get_stock_revenue_yoy, _get_stock_quarterly_yoy, _get_stock_yearly_yoy,
)
from services.alert_notifier import (  # noqa: F401
    notify_triggered, send_to_discord,
)
from core.settings import settings  # noqa: F401
