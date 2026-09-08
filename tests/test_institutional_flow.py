"""TWSE BFI82U parsing, persistence, sync batching, and API enrichment."""
import math
from datetime import date, datetime
from unittest.mock import patch

import pytest
import requests
from pydantic import SecretStr

import core.twse_institutional as twse
from core.errors import FetcherError, FetcherParseError, StockDashboardError
from core.markets import TW
from jobs.registry import JOBS
from repositories import institutional_flow as repo
from repositories import market_volume
from services import institutional_flow_notification as notification
from services import institutional_flow_sync as sync
from services.market_heat import get_market_heat


class _Resp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


_BFI82U = {
    "stat": "OK",
    "date": "20260901",
    "data": [
        ["自營商(自行買賣)", "15,831,000,000", "12,674,000,000", "3,157,000,000"],
        ["自營商(避險)", "46,908,000,000", "33,735,000,000", "13,173,000,000"],
        ["投信", "39,106,000,000", "26,005,000,000", "13,101,000,000"],
        ["外資及陸資(不含外資自營商)", "401,999,000,000", "375,291,000,000", "26,708,000,000"],
        ["外資自營商", "0", "0", "0"],
        ["合計", "503,844,000,000", "447,705,000,000", "56,139,000,000"],
    ],
}


def test_fetch_day_parses_labels_and_integer_yuan():
    with patch.object(twse.requests, "get", return_value=_Resp(_BFI82U)):
        row = twse.fetch_day(date(2026, 9, 1))
    assert row["date"] == "2026-09-01"
    assert row["dealer_proprietary_buy"] == 15_831_000_000
    assert row["dealer_hedge_sell"] == 33_735_000_000
    assert row["foreign_buy"] == 401_999_000_000
    assert row["total_sell"] == 447_705_000_000


def test_fetch_day_no_data_is_none():
    with patch.object(twse.requests, "get", return_value=_Resp({"stat": "沒有符合條件的資料"})):
        assert twse.fetch_day(date(2026, 9, 2)) is None


def test_fetch_day_rejects_wrong_date_and_bad_difference():
    wrong_date = {**_BFI82U, "date": "20260831"}
    with patch.object(twse.requests, "get", return_value=_Resp(wrong_date)):
        with pytest.raises(FetcherParseError):
            twse.fetch_day(date(2026, 9, 1))

    bad = {**_BFI82U, "data": [list(row) for row in _BFI82U["data"]]}
    bad["data"][0][3] = "1"
    with patch.object(twse.requests, "get", return_value=_Resp(bad)):
        with pytest.raises(FetcherParseError):
            twse.fetch_day(date(2026, 9, 1))


def _raw(iso: str, multiplier: int = 1) -> dict:
    return {
        "date": iso,
        "dealer_proprietary_buy": 200 * multiplier,
        "dealer_proprietary_sell": 100 * multiplier,
        "dealer_hedge_buy": 400 * multiplier,
        "dealer_hedge_sell": 250 * multiplier,
        "trust_buy": 300 * multiplier,
        "trust_sell": 200 * multiplier,
        "foreign_buy": 1000 * multiplier,
        "foreign_sell": 800 * multiplier,
        "foreign_dealer_buy": 0,
        "foreign_dealer_sell": 0,
        "total_buy": 1900 * multiplier,
        "total_sell": 1350 * multiplier,
    }


def test_repository_upsert_is_idempotent():
    repo.upsert_days(TW, [_raw("2026-09-01")])
    repo.upsert_days(TW, [_raw("2026-09-01", 2)])
    rows = repo.list_days(TW)
    assert len(rows) == 1
    assert rows[0]["foreign_buy"] == 2000


