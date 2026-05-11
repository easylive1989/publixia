"""CSV-parser tests for fetchers.txo_strike_oi.

No network — we feed parse_csv synthetic CSV bodies that mirror the
TAIFEX `選擇權每日交易行情` layout.
"""
from fetchers.txo_strike_oi import parse_csv


_HEADER = (
    "交易日期,契約,到期月份(週別),履約價,買賣權,"
    "開盤價,最高價,最低價,最後成交價,結算價,成交量,未沖銷契約量,"
    "最後最佳買價,最後最佳賣價,歷史最高價,歷史最低價,"
    "是否因訊息面暫停交易,交易時段"
)


def _csv(*body_lines: str) -> str:
    return "\n".join((_HEADER, *body_lines))


def test_extracts_strike_rows_for_txo():
    body = _csv(
        "2026/05/09,TXO,202506,17000,買權,80,90,75,85,86,1000,3500,80,82,200,50,,一般",
        "2026/05/09,TXO,202506,17000,賣權,70,75,65,72,73,1200,4200,71,72,180,40,,一般",
        "2026/05/09,TXO,202506,17500,買權,40,45,35,42,43,900,1800,41,42,150,30,,一般",
    )
    rows = parse_csv(body)
    assert len(rows) == 3
    by_key = {(r["expiry_month"], r["strike"], r["put_call"]): r for r in rows}
    assert by_key[("202506", 17000.0, "CALL")]["open_interest"] == 3500
    assert by_key[("202506", 17000.0, "PUT")]["open_interest"]  == 4200
    assert by_key[("202506", 17500.0, "CALL")]["open_interest"] == 1800
    assert all(r["symbol"] == "TXO" for r in rows)
    assert all(r["date"]   == "2026-05-09" for r in rows)
    # settle_price is parsed when present.
    assert by_key[("202506", 17000.0, "CALL")]["settle_price"] == 86.0


def test_filters_to_regular_session_only():
    """盤後 rows duplicate OI; we keep only 一般."""
    body = _csv(
        "2026/05/09,TXO,202506,17000,買權,80,90,75,85,86,1000,3500,80,82,200,50,,一般",
        # Same key, after-hours — must be dropped, not re-applied.
        "2026/05/09,TXO,202506,17000,買權,82,88,80,83,84,500,3500,82,83,200,50,,盤後",
    )
    rows = parse_csv(body)
    assert len(rows) == 1
    assert rows[0]["open_interest"] == 3500


def test_keeps_weekly_contracts_distinct_from_monthly():
    body = _csv(
        "2026/05/09,TXO,202506,17000,買權,80,90,75,85,86,1000,3500,80,82,200,50,,一般",
        "2026/05/09,TXO,202506W2,17000,買權,80,90,75,85,86,300,800,80,82,200,50,,一般",
    )
    rows = parse_csv(body)
    assert len(rows) == 2
    by_expiry = {(r["expiry_month"], r["put_call"]): r for r in rows}
    assert by_expiry[("202506",   "CALL")]["open_interest"] == 3500
    assert by_expiry[("202506W2", "CALL")]["open_interest"] == 800


def test_skips_non_txo_products():
    body = _csv(
        "2026/05/09,TXO,202506,17000,買權,80,90,75,85,86,1000,3500,80,82,200,50,,一般",
        # 電子選擇權 / TEO — must be filtered.
        "2026/05/09,TEO,202506,500,買權,5,6,4,5,5,10,20,5,6,10,3,,一般",
    )
    rows = parse_csv(body)
    assert len(rows) == 1
    assert rows[0]["symbol"] == "TXO"


def test_handles_thousand_separators_in_oi():
    body = _csv(
        "2026/05/09,TXO,202506,17000,買權,80,90,75,85,86,\"1,000\",\"42,500\",80,82,200,50,,一般",
    )
    rows = parse_csv(body)
    assert len(rows) == 1
    assert rows[0]["open_interest"] == 42_500


def test_skips_when_header_missing():
    assert parse_csv("nope,no,header\nstill,no,header") == []


def test_unknown_put_call_label_skipped():
    body = _csv(
        "2026/05/09,TXO,202506,17000,週買權,80,90,75,85,86,1000,3500,80,82,200,50,,一般",
    )
    assert parse_csv(body) == []


def test_blank_strike_row_skipped():
    body = _csv(
        "2026/05/09,TXO,202506,,買權,80,90,75,85,86,1000,3500,80,82,200,50,,一般",
        "2026/05/09,TXO,202506,17500,賣權,40,45,35,42,43,900,1800,41,42,150,30,,一般",
    )
    rows = parse_csv(body)
    assert len(rows) == 1
    assert rows[0]["strike"] == 17500.0
    assert rows[0]["put_call"] == "PUT"
