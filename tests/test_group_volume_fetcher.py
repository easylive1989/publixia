"""Tests for fetchers.group_volume.

FinMind is fully mocked — these tests only exercise the filtering and
aggregation logic, never the network.
"""
import fetchers.group_volume as gv


def _info_rows(*entries: tuple[str, str, str]) -> list[dict]:
    """Helper to build a TaiwanStockInfo response. Each entry is
    ``(stock_id, type, industry_category)``."""
    return [
        {"stock_id": sid, "type": kind, "industry_category": ind}
        for sid, kind, ind in entries
    ]


def _price_row(stock_id: str, date: str, value: float, volume: int) -> dict:
    return {
        "stock_id": stock_id,
        "date": date,
        "Trading_money": value,
        "Trading_Volume": volume,
    }


def _patch_finmind(monkeypatch, *, info_rows: list[dict], price_rows: list[dict]):
    """Stub the FinMind helper used by the fetcher.

    The ``TaiwanStockPrice`` stub honours ``start_date`` / ``end_date`` so
    callers that iterate day-by-day see only the matching rows — this
    mirrors what FinMind actually returns when each call covers one day.
    """
    calls: list[tuple] = []

    def fake_request(dataset: str, start_date: str, end_date: str | None = None):
        calls.append((dataset, start_date, end_date))
        if dataset == "TaiwanStockInfo":
            return info_rows
        if dataset == "TaiwanStockPrice":
            hi = end_date or start_date
            return [r for r in price_rows if start_date <= r.get("date", "") <= hi]
        raise AssertionError(f"unexpected dataset {dataset}")

    monkeypatch.setattr(gv, "request", fake_request)
    return calls


def test_industry_map_excludes_otc_etf_etn_and_blanks(monkeypatch):
    _patch_finmind(
        monkeypatch,
        info_rows=_info_rows(
            ("2330", "twse",  "半導體業"),
            ("0050", "twse",  "ETF"),           # exclude
            ("0056", "twse",  "受益證券"),       # exclude
            ("00679B", "twse", "ETN"),          # exclude
            ("3008", "twse",  "光電業"),
            ("9999", "twse",  ""),              # blank → exclude
            ("8888", "twse",  None),            # None → exclude
            ("5483", "tpex",  "半導體業"),       # OTC → exclude
        ),
        price_rows=[],
    )
    mapping = gv._load_industry_map()
    assert mapping == {"2330": "半導體業", "3008": "光電業"}


def test_fetch_industry_volume_aggregates_known_stocks_only(monkeypatch):
    _patch_finmind(
        monkeypatch,
        info_rows=_info_rows(
            ("2330", "twse", "半導體業"),
            ("2454", "twse", "半導體業"),
            ("3008", "twse", "光電業"),
            ("0050", "twse", "ETF"),     # in price feed but should be skipped
        ),
        price_rows=[
            _price_row("2330", "2026-05-15", 100_000_000.0, 50_000),
            _price_row("2454", "2026-05-15",  80_000_000.0, 30_000),
            _price_row("3008", "2026-05-15",  20_000_000.0, 10_000),
            _price_row("0050", "2026-05-15", 999_999_999.9, 99_999),  # skipped
            _price_row("UNKNOWN", "2026-05-15", 1.0, 1),              # skipped
        ],
    )

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
    _patch_finmind(
        monkeypatch,
        info_rows=_info_rows(
            ("2330", "twse", "半導體業"),
            ("3008", "twse", "光電業"),
        ),
        price_rows=[
            _price_row("2330", "2026-05-14", 100.0, 1),
            _price_row("3008", "2026-05-14", 200.0, 2),
            _price_row("2330", "2026-05-15", 110.0, 3),
        ],
    )
    by_date = gv.fetch_industry_volume_range("2026-05-14", "2026-05-15")

    assert sorted(by_date) == ["2026-05-14", "2026-05-15"]
    d1 = {a["group_code"]: a for a in by_date["2026-05-14"]}
    d2 = {a["group_code"]: a for a in by_date["2026-05-15"]}
    assert d1["半導體業"]["total_value"] == 100.0
    assert d1["光電業"]["total_value"]   == 200.0
    assert d2 == {"半導體業": {
        "group_code": "半導體業", "group_name": "半導體業",
        "total_value": 110.0, "total_volume": 3, "stock_count": 1,
    }}


def test_fetch_industry_volume_returns_empty_for_holiday(monkeypatch):
    """On weekends/holidays FinMind returns no rows; fetcher must not crash."""
    _patch_finmind(
        monkeypatch,
        info_rows=_info_rows(("2330", "twse", "半導體業")),
        price_rows=[],
    )
    assert gv.fetch_industry_volume("2026-05-16") == []  # 週六


def test_handles_zero_or_missing_trading_money(monkeypatch):
    """Quiet stocks with 0 turnover should still be counted in stock_count."""
    _patch_finmind(
        monkeypatch,
        info_rows=_info_rows(("2330", "twse", "半導體業")),
        price_rows=[
            {"stock_id": "2330", "date": "2026-05-15",
             "Trading_money": None, "Trading_Volume": None},
        ],
    )
    out = gv.fetch_industry_volume("2026-05-15")
    assert len(out) == 1
    assert out[0]["total_value"]  == 0.0
    assert out[0]["total_volume"] == 0
    assert out[0]["stock_count"]  == 1
