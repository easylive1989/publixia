"""TX futures final-settlement-date reader.

Reads from the user-maintained markdown at
`backend/data/settlement_dates.md` on demand. The markdown is the single
source of truth — no DB caching, no scheduled refresh job. Edits land on
the next deploy and become visible to `/api/futures/tw/foreign-flow`
immediately when the user updates the file.
"""
import logging
import re
from datetime import date
from pathlib import Path

logger = logging.getLogger(__name__)

SETTLEMENT_DATES_PATH = (
    Path(__file__).resolve().parent.parent / "data" / "settlement_dates.md"
)

_TABLE_ROW_RE = re.compile(r"^\s*\|(.*)\|\s*$")
_SEPARATOR_RE = re.compile(r"^\s*\|[\s\-:|]+\|\s*$")
_YEAR_RE = re.compile(r"^\d{4}$")
_MONTH_LABEL_RE = re.compile(r"^(\d{1,2})月$")
_CELL_RE = re.compile(r"^(\d{1,2})/(\d{1,2})$")


def _split_row(line: str) -> list[str]:
    body = _TABLE_ROW_RE.match(line).group(1)
    return [c.strip() for c in body.split("|")]


def parse_markdown(text: str) -> list[dict]:
    """Parse settlement_dates.md into [{year_month, settlement_date}, ...].

    Header row provides year columns (4-digit ints). Each data row's first
    cell is `N月`; remaining cells are `M/D` with optional trailing
    annotation tokens (e.g. `2/25 ※`). Empty / unparseable cells are
    skipped — `※` annotations and leap-year edge cases never need code
    changes, only an edit to the markdown.
    """
    years: list[int] | None = None
    out: list[dict] = []
    for line in text.splitlines():
        if not _TABLE_ROW_RE.match(line) or _SEPARATOR_RE.match(line):
            continue
        cells = _split_row(line)
        if not cells:
            continue
        if years is None:
            years = [int(c) if _YEAR_RE.match(c) else 0 for c in cells[1:]]
            continue
        m = _MONTH_LABEL_RE.match(cells[0])
        if not m:
            continue
        month = int(m.group(1))
        for idx, cell in enumerate(cells[1:]):
            if idx >= len(years) or years[idx] == 0:
                continue
            if not cell:
                continue
            year = years[idx]
            token = cell.split()[0]
            cm = _CELL_RE.match(token)
            if not cm:
                logger.warning(
                    "settlement_dates.md: skipping cell %r at %d/%d",
                    cell, year, month,
                )
                continue
            cell_month, day = int(cm.group(1)), int(cm.group(2))
            if cell_month != month:
                logger.warning(
                    "settlement_dates.md: month mismatch %r at row %d月, year %d",
                    cell, month, year,
                )
                continue
            try:
                d = date(year, month, day)
            except ValueError as e:
                logger.warning(
                    "settlement_dates.md: invalid date %d-%02d-%02d: %s",
                    year, month, day, e,
                )
                continue
            out.append({
                "year_month":      f"{year:04d}-{month:02d}",
                "settlement_date": d.strftime("%Y-%m-%d"),
            })
    return out


def get_settlement_dates_in_range(
    start_date: str, end_date: str,
    path: Path = SETTLEMENT_DATES_PATH,
) -> list[str]:
    """Settlement dates inside [start_date, end_date] (inclusive), ascending.

    Both bounds are `YYYY-MM-DD`. Lexical comparison is safe given the
    fixed-width ISO date format.
    """
    text = path.read_text(encoding="utf-8")
    items = parse_markdown(text)
    return sorted(
        it["settlement_date"] for it in items
        if start_date <= it["settlement_date"] <= end_date
    )
