"""TWSE BFI82U parsing, persistence, sync batching, and API enrichment."""
import math
from datetime import date
from unittest.mock import patch

import pytest

import core.twse_institutional as twse
from core.errors import FetcherParseError
from core.markets import TW
from repositories import institutional_flow as repo
from repositories import market_volume
from services import institutional_flow_sync as sync
from services.market_heat import get_market_heat


class _Resp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


_BFI82U = {
    "stat": "OK",
    "date": "20260901",
    "data": [
        ["自營商(自行買賣)", "15,831,000,000", "12,674,000,000", "3,157,000,000"],
        ["自營商(避險)", "46,908,000,000", "33,735,000,000", "13,173,000,000"],
        ["投信", "39,106,000,000", "26,005,000,000", "13,101,000,000"],
        ["外資及陸資(不含外資自營商)", "401,999,000,000", "375,291,000,000", "26,708,000,000"],
        ["外資自營商", "0", "0", "0"],
        ["合計", "503,844,000,000", "447,705,000,000", "56,139,000,000"],
    ],
}


def test_fetch_day_parses_labels_and_integer_yuan():
    with patch.object(twse.requests, "get", return_value=_Resp(_BFI82U)):
        row = twse.fetch_day(date(2026, 9, 1))
    assert row["date"] == "2026-09-01"
    assert row["dealer_proprietary_buy"] == 15_831_000_000
    assert row["dealer_hedge_sell"] == 33_735_000_000
    assert row["foreign_buy"] == 401_999_000_000
    assert row["total_sell"] == 447_705_000_000


def test_fetch_day_no_data_is_none():
    with patch.object(twse.requests, "get", return_value=_Resp({"stat": "沒有符合條件的資料"})):
        assert twse.fetch_day(date(2026, 9, 2)) is None


def test_fetch_day_rejects_wrong_date_and_bad_difference():
    wrong_date = {**_BFI82U, "date": "20260831"}
    with patch.object(twse.requests, "get", return_value=_Resp(wrong_date)):
        with pytest.raises(FetcherParseError):
            twse.fetch_day(date(2026, 9, 1))

    bad = {**_BFI82U, "data": [list(row) for row in _BFI82U["data"]]}
    bad["data"][0][3] = "1"
    with patch.object(twse.requests, "get", return_value=_Resp(bad)):
        with pytest.raises(FetcherParseError):
            twse.fetch_day(date(2026, 9, 1))


def _raw(iso: str, multiplier: int = 1) -> dict:
    return {
        "date": iso,
        "dealer_proprietary_buy": 200 * multiplier,
        "dealer_proprietary_sell": 100 * multiplier,
        "dealer_hedge_buy": 400 * multiplier,
        "dealer_hedge_sell": 250 * multiplier,
        "trust_buy": 300 * multiplier,
        "trust_sell": 200 * multiplier,
        "foreign_buy": 1000 * multiplier,
        "foreign_sell": 800 * multiplier,
        "foreign_dealer_buy": 0,
        "foreign_dealer_sell": 0,
        "total_buy": 1900 * multiplier,
        "total_sell": 1350 * multiplier,
    }


def test_repository_upsert_is_idempotent():
    repo.upsert_days(TW, [_raw("2026-09-01")])
    repo.upsert_days(TW, [_raw("2026-09-01", 2)])
    rows = repo.list_days(TW)
    assert len(rows) == 1
    assert rows[0]["foreign_buy"] == 2000


def test_sync_prioritises_recent_missing_dates_and_refreshes_latest(monkeypatch):
    market_volume.upsert_days(TW, [
        {"date": f"2026-09-0{day}", "index_close": 10000 + day, "turnover": 1000}
        for day in range(1, 5)
    ])
    repo.upsert_days(TW, [_raw("2026-09-04")])
    fetched = []
    monkeypatch.setattr(sync.time, "sleep", lambda _: None)

    def fake_fetch(day):
        fetched.append(day.isoformat())
        return _raw(day.isoformat())

    monkeypatch.setattr(sync, "fetch_day", fake_fetch)
    result = sync.run_institutional_flow_sync(today=date(2026, 9, 4), batch_size=2)
    assert fetched == ["2026-09-04", "2026-09-03", "2026-09-02"]
    assert result == {"requested": 3, "rows": 3, "remaining": 1}


def test_early_sync_only_refreshes_latest(monkeypatch):
    market_volume.upsert_days(TW, [
        {"date": f"2026-09-0{day}", "index_close": 10000 + day, "turnover": 1000}
        for day in range(1, 5)
    ])
    fetched = []

    def fake_fetch(day):
        fetched.append(day.isoformat())
        return _raw(day.isoformat())

    monkeypatch.setattr(sync, "fetch_day", fake_fetch)
    result = sync.run_institutional_flow_early_sync(today=date(2026, 9, 4))
    assert fetched == ["2026-09-04"]
    assert result == {"requested": 1, "rows": 1, "remaining": 3}


def test_market_heat_attaches_billion_amounts_and_turnover_ratio():
    rows = []
    for index in range(60):
        close = 10000 + index * 10
        rows.append({
            "date": f"2026-{1 + index // 28:02d}-{1 + index % 28:02d}",
            "index_close": close,
            "turnover": math.exp(-7.75 + 1.608 * math.log(close)),
        })
    market_volume.upsert_days(TW, rows)
    latest = rows[-1]
    raw = _raw(latest["date"], 100_000_000)
    repo.upsert_days(TW, [raw])

    payload = get_market_heat(days=1)
    institutional = payload["latest"]["institutional"]
    assert institutional["dealer_proprietary"] == {
        "buy": 200.0, "sell": 100.0, "net": 100.0,
    }
    assert institutional["dealer"]["net"] == 250.0
    assert institutional["foreign"]["net"] == 200.0
    expected_ratio = (1900 + 1350) / (2 * latest["turnover"]) * 100
    assert institutional["turnover_ratio"] == pytest.approx(expected_ratio)
