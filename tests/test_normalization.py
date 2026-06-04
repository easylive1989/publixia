"""Stock-name normalization (ticker / canonical / alias resolution)."""
from repositories.stock_reference import upsert_reference_batch
from services.normalization import normalize


def _seed():
    upsert_reference_batch([
        {"ticker": "2330", "market": "TW", "canonical_name": "台積電", "aliases": ["護國神山", "TSMC"]},
        {"ticker": "TSM", "market": "US", "canonical_name": "Taiwan Semiconductor", "aliases": ["台積電ADR"]},
        {"ticker": "NVDA", "market": "US", "canonical_name": "NVIDIA", "aliases": ["輝達"]},
    ], source="test")


def test_canonical_name():
    _seed()
    assert normalize("台積電") == ("2330", "TW")


def test_ticker_exact_case_insensitive():
    _seed()
    assert normalize("2330") == ("2330", "TW")
    assert normalize("nvda") == ("NVDA", "US")


def test_alias_match():
    _seed()
    assert normalize("護國神山") == ("2330", "TW")
    assert normalize("輝達") == ("NVDA", "US")


def test_unknown_returns_none():
    _seed()
    assert normalize("完全不存在的東西") == (None, None)
    assert normalize("") == (None, None)
