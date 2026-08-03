"""TWSE FMTQIK parsing + incremental month-by-month sync."""
from datetime import date
from unittest.mock import patch

import pytest

import core.twse as twse
from core.errors import FetcherParseError
from repositories import market_volume as repo
from services import market_volume_sync as sync


class _Resp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


_FMTQIK = {
    "stat": "OK",
    "fields": ["日期", "成交股數", "成交金額", "成交筆數", "發行量加權股價指數", "漲跌點數"],
    "data": [
        ["115/07/30", "6,163,222,519", "1,146,900,000,000", "2,470,626", "39,933.30", "110.26"],
        ["115/07/31", "5,000,000,000", "887,700,000,000", "2,000,000", "43,119.75", "-55.00"],
    ],
}


def test_fetch_month_parses_roc_dates_and_units():
    with patch.object(twse.requests, "get", return_value=_Resp(_FMTQIK)):
        rows = twse.fetch_month(2026, 7)
    assert rows == [
        {"date": "2026-07-30", "taiex_close": 39933.30, "turnover": 11469.0},
        {"date": "2026-07-31", "taiex_close": 43119.75, "turnover": 8877.0},
    ]


def test_fetch_month_no_data_month_is_empty():
    with patch.object(
        twse.requests, "get",
        return_value=_Resp({"stat": "很抱歉，沒有符合條件的資料!"}),
    ):
        assert twse.fetch_month(2027, 1) == []


def test_fetch_month_malformed_row_raises_parse_error():
    bad = {"stat": "OK", "data": [["115/07/31", "1", "not-a-number", "1", "2", "3"]]}
    with patch.object(twse.requests, "get", return_value=_Resp(bad)):
        with pytest.raises(FetcherParseError):
            twse.fetch_month(2026, 7)


def test_month_range_inclusive_across_years():
    assert twse.month_range(date(2025, 11, 15), date(2026, 2, 1)) == [
        (2025, 11), (2025, 12), (2026, 1), (2026, 2),
    ]


def test_sync_backfills_from_2016_when_empty(monkeypatch):
    monkeypatch.setattr(sync.time, "sleep", lambda s: None)
    fetched = []

    def fake_fetch(y, m):
        fetched.append((y, m))
        return [{"date": f"{y:04d}-{m:02d}-15", "taiex_close": 10000.0, "turnover": 1000.0}]

    monkeypatch.setattr(sync, "fetch_month", fake_fetch)
    result = sync.run_market_volume_sync(today=date(2016, 3, 20))
    assert fetched == [(2016, 1), (2016, 2), (2016, 3)]
    assert result == {"months": 3, "rows": 3}
    assert repo.latest_date() == "2016-03-15"


def test_sync_resumes_from_latest_stored_month(monkeypatch):
    monkeypatch.setattr(sync.time, "sleep", lambda s: None)
    repo.upsert_days([{"date": "2026-06-25", "taiex_close": 44571.76, "turnover": 16728.0}])
    fetched = []
    monkeypatch.setattr(sync, "fetch_month", lambda y, m: fetched.append((y, m)) or [])
    sync.run_market_volume_sync(today=date(2026, 7, 31))
    # re-fetches the latest stored month (catches its remaining days) + current
    assert fetched == [(2026, 6), (2026, 7)]


def test_upsert_days_is_idempotent_on_date():
    repo.upsert_days([{"date": "2026-07-31", "taiex_close": 1.0, "turnover": 2.0}])
    repo.upsert_days([{"date": "2026-07-31", "taiex_close": 43119.75, "turnover": 8877.0}])
    days = repo.list_days()
    assert len(days) == 1
    assert days[0]["taiex_close"] == 43119.75
