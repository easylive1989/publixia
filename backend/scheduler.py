import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from fetchers.yfinance_fetcher import fetch_taiex, fetch_fx, fetch_tw_stocks, fetch_us_stocks
from fetchers.fear_greed import fetch_fear_greed
from fetchers.chip_total import fetch_chip_total
from fetchers.fundamentals_stock import fetch_watchlist_stock_daily
from fetchers.ndc import fetch_ndc
from fetchers.news import fetch_news
from fetchers.volume import fetch_tw_volume, fetch_us_volume
from db import purge_old_data

TST = pytz.timezone("Asia/Taipei")

def start_scheduler() -> BackgroundScheduler:
    scheduler = BackgroundScheduler(timezone=TST)

    # 台股相關:每日 14:00 TST (台股 13:30 收盤後)
    scheduler.add_job(fetch_taiex,     CronTrigger(hour=14, minute=0, timezone=TST), id="taiex",     replace_existing=True)
    scheduler.add_job(fetch_tw_stocks, CronTrigger(hour=14, minute=5, timezone=TST), id="tw_stocks", replace_existing=True)

    # 美股 + 匯率:每日 06:00 TST (美股收盤後)
    scheduler.add_job(fetch_fx,        CronTrigger(hour=6, minute=0,  timezone=TST), id="fx",        replace_existing=True)
    scheduler.add_job(fetch_us_stocks, CronTrigger(hour=6, minute=5,  timezone=TST), id="us_stocks", replace_existing=True)

    # Daily 08:00 TST
    scheduler.add_job(fetch_fear_greed, CronTrigger(hour=8,  minute=0, timezone=TST), id="fear_greed", replace_existing=True)

    # Daily 18:00 TST (after TWSE settlement)
    scheduler.add_job(fetch_chip_total, CronTrigger(hour=18, minute=0, timezone=TST), id="chip_total", replace_existing=True)
    scheduler.add_job(fetch_tw_volume,  CronTrigger(hour=18, minute=5, timezone=TST), id="tw_volume",  replace_existing=True)

    # Phase 4: watchlist 個股 daily 主動拉(chip + PER),確保警示能觸發
    scheduler.add_job(
        fetch_watchlist_stock_daily,
        CronTrigger(hour=18, minute=30, timezone=TST),
        id="watchlist_chip_per",
        replace_existing=True,
    )

    # 美股每日 06:00 TST (美股收盤後)
    scheduler.add_job(fetch_us_volume,  CronTrigger(hour=6,  minute=10, timezone=TST), id="us_volume", replace_existing=True)

    # Monthly on the 1st at 09:00 TST
    scheduler.add_job(fetch_ndc,        CronTrigger(day=1,  hour=9,  minute=0, timezone=TST), id="ndc", replace_existing=True)

    # News: every 30 minutes
    scheduler.add_job(fetch_news, "interval", minutes=30, id="news", replace_existing=True)

    # Weekly cleanup of data older than 3 years
    scheduler.add_job(purge_old_data,   CronTrigger(day_of_week="sun", hour=0, timezone=TST), id="cleanup", replace_existing=True)

    scheduler.start()
    return scheduler
