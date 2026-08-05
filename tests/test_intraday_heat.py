"""盤中大盤冷熱判讀：MIS 快照解析、線性外推、判讀組裝、Discord 推播。"""
import math
from datetime import date, time as dtime
from unittest.mock import patch

import pytest
from pydantic import SecretStr

import core.twse_intraday as intraday
from core.errors import (
    FetcherError, FetcherParseError, MarketClosed, StockDashboardError,
)
from core.twse_intraday import IntradaySnapshot
from core.markets import TW
from repositories import market_volume as repo
from services import intraday_heat as svc


class _Resp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def _mis_index(d="20260803", t="13:00:07", z="43,119.75"):
    return {"msgArray": [{"c": "t00", "d": d, "t": t, "z": z, "o": "42,900.00"}],
            "rtcode": "0000"}


def _mis_statis(tm="789,000,000,000"):
    return {"msgArray": [{"ex": "tse", "tm": tm}], "rtcode": "0000"}


def _mis_responses(index_payload, statis_payload):
    """requests.get stub routing by URL (index vs 大盤統計)."""
    def fake_get(url, params=None, headers=None, timeout=None):
        return _Resp(index_payload if url == intraday.INDEX_URL else statis_payload)
    return fake_get


def _history(n=80, start=date(2026, 1, 1)):
    """n 天量價齊漲的假歷史：成交金額大致貼著 index**1.6，殘差小幅擺盪，
    足夠讓 OLS 有位階跨度、也讓百分位有分佈。"""
    from datetime import timedelta
    rows = []
    for i in range(n):
        taiex = 20000.0 + 10.0 * i
        wobble = 1.0 + 0.01 * ((i % 7) - 3)
        turnover = 3000.0 * (taiex / 20000.0) ** 1.6 * wobble
        rows.append({
            "date": (start + timedelta(days=i)).isoformat(),
            "index_close": taiex,
            "turnover": turnover,
        })
    return rows


# --- 外推 ---------------------------------------------------------------

def test_extrapolate_at_1300_scales_by_full_session_over_elapsed():
    # 09:00–13:00 走完 240 分，全場 270 分 → ×1.125
    assert svc.extrapolate_turnover(8000.0, dtime(13, 0)) == pytest.approx(9000.0)


def test_extrapolate_at_close_is_identity():
    assert svc.extrapolate_turnover(8000.0, dtime(13, 30)) == pytest.approx(8000.0)


def test_extrapolate_never_scales_past_close():
    """收盤後（例如 job 延遲）不該再放大。"""
    assert svc.extrapolate_turnover(8000.0, dtime(14, 30)) == pytest.approx(8000.0)


# --- MIS 解析 -----------------------------------------------------------

def test_mis_snapshot_parses_index_and_turnover():
    with patch.object(
        intraday.requests, "get",
        side_effect=_mis_responses(_mis_index(), _mis_statis()),
    ):
        snap = intraday.fetch_snapshot(date(2026, 8, 3))
    assert snap == IntradaySnapshot(
        date="2026-08-03", time="13:00:07",
        taiex=43119.75, turnover=7890.0, is_final=False,
    )


def test_stale_index_date_is_reported_as_market_closed(monkeypatch):
    """休市日 MIS 仍回上一交易日的快照 —— 是「今天沒有盤」，不是抓不到。"""
    monkeypatch.setattr(
        intraday.requests, "get",
        _mis_responses(_mis_index(d="20260731"), _mis_statis()),
    )
    monkeypatch.setattr(intraday, "fetch_month", lambda y, m: [])
    with pytest.raises(MarketClosed) as e:
        intraday.fetch_snapshot(date(2026, 8, 3))
    assert "20260731" in str(e.value)


def test_wrong_turnover_magnitude_raises_instead_of_going_quiet(monkeypatch):
    """欄位若已經是億元（而非元），要擋下來並且吵 —— 不是靜靜地沒有判讀。"""
    monkeypatch.setattr(
        intraday.requests, "get",
        _mis_responses(_mis_index(), _mis_statis(tm="7,890")),
    )
    monkeypatch.setattr(intraday, "fetch_month", lambda y, m: [])
    with pytest.raises(FetcherError) as e:
        intraday.fetch_snapshot(date(2026, 8, 3))
    # 這不是休市，別被歸到安靜那一類
    assert not isinstance(e.value, MarketClosed)
    # 通報要能照著訊息直接定位到欄位跟數量級
    assert "'tm'" in str(e.value) and "raw=7890.0" in str(e.value)


def test_mis_missing_turnover_field_names_the_keys_it_saw():
    with patch.object(
        intraday.requests, "get",
        side_effect=_mis_responses(_mis_index(), {"msgArray": [{"ex": "tse", "tv": "1"}]}),
    ):
        with pytest.raises(FetcherParseError) as e:
            intraday._from_mis(date(2026, 8, 3))
    assert "'tv'" in str(e.value)  # 實際欄位列在訊息裡，好照著修


