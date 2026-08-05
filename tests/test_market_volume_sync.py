"""TWSE FMTQIK / Yahoo ^IXIC parsing + the two per-market sync jobs."""
from datetime import date, datetime, timezone
from unittest.mock import patch

import pytest

import core.nasdaq as nasdaq
import core.twse as twse
from core.errors import FetcherError, FetcherParseError
from core.markets import TW, US
from repositories import market_volume as repo
from services import market_volume_sync as sync


class _Resp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


# --------------------------------------------------------------------------
# TW — TWSE FMTQIK
# --------------------------------------------------------------------------

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
        {"date": "2026-07-30", "index_close": 39933.30, "turnover": 11469.0},
        {"date": "2026-07-31", "index_close": 43119.75, "turnover": 8877.0},
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
        return [{"date": f"{y:04d}-{m:02d}-15", "index_close": 10000.0, "turnover": 1000.0}]

    monkeypatch.setattr(sync, "fetch_month", fake_fetch)
    result = sync.run_market_volume_sync(today=date(2016, 3, 20))
    assert fetched == [(2016, 1), (2016, 2), (2016, 3)]
    assert result == {"months": 3, "rows": 3}
    assert repo.latest_date(TW) == "2016-03-15"


def test_sync_resumes_from_latest_stored_month(monkeypatch):
    monkeypatch.setattr(sync.time, "sleep", lambda s: None)
    repo.upsert_days(TW, [{"date": "2026-06-25", "index_close": 44571.76, "turnover": 16728.0}])
    fetched = []
    monkeypatch.setattr(sync, "fetch_month", lambda y, m: fetched.append((y, m)) or [])
    sync.run_market_volume_sync(today=date(2026, 7, 31))
    # re-fetches the latest stored month (catches its remaining days) + current
    assert fetched == [(2026, 6), (2026, 7)]


def test_upsert_days_is_idempotent_on_date():
    repo.upsert_days(TW, [{"date": "2026-07-31", "index_close": 1.0, "turnover": 2.0}])
    repo.upsert_days(TW, [{"date": "2026-07-31", "index_close": 43119.75, "turnover": 8877.0}])
    days = repo.list_days(TW)
    assert len(days) == 1
    assert days[0]["index_close"] == 43119.75


def test_markets_are_stored_side_by_side():
    """同一天在兩個市場各存一列，彼此不覆蓋、查詢也不互相看見。"""
    repo.upsert_days(TW, [{"date": "2026-07-31", "index_close": 43119.75, "turnover": 8877.0}])
    repo.upsert_days(US, [{"date": "2026-07-31", "index_close": 21500.0, "turnover": 62.5}])
    assert [r["index_close"] for r in repo.list_days(TW)] == [43119.75]
    assert [r["index_close"] for r in repo.list_days(US)] == [21500.0]


# --------------------------------------------------------------------------
# US — Yahoo ^IXIC
# --------------------------------------------------------------------------

def _stamp(y: int, m: int, d: int) -> int:
    """Yahoo daily bar 的 timestamp：交易日當天 09:30 ET ≈ 13:30 UTC。"""
    return int(datetime(y, m, d, 13, 30, tzinfo=timezone.utc).timestamp())


def _chart(timestamp, close, volume, error=None):
    return {
        "chart": {
            "result": [{
                "meta": {"symbol": "^IXIC", "currency": "USD"},
                "timestamp": timestamp,
                "indicators": {"quote": [{"close": close, "volume": volume}]},
            }],
            "error": error,
        }
    }


_IXIC = _chart(
    [_stamp(2026, 7, 30), _stamp(2026, 7, 31)],
    [21_450.12, 21_602.87],
    [6_240_000_000, 7_115_000_000],
)


def test_fetch_range_parses_dates_and_converts_volume_to_yi():
    with patch.object(nasdaq.requests, "get", return_value=_Resp(_IXIC)):
        rows = nasdaq.fetch_range(date(2026, 7, 30), date(2026, 7, 31))
    assert rows == [
        {"date": "2026-07-30", "index_close": 21450.12, "turnover": 62.4},
        {"date": "2026-07-31", "index_close": 21602.87, "turnover": 71.15},
    ]


def test_fetch_range_skips_null_bars_but_keeps_the_rest():
    payload = _chart(
        [_stamp(2026, 7, 29), _stamp(2026, 7, 30), _stamp(2026, 7, 31)],
        [None, 21_450.12, 21_602.87],
        [None, 6_240_000_000, 0],  # 半日盤/資料缺漏會出現 null 或 0
    )
    with patch.object(nasdaq.requests, "get", return_value=_Resp(payload)):
        rows = nasdaq.fetch_range(date(2026, 7, 29), date(2026, 7, 31))
    assert [r["date"] for r in rows] == ["2026-07-30"]


