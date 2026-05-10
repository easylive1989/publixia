"""CSV-parser tests for fetchers.institutional_futures.

We don't hit the network in these tests; the fetcher is exercised by
feeding it a synthetic Big5 CSV body that mirrors the TAIFEX format.
"""
from fetchers.institutional_futures import parse_csv


_HEADER = (
    "日期,商品名稱,身份別,"
    "多方交易口數,多方契約金額,"
    "空方交易口數,空方契約金額,"
    "多空淨額交易口數,多空淨額契約金額,"
    "多方未平倉口數,多方未平倉契約金額,"
    "空方未平倉口數,空方未平倉契約金額,"
    "多空淨額未平倉口數,多空淨額未平倉契約金額"
)


def _csv(*body_lines: str) -> str:
    return "\n".join((_HEADER, *body_lines))


def test_keeps_only_foreign_tx_and_mtx_rows():
    body = _csv(
        # TX 自營商 — should be skipped
        "2025/05/10,臺股期貨,自營商,1,2,3,4,5,6,7,8,9,10,11,12",
        # TX 投信 — skipped
        "2025/05/10,臺股期貨,投信,1,2,3,4,5,6,7,8,9,10,11,12",
        # TX 外資 — kept
        "2025/05/10,臺股期貨,外資,100,200,50,100,50,100,1000,3200000,3000,9600000,-2000,-6400000",
        # MTX 外資 — kept
        "2025/05/10,小型臺指期貨,外資,40,80,20,40,20,40,400,1280000,1200,3840000,-800,-2560000",
        # 電子期貨 外資 — skipped (not TX/MTX)
        "2025/05/10,電子期貨,外資,1,2,3,4,5,6,7,8,9,10,11,12",
    )
    rows = parse_csv(body)
    assert len(rows) == 2
    by_symbol = {r["symbol"]: r for r in rows}
    assert by_symbol["TX"]["date"] == "2025-05-10"
    assert by_symbol["TX"]["foreign_long_oi"]      == 1000
    assert by_symbol["TX"]["foreign_short_oi"]     == 3000
    assert by_symbol["TX"]["foreign_long_amount"]  == 3_200_000.0
    assert by_symbol["TX"]["foreign_short_amount"] == 9_600_000.0
    assert by_symbol["MTX"]["foreign_long_oi"]     == 400
    assert by_symbol["MTX"]["foreign_short_oi"]    == 1200


def test_handles_thousand_separators_and_dashes():
    body = _csv(
        "2025/05/10,臺股期貨,外資,\"1,000\",\"2,000\",-,-,-,-,\"15,000\",\"48,000,000\",\"3,000\",\"9,600,000\",12000,38400000",
    )
    rows = parse_csv(body)
    assert len(rows) == 1
    assert rows[0]["foreign_long_oi"]     == 15_000
    assert rows[0]["foreign_short_oi"]    == 3_000
    assert rows[0]["foreign_long_amount"] == 48_000_000.0


def test_skips_when_header_is_missing():
    body = "this,is,not,a,table\nrow,without,header,ok,nope"
    assert parse_csv(body) == []


def test_alt_label_for_foreign_post_2020():
    """TAIFEX renamed 外資 → 外資及陸資 in some downloads — both must work."""
    body = _csv(
        "2025/05/10,臺股期貨,外資及陸資,1,2,3,4,5,6,500,1600000,1500,4800000,-1000,-3200000",
    )
    rows = parse_csv(body)
    assert len(rows) == 1
    assert rows[0]["foreign_long_oi"] == 500
