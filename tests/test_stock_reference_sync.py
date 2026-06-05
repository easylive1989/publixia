"""US roster sync from SEC + Chinese-alias overlay."""
from db.connection import get_connection
from services import stock_reference_sync as svc
from services.normalization import normalize

_SEC_PAYLOAD = [
    {"cik_str": 50863, "ticker": "INTC", "title": "Intel Corp."},
    {"cik_str": 1045810, "ticker": "NVDA", "title": "NVIDIA Corp"},
    {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."},
]


def test_sync_us_from_sec_normalizes_roster_tickers(monkeypatch):
    monkeypatch.setattr(svc, "fetch_company_tickers", lambda: _SEC_PAYLOAD)
    count = svc.sync_us_from_sec()
    assert count == 3
    # 不在舊手寫清單裡的 INTC 現在對得到；大小寫不敏感
    assert normalize("intc") == ("INTC", "US")


def test_sync_us_from_sec_keeps_chinese_alias_overlay(monkeypatch):
    monkeypatch.setattr(svc, "fetch_company_tickers", lambda: _SEC_PAYLOAD)
    svc.sync_us_from_sec()
    assert normalize("輝達") == ("NVDA", "US")


def test_sync_us_from_sec_uses_sec_company_name(monkeypatch):
    monkeypatch.setattr(svc, "fetch_company_tickers", lambda: _SEC_PAYLOAD)
    svc.sync_us_from_sec()
    with get_connection() as conn:
        row = conn.execute(
            "SELECT canonical_name FROM stock_reference "
            "WHERE ticker='INTC' AND market='US'"
        ).fetchone()
    assert row["canonical_name"] == "Intel Corp."


def test_run_stock_reference_sync_includes_us(monkeypatch):
    # TW 與 SEC 都 stub 掉，只驗證 us 欄走 sync_us_from_sec
    monkeypatch.setattr(svc, "sync_tw_from_finmind", lambda: 0)
    monkeypatch.setattr(svc, "fetch_company_tickers", lambda: _SEC_PAYLOAD)
    result = svc.run_stock_reference_sync()
    assert result["us"] == 3
    assert "tw" in result and "index" in result
