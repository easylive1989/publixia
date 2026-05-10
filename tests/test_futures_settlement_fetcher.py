"""Algorithmic generator tests for fetchers.futures_settlement.

The scraping path is best-effort and exercised only at runtime; the
algorithm is what guarantees the page renders something even when
TAIFEX is unreachable, so it's the part we lock down.
"""
from datetime import date

from fetchers.futures_settlement import third_wednesday, generate_algorithmic


def test_third_wednesday_known_months():
    # TX 2025/05 settlement: third Wednesday is 2025-05-21
    assert third_wednesday(2025, 5)  == date(2025, 5, 21)
    # 2025/01 settlement: third Wednesday is 2025-01-15
    assert third_wednesday(2025, 1)  == date(2025, 1, 15)
    # December 2024
    assert third_wednesday(2024, 12) == date(2024, 12, 18)


def test_generate_algorithmic_is_inclusive_of_endpoints():
    out = generate_algorithmic(date(2025, 5, 21), date(2025, 6, 18))
    months = [it["year_month"] for it in out]
    dates  = [it["settlement_date"] for it in out]
    assert months == ["2025-05", "2025-06"]
    assert dates  == ["2025-05-21", "2025-06-18"]


def test_generate_algorithmic_empty_when_window_skips_months():
    # Window between two settlements → no rows.
    out = generate_algorithmic(date(2025, 5, 22), date(2025, 6, 17))
    assert out == []


def test_generate_algorithmic_year_rollover():
    out = generate_algorithmic(date(2024, 12, 1), date(2025, 1, 31))
    months = [it["year_month"] for it in out]
    assert months == ["2024-12", "2025-01"]