def test_fetch_range_empty_result_names_the_yahoo_error():
    payload = {"chart": {"result": [], "error": {"code": "Unauthorized"}}}
    with patch.object(nasdaq.requests, "get", return_value=_Resp(payload)):
        with pytest.raises(FetcherParseError) as e:
            nasdaq.fetch_range(date(2026, 7, 30), date(2026, 7, 31))
    assert "Unauthorized" in str(e.value)


def test_fetch_range_missing_close_names_the_keys_it_saw():
    payload = _chart([_stamp(2026, 7, 31)], None, [6_240_000_000])
    payload["chart"]["result"][0]["indicators"]["quote"][0] = {"open": [1.0], "volume": [1]}
    with patch.object(nasdaq.requests, "get", return_value=_Resp(payload)):
        with pytest.raises(FetcherParseError) as e:
            nasdaq.fetch_range(date(2026, 7, 31), date(2026, 7, 31))
    assert "open" in str(e.value) and "volume" in str(e.value)


def test_fetch_range_length_mismatch_raises():
    payload = _chart([_stamp(2026, 7, 30), _stamp(2026, 7, 31)], [21_450.12], [6_240_000_000])
    with patch.object(nasdaq.requests, "get", return_value=_Resp(payload)):
        with pytest.raises(FetcherParseError, match="長度對不上"):
            nasdaq.fetch_range(date(2026, 7, 30), date(2026, 7, 31))


def test_fetch_range_rejects_volume_of_the_wrong_magnitude():
    """成交金額（~1e11 美元）誤當成交股數送進來時要炸，不能安靜地判成天量。"""
    payload = _chart([_stamp(2026, 7, 31)], [21_602.87], [4_500_000_000_000])
    with patch.object(nasdaq.requests, "get", return_value=_Resp(payload)):
        with pytest.raises(FetcherParseError, match="不在合理區間"):
            nasdaq.fetch_range(date(2026, 7, 31), date(2026, 7, 31))


def test_fetch_range_all_null_is_a_failure_not_an_empty_result():
    payload = _chart([_stamp(2026, 7, 30), _stamp(2026, 7, 31)], [None, None], [None, None])
    with patch.object(nasdaq.requests, "get", return_value=_Resp(payload)):
        with pytest.raises(FetcherParseError, match="解不出任何交易日"):
            nasdaq.fetch_range(date(2026, 7, 30), date(2026, 7, 31))


def test_fetch_range_network_failure_is_a_fetcher_error():
    with patch.object(nasdaq.requests, "get", side_effect=nasdaq.requests.ConnectionError("boom")):
        with pytest.raises(FetcherError):
            nasdaq.fetch_range(date(2026, 7, 31), date(2026, 7, 31))


def test_nasdaq_sync_backfills_from_2016_when_empty(monkeypatch):
    seen = {}

    def fake_fetch(start, end):
        seen["range"] = (start, end)
        return [{"date": "2016-01-04", "index_close": 4903.09, "turnover": 21.5}]

    monkeypatch.setattr(sync, "fetch_range", fake_fetch)
    result = sync.run_nasdaq_volume_sync(today=date(2026, 8, 5))
    assert seen["range"] == (date(2016, 1, 1), date(2026, 8, 5))
    assert result["rows"] == 1
    assert repo.latest_date(US) == "2016-01-04"
    assert repo.latest_date(TW) is None


def test_nasdaq_sync_refetches_an_overlapping_window(monkeypatch):
    """往回多抓 10 天，把 Yahoo 可能給過的「盤中未收完」那根 bar 覆蓋掉。"""
    repo.upsert_days(US, [{"date": "2026-08-04", "index_close": 21_500.0, "turnover": 30.0}])
    seen = {}

    def fake_fetch(start, end):
        seen["range"] = (start, end)
        return [{"date": "2026-08-04", "index_close": 21_500.0, "turnover": 64.2}]

    monkeypatch.setattr(sync, "fetch_range", fake_fetch)
    sync.run_nasdaq_volume_sync(today=date(2026, 8, 5))
    assert seen["range"] == (date(2026, 7, 25), date(2026, 8, 5))
    assert repo.list_days(US)[0]["turnover"] == 64.2
