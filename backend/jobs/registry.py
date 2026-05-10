"""Central registry of scheduled jobs.

Single source of truth for job name → callable + default cron expression.
The scheduler seeds `scheduler_jobs` from this dict on startup (insert-if-
missing) and then reads the row back to decide whether to wire the job up
and at what cadence.

All cron expressions are 5-field POSIX style (minute hour dom month dow)
and interpreted in the scheduler's timezone (Asia/Taipei).
"""
from collections.abc import Callable
from dataclasses import dataclass

from fetchers.yfinance_fetcher import (
    fetch_taiex, fetch_fx, fetch_tw_stocks, fetch_us_stocks,
)
from fetchers.fear_greed import fetch_fear_greed
from fetchers.chip_total import fetch_chip_total
from fetchers.fundamentals_stock import fetch_watchlist_stock_daily
from fetchers.ndc import fetch_ndc
from fetchers.news import fetch_news
from fetchers.volume import fetch_tw_volume, fetch_us_volume
from fetchers.futures import (
    fetch_tw_futures, fetch_tw_futures_mtx, fetch_tw_futures_tmf,
)
from fetchers.institutional_futures import fetch_latest as fetch_inst_futures
from fetchers.institutional_options import fetch_latest as fetch_inst_options
from fetchers.large_trader import fetch_latest as fetch_large_trader
from fetchers.futures_settlement import fetch_settlement_refresh
from services.backup import backup_db_to_r2
from db import purge_old_data


@dataclass(frozen=True)
class JobSpec:
    fn: Callable[[], object]
    default_cron: str
    description: str


JOBS: dict[str, JobSpec] = {
    "taiex":              JobSpec(fetch_taiex,                "0 14 * * *",   "TAIEX 加權指數"),
    "tw_stocks":          JobSpec(fetch_tw_stocks,            "5 14 * * *",   "台股 watchlist 收盤快照"),
    "fx":                 JobSpec(fetch_fx,                   "0 6 * * *",    "美金匯率"),
    "us_stocks":          JobSpec(fetch_us_stocks,            "5 6 * * *",    "美股 watchlist 收盤快照"),
    "fear_greed":         JobSpec(fetch_fear_greed,           "0 8 * * *",    "Fear & Greed Index"),
    "chip_total":         JobSpec(fetch_chip_total,           "0 18 * * *",   "整體市場籌碼面"),
    "inst_futures":       JobSpec(fetch_inst_futures,         "0 18 * * *",   "外資台指期/小台未平倉"),
    "inst_options":       JobSpec(fetch_inst_options,         "10 18 * * *",  "三大法人 TXO 選擇權買賣權分計"),
    "large_trader":       JobSpec(fetch_large_trader,         "5 18 * * *",   "大額交易人 (散戶多空比)"),
    "futures_settlement": JobSpec(fetch_settlement_refresh,   "0 2 1 * *",    "TX 結算日 (每月補未來 12 個月)"),
    "tw_volume":          JobSpec(fetch_tw_volume,            "5 18 * * *",   "台股大盤量能"),
    "tw_futures":         JobSpec(fetch_tw_futures,           "30 17 * * *",  "台指期 (TX) 日線"),
    "tw_futures_mtx":     JobSpec(fetch_tw_futures_mtx,       "30 17 * * *",  "小台指期 (MTX) 日線"),
    "tw_futures_tmf":     JobSpec(fetch_tw_futures_tmf,       "30 17 * * *",  "微台指期 (TMF) 日線"),
    "watchlist_chip_per": JobSpec(fetch_watchlist_stock_daily,"30 18 * * *",  "watchlist 個股籌碼/PER"),
    "us_volume":          JobSpec(fetch_us_volume,            "10 6 * * *",   "美股大盤量能"),
    "ndc":                JobSpec(fetch_ndc,                  "0 9 1 * *",    "國發會景氣對策信號"),
    "news":               JobSpec(fetch_news,                 "*/30 * * * *", "新聞 (每 30 分鐘)"),
    "cleanup":            JobSpec(purge_old_data,             "0 0 * * 0",    "舊資料清理 (週日)"),
    "backup_db":          JobSpec(backup_db_to_r2,            "0 3 * * *",    "DB 備份至 Cloudflare R2"),
}