def test_empty_msgarray_reports_rtcode_and_rtmessage():
    """MIS 就是用 rtcode/rtmessage 講「你沒有 session」的，通報要看得到。"""
    with patch.object(
        intraday.requests, "get",
        side_effect=_mis_responses(
            {"msgArray": [], "rtcode": "5004", "rtmessage": "Fail"}, _mis_statis(),
        ),
    ):
        with pytest.raises(FetcherParseError) as e:
            intraday._from_mis(date(2026, 8, 3))
    assert "5004" in str(e.value) and "Fail" in str(e.value)


def test_non_dict_payload_is_a_parse_error_not_an_attribute_error():
    """回應形狀沒對過真實 session，list 之類的東西不能炸成 AttributeError。"""
    with patch.object(
        intraday.requests, "get",
        side_effect=_mis_responses([{"ex": "tse"}], _mis_statis()),
    ):
        with pytest.raises(FetcherParseError) as e:
            intraday._from_mis(date(2026, 8, 3))
    assert "list" in str(e.value)


def test_snapshot_failure_carries_the_mis_reason_for_the_alert(monkeypatch):
    """FMTQIK 也救不回來時，例外訊息要留著 MIS 的原始原因。"""
    def boom(*a, **kw):
        raise intraday.FetcherError("MIS down: connection reset")
    monkeypatch.setattr(intraday, "_get", boom)
    monkeypatch.setattr(intraday, "fetch_month", lambda y, m: [])
    with pytest.raises(FetcherError) as e:
        intraday.fetch_snapshot(date(2026, 8, 3))
    assert "connection reset" in str(e.value)


def test_snapshot_falls_back_to_fmtqik_after_close(monkeypatch):
    def boom(*a, **kw):
        raise intraday.FetcherError("MIS down")
    monkeypatch.setattr(intraday, "_get", boom)
    monkeypatch.setattr(intraday, "fetch_month", lambda y, m: [
        {"date": "2026-08-03", "index_close": 43119.75, "turnover": 8877.0},
    ])
    snap = intraday.fetch_snapshot(date(2026, 8, 3))
    assert snap.is_final is True
    assert snap.turnover == 8877.0


# --- 判讀組裝 -----------------------------------------------------------

def test_build_reading_extrapolates_and_classifies_hot():
    repo.upsert_days(TW, _history())
    snap = IntradaySnapshot(
        date="2026-03-30", time="13:00:00",
        taiex=20800.0, turnover=8000.0, is_final=False,
    )
    reading = svc.build_reading(snap)
    assert reading["at"] == "13:00"
    assert reading["partial_turnover"] == 8000.0
    # 部分金額外推成全日估計後才進模型
    assert reading["today"]["turnover"] == pytest.approx(9000.0)
    # 量能遠高於位階常態 → 百分位頂到最熱那一級
    assert reading["today"]["level"] == "very_hot"
    assert reading["prev"] is not None


def test_build_reading_replaces_todays_existing_row():
    """收盤 sync 已寫過今天時，盤中判讀要換掉那一列而不是多長一天。"""
    rows = _history()
    repo.upsert_days(TW, rows)
    today = rows[-1]["date"]
    snap = IntradaySnapshot(
        date=today, time="13:00:00", taiex=99999.0, turnover=1.0, is_final=True,
    )
    reading = svc.build_reading(snap)
    assert reading["today"]["date"] == today
    assert reading["today"]["index_close"] == 99999.0
    assert reading["prev"]["date"] == rows[-2]["date"]


def test_build_reading_needs_enough_history():
    repo.upsert_days(TW, _history(n=5))
    snap = IntradaySnapshot(
        date="2026-03-30", time="13:00:00", taiex=20800.0, turnover=8000.0, is_final=False,
    )
    assert svc.build_reading(snap) is None


def test_intraday_message_labels_the_estimate_and_shows_both_numbers():
    reading = {
        "today": {
            "date": "2026-08-03", "index_close": 43119.75, "turnover": 9000.0,
            "expected_turnover": 6540.0, "volume_ratio": 1.376,
            "percentile": 0.92, "level": "very_hot", "label": "明顯偏熱",
        },
        "prev": {"label": "偏熱", "percentile": 0.78},
        "partial_turnover": 8000.0,
        "at": "13:00",
        "is_final": False,
    }
    msg = svc.format_message(reading)
    assert "盤中 13:00 估計" in msg
    assert "明顯偏熱" in msg and "PR 92" in msg
    assert "盤中累計 8,000 億 → 全日估計 9,000 億" in msg
    assert "位階常態　6,540 億（量能比 1.38）" in msg
    assert "前一交易日　偏熱（PR 78）" in msg
    assert "收盤後會以實際成交金額重算" in msg


def test_final_message_drops_the_estimate_caveat():
    reading = {
        "today": {
            "date": "2026-08-03", "index_close": 43119.75, "turnover": 8877.0,
            "expected_turnover": 6540.0, "volume_ratio": 1.36,
            "percentile": 0.5, "level": "normal", "label": "正常",
        },
        "prev": None, "partial_turnover": 8877.0, "at": "13:30", "is_final": True,
    }
    msg = svc.format_message(reading)
    assert "收盤定案" in msg
    assert "成交金額　8,877 億" in msg
    assert "估計" not in msg


