"""CSV-parser tests for fetchers.institutional_options.

We don't hit the network in these tests; the fetcher is exercised by
feeding it a synthetic CSV body that mirrors the TAIFEX layout for
`三大法人 - 選擇權買賣權分計`.
"""
from fetchers.institutional_options import parse_csv


_HEADER = (
    "日期,商品名稱,買賣權別,身份別,"
    "買方交易口數,買方交易契約金額(千元),"
    "賣方交易口數,賣方交易契約金額(千元),"
    "交易口數買賣淨額,交易契約金額買賣淨額(千元),"
    "買方未平倉口數,買方未平倉契約金額(千元),"
    "賣方未平倉口數,賣方未平倉契約金額(千元),"
    "未平倉口數買賣淨額,未平倉契約金額買賣淨額(千元)"
)


def _csv(*body_lines: str) -> str:
    return "\n".join((_HEADER, *body_lines))


def test_keeps_only_txo_three_identities():
    body = _csv(
        # TXO 外資 CALL
        "2026/05/09,臺指選擇權,買權,外資,1,2,3,4,5,6,1000,3200000,500,1600000,500,1600000",
        # TXO 外資 PUT
        "2026/05/09,臺指選擇權,賣權,外資,1,2,3,4,5,6,800,2560000,400,1280000,400,1280000",
        # TXO 投信 CALL
        "2026/05/09,臺指選擇權,買權,投信,0,0,0,0,0,0,100,320000,50,160000,50,160000",
        # 不相關商品（電子選擇權） — skipped
        "2026/05/09,電子選擇權,買權,外資,1,2,3,4,5,6,7,8,9,10,11,12",
    )
    rows = parse_csv(body)
    assert len(rows) == 3
    by_key = {(r["identity"], r["put_call"]): r for r in rows}
    assert by_key[("foreign", "CALL")]["long_oi"]      == 1000
    assert by_key[("foreign", "CALL")]["long_amount"]  == 3_200_000.0
    assert by_key[("foreign", "PUT")]["short_oi"]      == 400
    assert by_key[("investment_trust", "CALL")]["long_oi"] == 100
    assert all(r["symbol"] == "TXO" for r in rows)
    assert all(r["date"]   == "2026-05-09" for r in rows)


def test_dealer_subcategories_aggregate_to_single_dealer_row():
    """TAIFEX splits 自營商 into (避險) and (自行買賣); we sum them."""
    body = _csv(
        "2026/05/09,臺指選擇權,買權,自營商(避險),0,0,0,0,0,0,300,900000,200,600000,100,300000",
        "2026/05/09,臺指選擇權,買權,自營商(自行買賣),0,0,0,0,0,0,40,120000,10,30000,30,90000",
    )
    rows = parse_csv(body)
    assert len(rows) == 1
    r = rows[0]
    assert r["identity"]    == "dealer"
    assert r["put_call"]    == "CALL"
    assert r["long_oi"]     == 340                # 300 + 40
    assert r["short_oi"]    == 210                # 200 + 10
    assert r["long_amount"] == 1_020_000.0        # 900,000 + 120,000


def test_handles_thousand_separators_and_dashes():
    body = _csv(
        "2026/05/09,臺指選擇權,買權,外資,-,-,-,-,-,-,\"15,000\",\"48,000,000\",\"3,000\",\"9,600,000\",12000,38400000",
    )
    rows = parse_csv(body)
    assert len(rows) == 1
    assert rows[0]["long_oi"]     == 15_000
    assert rows[0]["short_oi"]    == 3_000
    assert rows[0]["long_amount"] == 48_000_000.0


def test_skips_when_header_is_missing():
    body = "this,is,not,a,table\nrow,without,header,ok,nope"
    assert parse_csv(body) == []


def test_alt_label_for_foreign_post_2020():
    """TAIFEX renamed 外資 → 外資及陸資 in some downloads — both must work."""
    body = _csv(
        "2026/05/09,臺指選擇權,賣權,外資及陸資,0,0,0,0,0,0,500,1600000,1500,4800000,-1000,-3200000",
    )
    rows = parse_csv(body)
    assert len(rows) == 1
    assert rows[0]["identity"] == "foreign"
    assert rows[0]["put_call"] == "PUT"
    assert rows[0]["short_oi"] == 1500


def test_alt_product_label():
    """Some archives spell 商品名稱 with the simplified 台 character."""
    body = _csv(
        "2026/05/09,台指選擇權,買權,外資,0,0,0,0,0,0,7,8,9,10,11,12",
    )
    rows = parse_csv(body)
    assert len(rows) == 1
    assert rows[0]["symbol"] == "TXO"


def test_unknown_put_call_label_skipped():
    body = _csv(
        "2026/05/09,臺指選擇權,週選買權,外資,0,0,0,0,0,0,1,2,3,4,5,6",
    )
    assert parse_csv(body) == []
