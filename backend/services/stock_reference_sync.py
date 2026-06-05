"""Populate the stock_reference normalization table.

TW: the full listed-stock roster from FinMind's ``TaiwanStockInfo``, plus a
small hand-maintained alias overlay for popular nicknames the posts use
(護國神山, 小台電, ...). US: the full filer roster from SEC's
``company_tickers.json``, plus a Chinese-alias overlay for the nicknames.

Run by the ``stock_ref_sync`` scheduler job. Safe to re-run (upsert). After
refreshing the rosters it re-normalizes trades the bigger roster can now
resolve (see ``backfill_unnormalized_trades``).
"""
import logging
from datetime import date

from core.finmind import request as finmind_request
from core.sec import fetch_company_tickers
from repositories.stock_reference import upsert_reference_batch
from services.backfill_normalization import backfill_unnormalized_trades
from services.price_tracking_runner import run_price_tracking

logger = logging.getLogger(__name__)

# Common TW nicknames not present in the official names. ticker → aliases.
_TW_ALIAS_OVERLAY: dict[str, list[str]] = {
    "2330": ["護國神山", "台積", "TSMC"],
    "2317": ["鴻海", "Foxconn"],
    "2454": ["聯發科", "MTK"],
    "2603": ["長榮海運"],
    "3231": ["緯創資通"],
    "2890": ["永豐金控"],
}

# Common US nicknames the posts use (Chinese). ticker → aliases.
# Canonical English names come from the SEC roster, not here.
_US_ALIAS_OVERLAY: dict[str, list[str]] = {
    "NVDA": ["輝達", "黃仁勳"],
    "TSLA": ["特斯拉", "電動車"],
    "AAPL": ["蘋果"],
    "MSFT": ["微軟"],
    "GOOGL": ["谷歌", "Google"],
    "AMZN": ["亞馬遜"],
    "META": ["臉書", "Facebook"],
    "TSM": ["台積電ADR", "台積電 ADR"],
    "AMD": ["超微"],
}


def sync_tw_from_finmind() -> int:
    """Upsert the full TW listed-stock roster (ticker → official name)."""
    rows_raw = finmind_request("TaiwanStockInfo", date.today().isoformat())
    # FinMind returns one row per (stock_id, type); dedupe on stock_id.
    seen: dict[str, dict] = {}
    for r in rows_raw:
        sid = r.get("stock_id")
        name = r.get("stock_name")
        if not sid or not name:
            continue
        seen.setdefault(
            sid,
            {
                "ticker": sid,
                "market": "TW",
                "canonical_name": name,
                "aliases": _TW_ALIAS_OVERLAY.get(sid),
            },
        )
    count = upsert_reference_batch(list(seen.values()), source="finmind")
    logger.info("stock_ref_tw_synced count=%d", count)
    return count


def sync_us_from_sec() -> int:
    """Upsert the full US roster from SEC (ticker → company name)."""
    rows_raw = fetch_company_tickers()
    # dedupe on ticker (SEC should be unique; setdefault guards anyway).
    seen: dict[str, dict] = {}
    for r in rows_raw:
        ticker = r.get("ticker")
        title = r.get("title")
        if not ticker or not title:
            continue
        seen.setdefault(
            ticker,
            {
                "ticker": ticker,
                "market": "US",
                "canonical_name": title,
                "aliases": _US_ALIAS_OVERLAY.get(ticker),
            },
        )
    count = upsert_reference_batch(list(seen.values()), source="sec")
    logger.info("stock_ref_us_synced count=%d", count)
    return count


def seed_indices() -> int:
    """Market indices tracked by points (大盤). 台股/大盤/加權 → TAIEX (^TWII)."""
    rows = [{
        "ticker": "TAIEX", "market": "INDEX", "canonical_name": "加權指數",
        "aliases": ["台股", "大盤", "加權", "加權指數", "台股大盤",
                    "大盤指數", "台股指數", "指數", "集中市場"],
    }]
    count = upsert_reference_batch(rows, source="static")
    logger.info("stock_ref_indices_seeded count=%d", count)
    return count


def run_stock_reference_sync() -> dict:
    """Scheduler entry point: refresh TW + US rosters + indices, then
    re-normalize trades the bigger roster can now resolve."""
    tw = sync_tw_from_finmind()
    us = sync_us_from_sec()
    idx = seed_indices()
    backfill = backfill_unnormalized_trades()
    if backfill["filled"]:
        run_price_tracking()  # newly-resolved trades get their price windows
    return {"tw": tw, "us": us, "index": idx, "backfill": backfill}