def test_sync_prioritises_recent_missing_dates_and_refreshes_latest(monkeypatch):
    market_volume.upsert_days(TW, [
        {"date": f"2026-09-0{day}", "index_close": 10000 + day, "turnover": 1000}
        for day in range(1, 5)
    ])
    repo.upsert_days(TW, [_raw("2026-09-04")])
    fetched = []
    sleeps = []
    monkeypatch.setattr(sync.time, "sleep", sleeps.append)

    def fake_fetch(day):
        fetched.append(day.isoformat())
        return _raw(day.isoformat())

    monkeypatch.setattr(sync, "fetch_day", fake_fetch)
    result = sync.run_institutional_flow_sync(today=date(2026, 9, 4), batch_size=2)
    assert fetched == ["2026-09-04", "2026-09-03", "2026-09-02"]
    assert sleeps == [5.0, 5.0]
    assert result == {"requested": 3, "rows": 3, "remaining": 1}


def test_sync_retries_a_transient_day_with_backoff(monkeypatch):
    market_volume.upsert_days(TW, [
        {"date": "2026-09-01", "index_close": 10001, "turnover": 1000},
    ])
    attempts = 0
    sleeps = []

    def flaky_fetch(day):
        nonlocal attempts
        attempts += 1
        if attempts <= 3:
            raise FetcherError("temporary timeout")
        return _raw(day.isoformat())

    monkeypatch.setattr(sync, "fetch_day", flaky_fetch)
    monkeypatch.setattr(sync.time, "sleep", sleeps.append)

    result = sync.run_institutional_flow_sync(today=date(2026, 9, 1), batch_size=1)

    assert attempts == 4
    assert sleeps == [15.0, 30.0, 60.0]
    assert result == {"requested": 1, "rows": 1, "remaining": 0}


def test_sync_skips_a_permanent_failure_but_persists_later_days(monkeypatch):
    market_volume.upsert_days(TW, [
        {"date": f"2026-09-0{day}", "index_close": 10000 + day, "turnover": 1000}
        for day in range(1, 4)
    ])
    fetched = []

    def partially_broken_fetch(day):
        fetched.append(day.isoformat())
        if day == date(2026, 9, 3):
            return None
        return _raw(day.isoformat())

    monkeypatch.setattr(sync, "fetch_day", partially_broken_fetch)
    monkeypatch.setattr(sync.time, "sleep", lambda _: None)

    with pytest.raises(FetcherError, match=r"rows=1 failed=1 remaining=2"):
        sync.run_institutional_flow_sync(today=date(2026, 9, 3), batch_size=2)

    assert fetched == ["2026-09-03"] * 4 + ["2026-09-02"]
    assert repo.existing_dates(TW) == {"2026-09-02"}


def test_early_sync_only_refreshes_latest(monkeypatch):
    market_volume.upsert_days(TW, [
        {"date": f"2026-09-0{day}", "index_close": 10000 + day, "turnover": 1000}
        for day in range(1, 5)
    ])
    fetched = []

    def fake_fetch(day):
        fetched.append(day.isoformat())
        return _raw(day.isoformat())

    monkeypatch.setattr(sync, "fetch_day", fake_fetch)
    notified = []
    monkeypatch.setattr(sync, "notify_institutional_flow", notified.append)
    result = sync.run_institutional_flow_early_sync(today=date(2026, 9, 4))
    assert fetched == ["2026-09-04"]
    assert [row["date"] for row in notified] == ["2026-09-04"]
    assert result == {"requested": 1, "rows": 1, "remaining": 3}


def test_market_heat_attaches_billion_amounts_and_turnover_ratio():
    rows = []
    for index in range(60):
        close = 10000 + index * 10
        rows.append({
            "date": f"2026-{1 + index // 28:02d}-{1 + index % 28:02d}",
            "index_close": close,
            "turnover": math.exp(-7.75 + 1.608 * math.log(close)),
        })
    market_volume.upsert_days(TW, rows)
    latest = rows[-1]
    raw = _raw(latest["date"], 100_000_000)
    repo.upsert_days(TW, [raw])

    payload = get_market_heat(days=1)
    institutional = payload["latest"]["institutional"]
    assert institutional["dealer_proprietary"] == {
        "buy": 200.0, "sell": 100.0, "net": 100.0,
    }
    assert institutional["dealer"]["net"] == 250.0
    assert institutional["foreign"]["net"] == 200.0
    expected_ratio = (1900 + 1350) / (2 * latest["turnover"]) * 100
    assert institutional["turnover_ratio"] == pytest.approx(expected_ratio)


