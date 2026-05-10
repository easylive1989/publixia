"""CSV-parser tests for fetchers.large_trader (TAIFEX 大額交易人).

Network-free: feed parse_csv a synthetic Big5-style CSV body matching
the TAIFEX `largeTraderFutDown` schema and assert it filters down to
the single row we care about (商品=TX, 到期月份=999999, 交易人類別=0).
"""
from fetchers.large_trader import parse_csv


_HEADER = (
    "日期,商品(契約),商品名稱(契約名稱),到期月份(週別),"
    "交易人類別,前五大交易人買方,前五大交易人賣方,"
    "前十大交易人買方,前十大交易人賣方,全市場未沖銷部位數"
)


def _csv(*body_lines: str) -> str:
    return "\n".join((_HEADER, *body_lines))


def test_keeps_only_tx_999999_type0_row():
    body = _csv(
        # Other product — skipped
        "2026/05/08,BRF    ,布蘭特原油期貨,202607  ,0,47,30,60,45,65",
        # TX near-month only — skipped (month != 999999)
        "2026/05/08,TX     ,臺股期貨(TX+MTX/4+TMF/20),202605  ,0,55752,49362,64485,65037,96191",
        # TX 999999 type=1 (特定法人 only) — skipped
        "2026/05/08,TX     ,臺股期貨(TX+MTX/4+TMF/20),999999  ,1,55823,51665,66097,67682,106157",
        # TX 999999 type=0 (全部) — kept
        "2026/05/08,TX     ,臺股期貨(TX+MTX/4+TMF/20),999999  ,0,55823,51665,66097,67682,106157",
    )
    rows = parse_csv(body)
    assert len(rows) == 1
    r = rows[0]
    assert r["date"] == "2026-05-08"
    assert r["market_oi"]      == 106_157
    assert r["top5_long_oi"]   == 55_823
    assert r["top5_short_oi"]  == 51_665
    assert r["top10_long_oi"]  == 66_097
    assert r["top10_short_oi"] == 67_682


def test_keeps_one_row_per_day_across_multi_day_response():
    body = _csv(
        "2026/05/04,TX     ,臺股期貨(TX+MTX/4+TMF/20),999999  ,0,53094,45946,63093,58707,99915",
        "2026/05/04,TX     ,臺股期貨(TX+MTX/4+TMF/20),999999  ,1,53094,45946,63093,58707,99915",
        "2026/05/05,TX     ,臺股期貨(TX+MTX/4+TMF/20),999999  ,0,52690,47527,62354,61794,99459",
        "2026/05/05,TX     ,臺股期貨(TX+MTX/4+TMF/20),202605  ,0,52668,45134,61400,59107,91150",
    )
    rows = parse_csv(body)
    assert len(rows) == 2
    assert {r["date"] for r in rows} == {"2026-05-04", "2026-05-05"}


def test_handles_thousand_separators():
    body = _csv(
        "2026/05/08,TX     ,臺股期貨(TX+MTX/4+TMF/20),999999  ,0,\"55,823\",\"51,665\",\"66,097\",\"67,682\",\"106,157\"",
    )
    rows = parse_csv(body)
    assert len(rows) == 1
    assert rows[0]["market_oi"] == 106_157
    assert rows[0]["top10_long_oi"] == 66_097


def test_skips_when_header_is_missing():
    rows = parse_csv("not a real csv\nfoo,bar,baz")
    assert rows == []
