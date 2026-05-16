"""Tests for fetchers.group_volume.

FinMind (industry map) and TWSE (per-day price feed) are both stubbed —
these tests exercise the filtering / aggregation logic, never the network.
"""
import fetchers.group_volume as gv


def _info_rows(*entries: tuple[str, str, str]) -> list[dict]:
    """Helper to build a TaiwanStockInfo response. Each entry is
    ``(stock_id, type, industry_category)``."""
    return [
        {"stock_id": sid, "type": kind, "industry_category": ind}
        for sid, kind, ind in entries
    ]


def _patch_industry_map(monkeypatch, info_rows: list[dict]):
    """Stub FinMind's ``TaiwanStockInfo`` (still Free-tier OK)."""
    def fake_request(dataset: str, start_date: str, end_date: str | None = None):
        if dataset == "TaiwanStockInfo":
            return info_rows
        raise AssertionError(f"unexpected dataset {dataset}")
    monkeypatch.setattr(gv, "request", fake_request)


def test_industry_map_excludes_otc_etf_etn_and_blanks(monkeypatch):
    _patch_industry_map(monkeypatch, _info_rows(
        ("2330", "twse",  "半導體業"),
        ("0050", "twse",  "ETF"),           # exclude
        ("0056", "twse",  "受益證券"),       # exclude
        ("00679B", "twse", "ETN"),          # exclude
        ("3008", "twse",  "光電業"),
        ("9999", "twse",  ""),              # blank → exclude
        ("8888", "twse",  None),            # None → exclude
        ("5483", "tpex",  "半導體業"),       # OTC → exclude
    ))
    mapping = gv._load_industry_map()
    assert mapping == {"2330": "半導體業", "3008": "光電業"}


def test_fetch_industry_volume_aggregates_known_stocks_only(monkeypatch):
    _patch_industry_map(monkeypatch, _info_rows(
        ("2330", "twse", "半導體業"),
        ("2454", "twse", "半導體業"),
        ("3008", "twse", "光電業"),
        ("0050", "twse", "ETF"),     # in price feed but skipped (not in map)
    ))
    _patch_twse(monkeypatch, {
        "20260515": _twse_payload([
            ("2330",    "50000", "100000000"),
            ("2454",    "30000",  "80000000"),
            ("3008",    "10000",  "20000000"),
            ("0050",    "99999", "999999999"),  # skipped
            ("UNKNOWN",     "1",         "1"),  # skipped
        ]),
    })

    aggregates = gv.fetch_industry_volume("2026-05-15")

    by_industry = {a["group_code"]: a for a in aggregates}
    assert set(by_industry) == {"半導體業", "光電業"}
    semi = by_industry["半導體業"]
    assert semi["total_value"]  == 180_000_000.0
    assert semi["total_volume"] == 80_000
    assert semi["stock_count"]  == 2
    assert by_industry["光電業"]["total_value"]  == 20_000_000.0
    assert by_industry["光電業"]["stock_count"]  == 1


def test_fetch_industry_volume_range_groups_by_date(monkeypatch):
    _patch_industry_map(monkeypatch, _info_rows(
        ("2330", "twse", "半導體業"),
        ("3008", "twse", "光電業"),
    ))
    _patch_twse(monkeypatch, {
        "20260514": _twse_payload([
            ("2330", "1", "100"),
            ("3008", "2", "200"),
        ]),
        "20260515": _twse_payload([
            ("2330", "3", "110"),
        ]),
    })
    by_date = gv.fetch_industry_volume_range("2026-05-14", "2026-05-15")

    assert sorted(by_date) == ["2026-05-14", "2026-05-15"]
    d1 = {a["group_code"]: a for a in by_date["2026-05-14"]}
    assert d1["半導體業"]["total_value"] == 100.0
    assert d1["光電業"]["total_value"]   == 200.0
    assert by_date["2026-05-15"] == [{
        "group_code": "半導體業", "group_name": "半導體業",
        "total_value": 110.0, "total_volume": 3, "stock_count": 1,
    }]


def test_fetch_industry_volume_range_skips_non_trading_days(monkeypatch):
    """Weekend / holiday TWSE responses are dropped from the result."""
    _patch_industry_map(monkeypatch, _info_rows(("2330", "twse", "半導體業")))
    _patch_twse(monkeypatch, {
        "20260514": _twse_payload([("2330", "1", "100")]),
        # 20260515 deliberately missing → TWSE no-data shape → skipped
    })
    by_date = gv.fetch_industry_volume_range("2026-05-14", "2026-05-15")
    assert list(by_date) == ["2026-05-14"]