@pytest.fixture
def discord(monkeypatch):
    sent = []
    monkeypatch.setattr(notification.settings, "discord_market_webhook_url", SecretStr("https://market.test"))
    monkeypatch.setattr(notification.settings, "discord_stock_webhook_url", None)
    monkeypatch.setattr(notification, "send_to_discord", lambda url, payload: sent.append((url, payload)))
    monkeypatch.setattr(sync.time, "sleep", lambda _: None)
    monkeypatch.setattr(sync, "fetch_day", lambda day: _raw(day.isoformat(), 100_000_000))
    return sent


def test_notification_formats_buy_sell_net_and_combines_dealers():
    row = _raw("2026-09-01", 100_000_000)
    row.update(trust_buy=100_000_000, trust_sell=200_000_000,
               foreign_dealer_buy=50_000_000_000)
    content = notification.format_message(row)
    assert "2026-09-01" in content and "單位：億元" in content
    assert "**外資及陸資**｜買進 1,000.00｜賣出 800.00｜買超 200.00" in content
    assert "**投信**｜買進 1.00｜賣出 2.00｜賣超 1.00" in content
    assert "**自營商**｜買進 600.00｜賣出 350.00｜買超 250.00" in content
    assert "**合計**｜買進 1,900.00｜賣出 1,350.00｜買超 550.00" in content
    assert "TWSE BFI82U" in content
    assert len(content) < 2000
    row["trust_sell"] = row["trust_buy"]
    assert "買賣平衡 0.00" in notification.format_message(row)


def test_notification_deduplicates_persistently_and_sends_revisions(discord):
    row = _raw("2026-09-01")
    assert notification.notify_institutional_flow(row) is True
    fingerprint = repo.notification_fingerprint(TW, row["date"])
    assert fingerprint
    # 重讀 DB 後仍查重；時間戳等 metadata 不影響金額指紋。
    repo.upsert_days(TW, [row])
    reloaded = {**repo.list_days(TW)[0], "updated_at": "later"}
    assert notification.notify_institutional_flow(reloaded) is False
    assert len(discord) == 1
    assert notification.notify_institutional_flow(_raw("2026-09-01", 2)) is True
    assert repo.notification_fingerprint(TW, row["date"]) != fingerprint
    assert "（更新）" in discord[-1][1]["content"]
    assert notification.notify_institutional_flow(_raw("2026-09-02", 2)) is True
    assert "（更新）" not in discord[-1][1]["content"]


@pytest.mark.parametrize("market_hook", [None, "", "   "])
def test_notification_falls_back_to_stock_webhook(monkeypatch, discord, market_hook):
    monkeypatch.setattr(notification.settings, "discord_market_webhook_url",
                        SecretStr(market_hook) if market_hook is not None else None)
    monkeypatch.setattr(notification.settings, "discord_stock_webhook_url", SecretStr(" https://stock.test "))
    notification.notify_institutional_flow(_raw("2026-09-01"))
    assert discord[0][0] == "https://stock.test"


def test_missing_webhook_raises_without_marking_sent(monkeypatch, discord):
    monkeypatch.setattr(notification.settings, "discord_market_webhook_url", None)
    with pytest.raises(StockDashboardError, match="沒有 Discord webhook"):
        notification.notify_institutional_flow(_raw("2026-09-01"))
    assert repo.notification_fingerprint(TW, "2026-09-01") is None
    assert discord == []


@pytest.mark.parametrize("revision", [False, True])
def test_failed_notification_can_retry_without_exposing_webhook(monkeypatch, discord, revision):
    if revision:
        notification.notify_institutional_flow(_raw("2026-09-01"))
    previous = repo.notification_fingerprint(TW, "2026-09-01")
    response = requests.Response()
    response.status_code = 503
    error = requests.HTTPError("503 https://discord.test/secret-token", response=response)
    with patch.object(notification, "send_to_discord", side_effect=error):
        with pytest.raises(StockDashboardError, match="HTTP=503") as raised:
            notification.notify_institutional_flow(_raw("2026-09-01", 2))
    assert "secret-token" not in str(raised.value)
    assert repo.notification_fingerprint(TW, "2026-09-01") == previous
    assert notification.notify_institutional_flow(_raw("2026-09-01", 2)) is True
    assert len(discord) == (2 if revision else 1)


