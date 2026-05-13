"""Tests for services.futures_settlement.

The markdown parser is what guarantees the table the user maintains by
hand turns into clean rows, so it's the part we lock down. The range
reader is a thin filter on top of the parser plus disk read.
"""
from pathlib import Path

from services.futures_settlement import (
    get_settlement_dates_in_range,
    parse_markdown,
)


BASIC_TABLE = """\
# heading

| 月份 | 2024 | 2025 |
|------|------|------|
| 1月  | 1/17 | 1/15 |
| 2月  | 2/21 | 2/19 |
| 12月 | 12/18 | 12/17 |
"""


def test_parse_markdown_basic():
    rows = parse_markdown(BASIC_TABLE)
    assert {(r["year_month"], r["settlement_date"]) for r in rows} == {
        ("2024-01", "2024-01-17"),
        ("2024-02", "2024-02-21"),
        ("2024-12", "2024-12-18"),
        ("2025-01", "2025-01-15"),
        ("2025-02", "2025-02-19"),
        ("2025-12", "2025-12-17"),
    }


def test_parse_markdown_strips_annotations():
    table = (
        "| 月份 | 2026 |\n"
        "|------|------|\n"
        "| 2月  | 2/25 ※ |\n"
    )
    rows = parse_markdown(table)
    assert rows == [{"year_month": "2026-02", "settlement_date": "2026-02-25"}]


def test_parse_markdown_skips_empty_and_invalid_cells():
    # 2025/3 is empty; 2024/3 says TBD — both skipped, no exception.
    table = (
        "| 月份 | 2024 | 2025 |\n"
        "|------|------|------|\n"
        "| 3月  | TBD  |      |\n"
        "| 4月  | 4/17 | 4/16 |\n"
    )
    rows = parse_markdown(table)
    assert rows == [
        {"year_month": "2024-04", "settlement_date": "2024-04-17"},
        {"year_month": "2025-04", "settlement_date": "2025-04-16"},
    ]


def test_parse_markdown_skips_cell_when_month_disagrees_with_row():
    # Cell month 3 in a 4月 row → typo, must be dropped not silently accepted.
    table = (
        "| 月份 | 2025 |\n"
        "|------|------|\n"
        "| 4月  | 3/19 |\n"
    )
    assert parse_markdown(table) == []


def test_parse_markdown_ignores_year_columns_with_non_numeric_header():
    # Header column "TBD" is treated as a placeholder — no rows emitted for it.
    table = (
        "| 月份 | 2025 | TBD |\n"
        "|------|------|-----|\n"
        "| 5月  | 5/21 | 5/20 |\n"
    )
    rows = parse_markdown(table)
    assert rows == [{"year_month": "2025-05", "settlement_date": "2025-05-21"}]


def test_parse_markdown_no_table_returns_empty():
    assert parse_markdown("just some prose, no table here.\n") == []


def test_get_settlement_dates_in_range_filters_and_sorts(tmp_path: Path):
    md = tmp_path / "settlement_dates.md"
    md.write_text(
        "| 月份 | 2025 |\n"
        "|------|------|\n"
        "| 4月  | 4/16 |\n"
        "| 5月  | 5/21 |\n"
        "| 6月  | 6/18 |\n",
        encoding="utf-8",
    )
    in_range = get_settlement_dates_in_range("2025-05-01", "2025-06-30", path=md)
    assert in_range == ["2025-05-21", "2025-06-18"]


def test_get_settlement_dates_in_range_inclusive_bounds(tmp_path: Path):
    md = tmp_path / "settlement_dates.md"
    md.write_text(
        "| 月份 | 2025 |\n"
        "|------|------|\n"
        "| 5月  | 5/21 |\n",
        encoding="utf-8",
    )
    assert get_settlement_dates_in_range(
        "2025-05-21", "2025-05-21", path=md,
    ) == ["2025-05-21"]


def test_get_settlement_dates_in_range_reads_real_markdown():
    # Smoke test against the checked-in markdown so a future edit that
    # breaks the parse format trips this test, not production.
    result = get_settlement_dates_in_range("2025-01-01", "2025-12-31")
    # 12 monthly settlements per year, all third-Wednesday-ish.
    assert len(result) == 12
    assert result == sorted(result)
    assert "2025-05-21" in result
