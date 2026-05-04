"""Common helpers shared across indicator modules."""
from datetime import datetime, timedelta, timezone


def percentile_rank(latest: float | None, history: list[float], min_n: int = 30) -> float | None:
    """Inclusive percentile rank: count(v <= latest) / total * 100.

    Returns None if `latest` is None or there are fewer than `min_n` clean samples.
    """
    if latest is None or len(history) < min_n:
        return None
    clean = [v for v in history if v is not None]
    if len(clean) < min_n:
        return None
    below = sum(1 for v in clean if v <= latest)
    return round(below / len(clean) * 100, 2)


def fetch_indicator_history(indicator: str, n: int) -> list[float]:
    """Get latest n values of a top-level indicator (oldest→newest)."""
    from repositories.indicators import get_indicator_history
    since = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=max(n * 3, 30))
    rows = get_indicator_history(indicator, since)
    values = [r["value"] for r in rows if r["value"] is not None]
    return values[-n:]