@pytest.mark.parametrize("run_early", [False, True])
def test_scheduled_evening_sync_sends_or_deduplicates_after_early(monkeypatch, discord, run_early):
    class TaipeiToday(datetime):
        @classmethod
        def now(cls, tz):
            assert str(tz) == "Asia/Taipei"
            return tz.localize(datetime(2026, 9, 1, 20))

    monkeypatch.setattr(sync, "datetime", TaipeiToday)
    market_volume.upsert_days(TW, [{"date": "2026-09-01", "index_close": 10000, "turnover": 1000}])
    if run_early:
        JOBS["institutional_flow_sync_early"].fn()
    JOBS["institutional_flow_sync"].fn()
    assert len(discord) == 1
    assert discord[0][0] == "https://market.test"


def test_manual_sync_and_backfill_do_not_send_notifications(discord):
    market_volume.upsert_days(TW, [
        {"date": f"2026-09-0{day}", "index_close": 10000, "turnover": 1000}
        for day in range(1, 4)
    ])
    sync.run_institutional_flow_sync(today=date(2026, 9, 3))
    assert discord == []


def test_historical_failure_does_not_block_today_notification(monkeypatch, discord):
    market_volume.upsert_days(TW, [
        {"date": f"2026-09-0{day}", "index_close": 10000, "turnover": 1000}
        for day in range(1, 4)
    ])

    def fetch(day):
        if day < date(2026, 9, 3):
            assert len(discord) == 1  # 當日通知在歷史回補前就已送達。
            raise FetcherError("historical timeout")
        return _raw(day.isoformat())

    monkeypatch.setattr(sync, "fetch_day", fetch)
    with pytest.raises(FetcherError, match="historical timeout"):
        sync.run_institutional_flow_sync(today=date(2026, 9, 3), notify=True)
    assert len(discord) == 1
    assert "2026-09-03" in discord[0][1]["content"]


def test_notification_failure_keeps_syncing_history(monkeypatch, discord):
    market_volume.upsert_days(TW, [
        {"date": f"2026-09-0{day}", "index_close": 10000, "turnover": 1000}
        for day in range(1, 4)
    ])
    monkeypatch.setattr(notification.settings, "discord_market_webhook_url", None)
    with pytest.raises(StockDashboardError, match="沒有 Discord webhook"):
        sync.run_institutional_flow_sync(today=date(2026, 9, 3), notify=True)
    assert len(repo.list_days(TW)) == 3
    assert repo.notification_fingerprint(TW, "2026-09-03") is None


def test_failed_current_fetch_does_not_send_stored_or_historical_data(monkeypatch, discord):
    market_volume.upsert_days(TW, [
        {"date": f"2026-09-0{day}", "index_close": 10000, "turnover": 1000}
        for day in range(1, 4)
    ])
    repo.upsert_days(TW, [_raw("2026-09-03")])
    monkeypatch.setattr(sync, "fetch_day", lambda day: None if day.day == 3 else _raw(day.isoformat()))
    with pytest.raises(FetcherError, match="2026-09-03"):
        sync.run_institutional_flow_sync(today=date(2026, 9, 3), notify=True)
    assert discord == []
    assert len(repo.list_days(TW)) == 3


def test_stale_market_data_does_not_send_yesterday_as_today(discord):
    market_volume.upsert_days(TW, [{"date": "2026-09-01", "index_close": 10000, "turnover": 1000}])
    with pytest.raises(FetcherError, match="最新交易日為 2026-09-01"):
        sync.run_institutional_flow_early_sync(today=date(2026, 9, 2))
    assert discord == []