# --- job ----------------------------------------------------------------

def test_run_sends_reading_to_discord(monkeypatch):
    repo.upsert_days(TW, _history())
    monkeypatch.setattr(
        svc.settings, "discord_market_webhook_url", SecretStr("https://hook.test"),
    )
    monkeypatch.setattr(svc, "fetch_snapshot", lambda today: IntradaySnapshot(
        date="2026-03-30", time="13:00:00", taiex=20800.0, turnover=8000.0, is_final=False,
    ))
    sent = {}
    monkeypatch.setattr(svc, "send_to_discord", lambda url, payload: sent.update(
        url=url, content=payload["content"]))

    result = svc.run_intraday_heat_signal(today=date(2026, 3, 30))
    assert result["sent"] is True
    assert sent["url"] == "https://hook.test"
    assert "大盤成交金額冷熱判讀" in sent["content"]


def test_non_trading_day_still_says_so_on_discord(monkeypatch):
    """休市不是失敗，但也不能沒聲音 —— 「沒訊息」只該代表 job 沒跑。"""
    repo.upsert_days(TW, _history())

    def closed(today):
        raise MarketClosed("TWSE MIS 指數資料停在 '20260731'")
    monkeypatch.setattr(svc, "fetch_snapshot", closed)
    monkeypatch.setattr(svc, "send_to_discord", lambda *a: pytest.fail("不該推判讀"))
    alerts = []
    monkeypatch.setattr(svc, "send_alert", lambda title, **kw: alerts.append((title, kw)))

    assert svc.run_intraday_heat_signal(today=date(2026, 8, 3)) == {
        "sent": False, "reason": "market_closed",
    }
    (title, kw), = alerts
    assert kw["level"] == "info"
    assert "沒有盤" in title


def test_snapshot_failure_propagates_so_the_scheduler_alerts(monkeypatch):
    """抓不到快照是故障，不能被吞成一個安靜的 return。"""
    repo.upsert_days(TW, _history())

    def boom(today):
        raise FetcherError("MIS msgArray 是空的 rtcode='5004'")
    monkeypatch.setattr(svc, "fetch_snapshot", boom)
    with pytest.raises(FetcherError, match="5004"):
        svc.run_intraday_heat_signal(today=date(2026, 8, 3))


def test_insufficient_history_raises_with_the_row_count(monkeypatch):
    repo.upsert_days(TW, _history(n=5))
    monkeypatch.setattr(svc, "fetch_snapshot", lambda today: IntradaySnapshot(
        date="2026-03-30", time="13:00:00", taiex=20800.0, turnover=8000.0, is_final=False,
    ))
    with pytest.raises(StockDashboardError) as e:
        svc.run_intraday_heat_signal(today=date(2026, 3, 30))
    assert "5 列" in str(e.value)  # 通報看得到實際有幾列


def test_missing_webhook_raises_and_names_the_env_var(monkeypatch):
    repo.upsert_days(TW, _history())
    monkeypatch.setattr(svc.settings, "discord_market_webhook_url", None)
    monkeypatch.setattr(svc.settings, "discord_stock_webhook_url", None)
    monkeypatch.setattr(svc, "fetch_snapshot", lambda today: IntradaySnapshot(
        date="2026-03-30", time="13:00:00", taiex=20800.0, turnover=8000.0, is_final=False,
    ))
    with pytest.raises(StockDashboardError, match="DISCORD_MARKET_WEBHOOK_URL"):
        svc.run_intraday_heat_signal(today=date(2026, 3, 30))


def test_blank_webhook_counts_as_unset(monkeypatch):
    """未設定的 secret 會被 deploy 寫成空值，不能拿去 POST。"""
    monkeypatch.setattr(svc.settings, "discord_market_webhook_url", SecretStr("  "))
    monkeypatch.setattr(
        svc.settings, "discord_stock_webhook_url", SecretStr("https://fallback.test"),
    )
    assert svc._webhook() == "https://fallback.test"


def test_run_does_not_persist_the_estimate(monkeypatch):
    """估計值不能落地，否則前端在收盤資料回補前會把它當定案數字。"""
    rows = _history()
    repo.upsert_days(TW, rows)
    monkeypatch.setattr(
        svc.settings, "discord_market_webhook_url", SecretStr("https://hook.test"),
    )
    monkeypatch.setattr(svc, "fetch_snapshot", lambda today: IntradaySnapshot(
        date="2026-08-03", time="13:00:00", taiex=20800.0, turnover=8000.0, is_final=False,
    ))
    monkeypatch.setattr(svc, "send_to_discord", lambda url, payload: None)

    svc.run_intraday_heat_signal(today=date(2026, 8, 3))
    assert repo.latest_date(TW) == rows[-1]["date"]
    assert len(repo.list_days(TW)) == len(rows)


def test_webhook_falls_back_to_the_stock_hook(monkeypatch):
    monkeypatch.setattr(svc.settings, "discord_market_webhook_url", None)
    monkeypatch.setattr(
        svc.settings, "discord_stock_webhook_url", SecretStr("https://fallback.test"),
    )
    assert svc._webhook() == "https://fallback.test"
