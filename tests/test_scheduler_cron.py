"""cron 字串照 POSIX 語意解讀（星期 0=週日），不是 APScheduler 的 0=週一。

會有這支測試是因為 2026-08-10（週一）沒有盤中判讀：`CronTrigger.from_crontab`
把 `0 13 * * 1-5` 掛成了週二~週六。所以這裡直接斷言「哪幾天真的會燒」，而不
只是斷言字串轉換 —— 前者才是壞掉時看得見的東西。
"""
from datetime import datetime, timedelta

import pytest
import pytz

from jobs.cron import crontab_trigger, translate_day_of_week
from jobs.registry import JOBS

TST = pytz.timezone("Asia/Taipei")


def fire_days(expr: str, count: int = 7, start=datetime(2026, 8, 9)) -> list[str]:
    """接下來 `count` 次觸發落在星期幾（2026-08-09 是週日）。"""
    trigger = crontab_trigger(expr, TST)
    after = TST.localize(start)
    days = []
    for _ in range(count):
        nxt = trigger.get_next_fire_time(None, after)
        days.append(nxt.strftime("%a"))
        after = nxt + timedelta(seconds=1)
    return days


class TestTranslateDayOfWeek:
    @pytest.mark.parametrize("field,expected", [
        ("*", "*"),
        ("1-5", "mon,tue,wed,thu,fri"),      # 平日
        ("2-6", "tue,wed,thu,fri,sat"),
        ("0", "sun"),
        ("7", "sun"),                        # POSIX 的 7 也是週日
        ("6,0", "sat,sun"),                  # 週末
        ("1,3,5", "mon,wed,fri"),
        ("5-1", "mon,fri,sat,sun"),          # 跨週末的區間（輸出照 mon→sun 排）
        ("*/2", "tue,thu,sat,sun"),          # POSIX 0,2,4,6 = 日二四六
        ("1-5/2", "mon,wed,fri"),
        ("5/2", "fri"),                      # 從週五起每 2 天，週六為界
        ("mon-fri", "mon,tue,wed,thu,fri"),  # 英文縮寫沿用 POSIX 對照
        ("SUN", "sun"),
    ])
    def test_posix_semantics(self, field, expected):
        assert translate_day_of_week(field) == expected

    @pytest.mark.parametrize("field", ["8", "-1", "funday", "1-5/0", "1-5/x", "1,,3", ""])
    def test_rejects_garbage(self, field):
        # 掛不上的 job 完全不會執行，所以寧可在 start_scheduler 就丟例外
        # （那裡會 send_alert 通報），也不要默默排出一個錯的時間表。
        with pytest.raises(ValueError):
            translate_day_of_week(field)


class TestCrontabTrigger:
    def test_weekday_expression_skips_the_weekend_not_monday(self):
        # from_crontab 在這裡會回 ['Tue','Wed','Thu','Fri','Sat',…]
        assert fire_days("0 13 * * 1-5", 5) == ["Mon", "Tue", "Wed", "Thu", "Fri"]

    def test_daily_expression_fires_every_day(self):
        assert fire_days("0 3 * * *", 7) == [
            "Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"
        ]

    def test_honours_minute_hour_and_timezone(self):
        trigger = crontab_trigger("30 13 * * 1-5", TST)
        nxt = trigger.get_next_fire_time(None, TST.localize(datetime(2026, 8, 10, 9)))
        assert nxt.strftime("%Y-%m-%d %H:%M %Z") == "2026-08-10 13:30 CST"

    def test_day_and_month_fields_still_apply(self):
        trigger = crontab_trigger("0 3 1 1 *", TST)
        nxt = trigger.get_next_fire_time(None, TST.localize(datetime(2026, 8, 10)))
        assert nxt.date().isoformat() == "2027-01-01"

    @pytest.mark.parametrize("expr", ["0 13 * *", "0 13 * * 1-5 7", ""])
    def test_rejects_wrong_field_count(self, expr):
        with pytest.raises(ValueError):
            crontab_trigger(expr, TST)


class TestRegistryDefaults:
    """註冊表裡的預設 cron 全部要能掛上，而且落在該落的日子。"""

    def test_all_defaults_parse(self):
        for name, spec in JOBS.items():
            assert crontab_trigger(spec.default_cron, TST) is not None, name

    def test_tw_jobs_run_on_taipei_weekdays(self):
        for name in (
            "intraday_heat_signal",
            "market_volume_sync",
            "market_breadth_sync",
            "institutional_flow_sync_early",
            "institutional_flow_sync",
        ):
            assert fire_days(JOBS[name].default_cron, 5) == [
                "Mon", "Tue", "Wed", "Thu", "Fri"
            ], name
