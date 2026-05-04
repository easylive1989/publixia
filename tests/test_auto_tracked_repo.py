from repositories.auto_tracked import (
    insert_if_missing, is_auto_tracked, list_auto_tracked_tickers,
)


def test_insert_then_query():
    assert insert_if_missing('TSTAAA.TW') is True
    assert insert_if_missing('TSTAAA.TW') is False  # idempotent
    assert is_auto_tracked('TSTAAA.TW') is True
    assert is_auto_tracked('NOPE.TW') is False


def test_list_returns_sorted():
    insert_if_missing('TSTBBB.TW')
    insert_if_missing('TSTAAA.TW')
    tickers = list_auto_tracked_tickers()
    # Test rows + whatever the seed loader put in there
    assert 'TSTAAA.TW' in tickers
    assert 'TSTBBB.TW' in tickers
    assert tickers == sorted(tickers)