def test_fetch_industry_volume_returns_empty_for_holiday(monkeypatch):
    """Weekend: TWSE returns no data; fetcher must not crash."""
    _patch_industry_map(monkeypatch, _info_rows(("2330", "twse", "半導體業")))
    _patch_twse(monkeypatch, {})  # date not present → no-data response
    assert gv.fetch_industry_volume("2026-05-16") == []  # 週六


class _FakeResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def _twse_payload(rows: list[tuple[str, str, str]]) -> dict:
    """Build a TWSE MI_INDEX-shaped response.

    Each ``rows`` entry is ``(stock_id, trading_volume_str, trading_money_str)``
    where the numeric strings may contain thousands separators — same as
    the real TWSE feed.
    """
    return {
        "stat": "OK",
        "tables": [
            {
                "title":  "115年05月15日 大盤統計資訊",
                "fields": ["成交統計", "成交金額(元)", "成交股數(股)", "成交筆數"],
                "data":   [["全部市場", "1", "1", "1"]],
            },
            {
                "title":  "115年05月15日 每日收盤行情(全部)",
                "fields": [
                    "證券代號", "證券名稱", "成交股數", "成交筆數", "成交金額",
                    "開盤價", "最高價", "最低價", "收盤價", "漲跌(+/-)",
                    "漲跌價差", "最後揭示買價", "最後揭示買量",
                    "最後揭示賣價", "最後揭示賣量", "本益比",
                ],
                "data": [
                    [sid, "name", vol, "1", val, "10", "10", "10", "10",
                     "<p>+</p>", "0", "10", "1", "10", "1", "0"]
                    for sid, vol, val in rows
                ],
            },
        ],
    }


def _patch_twse(monkeypatch, payloads_by_date: dict[str, dict]):
    """Stub ``requests.get`` so each TWSE call returns the payload keyed by
    ``date=YYYYMMDD``. Missing keys → empty (non-trading-day) response.
    Also no-ops the inter-request sleep so range tests don't pay real time.
    """
    def fake_get(url, params=None, timeout=None, **_kw):
        d = (params or {}).get("date", "")
        return _FakeResponse(payloads_by_date.get(d, {"stat": "no data", "tables": []}))
    monkeypatch.setattr(gv.requests, "get", fake_get)
    monkeypatch.setattr(gv.time, "sleep", lambda _s: None)


def test_fetch_twse_daily_all_parses_rows(monkeypatch):
    payload = _twse_payload([
        ("2330", "34,360,513", "78,454,021,723"),
        ("3008", "1,234", "5,678,900"),
    ])
    _patch_twse(monkeypatch, {"20260515": payload})
    out = gv._fetch_twse_daily_all("2026-05-15")
    assert out == [
        {"stock_id": "2330", "trading_volume": 34360513, "trading_money": 78454021723},
        {"stock_id": "3008", "trading_volume":     1234, "trading_money":     5678900},
    ]


def test_fetch_twse_daily_all_returns_empty_on_holiday(monkeypatch):
    _patch_twse(monkeypatch, {})  # no payload for the date → non-trading-day shape
    assert gv._fetch_twse_daily_all("2026-05-16") == []


def test_fetch_twse_daily_all_returns_empty_when_table_missing(monkeypatch):
    _patch_twse(monkeypatch, {"20260515": {"stat": "OK", "tables": []}})
    assert gv._fetch_twse_daily_all("2026-05-15") == []


def test_fetch_twse_daily_all_skips_unparseable_rows(monkeypatch):
    # First row has a non-numeric trading_volume → must be skipped silently,
    # remaining rows still come through.
    payload = _twse_payload([
        ("9999", "n/a",   "0"),
        ("2330", "1,000", "10,000"),
    ])
    _patch_twse(monkeypatch, {"20260515": payload})
    out = gv._fetch_twse_daily_all("2026-05-15")
    assert out == [
        {"stock_id": "2330", "trading_volume": 1000, "trading_money": 10000},
    ]


def test_handles_zero_trading_money(monkeypatch):
    """Quiet stocks with 0 turnover still bump stock_count."""
    _patch_industry_map(monkeypatch, _info_rows(("2330", "twse", "半導體業")))
    _patch_twse(monkeypatch, {
        "20260515": _twse_payload([("2330", "0", "0")]),
    })
    out = gv.fetch_industry_volume("2026-05-15")
    assert len(out) == 1
    assert out[0]["total_value"]  == 0.0
    assert out[0]["total_volume"] == 0
    assert out[0]["stock_count"]  == 1
