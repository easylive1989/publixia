"""TWSE breadth parsing, persistence, sync, and sentiment calculation."""
import math
from datetime import date
from unittest.mock import Mock

import pytest

from core.errors import FetcherParseError
from core.markets import TW
from core import twse_breadth
from repositories import market_breadth, market_volume
from services import market_breadth_sync
from services.market_sentiment import classify_sentiment, compute_sentiment


def _payload(day="20260915"):
    return {
        "stat": "OK",
        "date": day,
        "tables": [{
            "title": "漲跌證券數合計",
            "fields": ["類型", "整體市場", "股票"],
            "data": [
                ["上漲(漲停)", "3,552(16)", "207(5)"],
                ["下跌(跌停)", "8,814(79)", "790(1)"],
                ["持平", "979", "74"],
                ["未成交", "18,705", "3"],
            ],
        }],
    }


def _market_rows(n=600):
    return [
        {
            "date": f"D{i:04d}",
            "index_close": 10_000 * math.exp(0.0004 * i + 0.03 * math.sin(i / 19)),
            "turnover": 1_000 + i,
        }
        for i in range(n)
    ]


def test_parse_breadth_uses_stock_column_and_ignores_limit_subcount():
    assert twse_breadth.parse_payload(_payload(), "20260915") == {
        "date": "2026-09-15",
        "advancing": 207,
        "declining": 790,
        "unchanged": 74,
    }


def test_parse_breadth_accepts_legacy_schema():
    payload = _payload()
    table = payload.pop("tables")[0]
    payload["fields8"] = table["fields"]
    payload["data8"] = table["data"]
    assert twse_breadth.parse_payload(payload, "20260915")["advancing"] == 207


def test_parse_breadth_rejects_wrong_date_or_missing_table():
    with pytest.raises(FetcherParseError, match="日期不符"):
        twse_breadth.parse_payload(_payload("20260914"), "20260915")
    payload = _payload()
    payload["tables"] = []
    with pytest.raises(FetcherParseError, match="找不到"):
        twse_breadth.parse_payload(payload, "20260915")


def test_fetch_breadth_requests_compact_market_statistics(monkeypatch):
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = _payload()
    get = Mock(return_value=response)
    monkeypatch.setattr(twse_breadth.requests, "get", get)

    row = twse_breadth.fetch_day(date(2026, 9, 15))
    assert row["declining"] == 790
    assert get.call_args.kwargs["params"] == {
        "date": "20260915", "type": "MS", "response": "json",
    }


def test_breadth_repository_upserts():
    row = {"date": "2026-09-15", "advancing": 207, "declining": 790, "unchanged": 74}
    assert market_breadth.upsert_days(TW, [row]) == 1
    row["advancing"] = 208
    market_breadth.upsert_days(TW, [row])
    assert market_breadth.list_days(TW)[0]["advancing"] == 208
    assert market_breadth.existing_dates(TW) == {"2026-09-15"}


def test_sentiment_is_weighted_zero_to_hundred_reading():
    rows = _market_rows()
    target = rows[-1]["date"]
    breadth = [{"date": target, "advancing": 20, "declining": 70, "unchanged": 10}]
    reading = compute_sentiment(rows, breadth)[target]
    components = reading["components"]
    expected = (
        .25 * components["momentum"]
        + .20 * components["drawdown"]
        + .20 * components["volatility"]
        + .25 * components["breadth"]
        + .10 * components["deviation"]
    )
    assert reading["score"] == pytest.approx(expected)
    assert components["breadth"] == pytest.approx(25.0)
    assert 0 <= reading["score"] <= 100
    assert reading["method"] == "tw_fear_greed_proxy_v1"


def test_sentiment_requires_breadth_and_prior_history():
    rows = _market_rows()
    assert compute_sentiment(rows, []) == {}
    early = rows[300]["date"]  # only 49 prior price-signal rows, below the 252 minimum
    breadth = [{"date": early, "advancing": 1, "declining": 1, "unchanged": 0}]
    assert compute_sentiment(rows, breadth) == {}


@pytest.mark.parametrize("score,label", [
    (19.99, "極度恐懼"), (20, "恐懼"), (39.99, "恐懼"),
    (40, "中性"), (60, "中性"), (80, "貪婪"), (80.01, "極度貪婪"),
])
def test_sentiment_labels(score, label):
    assert classify_sentiment(score) == label


def test_breadth_sync_backfills_latest_missing_dates(monkeypatch):
    rows = [
        {"date": f"2026-09-{day:02d}", "index_close": 10_000 + day, "turnover": 1_000}
        for day in range(1, 6)
    ]
    market_volume.upsert_days(TW, rows)
    monkeypatch.setattr(market_breadth_sync, "_PAUSE_SECONDS", 0)
    monkeypatch.setattr(
        market_breadth_sync,
        "fetch_day",
        lambda day: {
            "date": day.isoformat(), "advancing": 500,
            "declining": 400, "unchanged": 100,
        },
    )
    result = market_breadth_sync.run_market_breadth_sync(
        today=date(2026, 9, 5), batch_size=2,
    )
    assert result == {"requested": 2, "rows": 2, "remaining": 3}
    assert market_breadth.existing_dates(TW) == {"2026-09-04", "2026-09-05"}
