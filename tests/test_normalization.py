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


def test_market_aliases_map_to_taiex_index():
    # the index row is seeded by migration 0026 (no _seed needed)
    assert normalize("台股") == ("TAIEX", "INDEX")
    assert normalize("大盤") == ("TAIEX", "INDEX")
    assert normalize("加權指數") == ("TAIEX", "INDEX")


def test_alias_match_case_insensitive():
    _seed()
    # English nicknames resolve regardless of casing
    upsert_reference_batch([
        {"ticker": "NVDA", "market": "US", "canonical_name": "NVIDIA CORP", "aliases": ["輝達", "NVIDIA"]},
    ], source="test")
    assert normalize("NVIDIA") == ("NVDA", "US")
    assert normalize("nvidia") == ("NVDA", "US")
    assert normalize("Nvidia") == ("NVDA", "US")


def test_canonical_match_case_insensitive():
    upsert_reference_batch([
        {"ticker": "AAPL", "market": "US", "canonical_name": "Apple Inc.", "aliases": []},
    ], source="test")
    assert normalize("apple inc.") == ("AAPL", "US")
