"""Populate the stock_reference normalization table.

TW: the full listed-stock roster from FinMind's ``TaiwanStockInfo``, plus a
small hand-maintained alias overlay for popular nicknames the posts use
(護國神山, 小台電, ...). US: a curated static map of names these accounts
mention, keyed with Chinese aliases.

Run by the ``stock_ref_sync`` scheduler job. Safe to re-run (upsert).
"""
import logging
from datetime import date

from core.finmind import request as finmind_request
from repositories.stock_reference import upsert_reference_batch

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

# US stocks the accounts mention, with Chinese aliases. ticker → (name, aliases)
_US_STATIC: dict[str, tuple[str, list[str]]] = {
    "NVDA": ("NVIDIA", ["輝達", "輝達", "輝", "黃仁勳"]),
    "TSLA": ("Tesla", ["特斯拉", "電動車"]),
    "AAPL": ("Apple", ["蘋果"]),
    "MSFT": ("Microsoft", ["微軟"]),
    "GOOGL": ("Alphabet", ["谷歌", "Google"]),
    "AMZN": ("Amazon", ["亞馬遜"]),
    "META": ("Meta Platforms", ["臉書", "Facebook"]),
    "TSM": ("Taiwan Semiconductor ADR", ["台積電ADR", "台積電 ADR"]),
    "AMD": ("Advanced Micro Devices", ["超微"]),
    "PLTR": ("Palantir", []),
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


def seed_us_static() -> int:
    """Upsert the curated US static map."""
    rows = [
        {"ticker": t, "market": "US", "canonical_name": name, "aliases": aliases}
        for t, (name, aliases) in _US_STATIC.items()
    ]
    count = upsert_reference_batch(rows, source="static")
    logger.info("stock_ref_us_seeded count=%d", count)
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
    """Scheduler entry point: refresh TW roster + US static map + indices."""
    tw = sync_tw_from_finmind()
    us = seed_us_static()
    idx = seed_indices()
    return {"tw": tw, "us": us, "index": idx}
