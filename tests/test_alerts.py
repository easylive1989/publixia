"""core.alerts：失敗要推得出去，而且訊息要足以直接定位。"""
import logging

import pytest
from pydantic import SecretStr

import core.alerts as alerts
from core.errors import FetcherError


@pytest.fixture(autouse=True)
def _no_webhooks(monkeypatch):
    """預設三支 webhook 都沒設 —— 每個測試自己開需要的那支。"""
    for name in (
        "discord_ops_webhook_url",
        "discord_market_webhook_url",
        "discord_stock_webhook_url",
    ):
        monkeypatch.setattr(alerts.settings, name, None)


def _capture(monkeypatch) -> list:
    sent = []
    monkeypatch.setattr(
        alerts, "send_to_discord", lambda url, payload: sent.append((url, payload))
    )
    return sent


# --- webhook 取用順序 -----------------------------------------------------

def test_ops_webhook_wins_when_configured(monkeypatch):
    monkeypatch.setattr(alerts.settings, "discord_ops_webhook_url", SecretStr("https://ops"))
    monkeypatch.setattr(alerts.settings, "discord_market_webhook_url", SecretStr("https://mkt"))
    assert alerts._webhook() == "https://ops"


def test_falls_back_to_the_reading_webhooks(monkeypatch):
    """沒有專用維運頻道時，寧可跟判讀擠同一個頻道，也不要靜音。"""
    monkeypatch.setattr(alerts.settings, "discord_stock_webhook_url", SecretStr("https://stock"))
    assert alerts._webhook() == "https://stock"


def test_blank_webhook_counts_as_unset(monkeypatch):
    """未設定的 secret 在 deploy 時會被寫成 `DISCORD_OPS_WEBHOOK_URL=`。"""
    monkeypatch.setattr(alerts.settings, "discord_ops_webhook_url", SecretStr(""))
    monkeypatch.setattr(alerts.settings, "discord_market_webhook_url", SecretStr("https://mkt"))
    assert alerts._webhook() == "https://mkt"


# --- 訊息內容 -------------------------------------------------------------

def test_alert_names_the_exception_type_and_message():
    content = alerts.format_alert(
        "排程失敗｜intraday_heat_signal",
        error=FetcherError("MIS msgArray 是空的 rtcode='5004'"),
        fields={"排程": "`0 13 * * 1-5`"},
    )
    assert "🚨" in content
    assert "FetcherError" in content and "5004" in content
    assert "0 13 * * 1-5" in content


def test_alert_includes_the_underlying_cause():
    try:
        try:
            raise ValueError("connection reset")
        except ValueError as inner:
            raise FetcherError("MIS 取不到快照") from inner
    except FetcherError as e:
        content = alerts.format_alert("失敗", error=e)
    assert "起因" in content and "connection reset" in content


def test_a_cause_already_quoted_in_the_message_is_not_repeated():
    """外層訊息包了原因時，再貼一行只會把有用的欄位擠出畫面。"""
    try:
        try:
            raise ValueError("rtcode='5004'")
        except ValueError as inner:
            raise FetcherError(f"MIS 取不到快照（{inner}）") from inner
    except FetcherError as e:
        content = alerts.format_alert("失敗", error=e)
    assert "起因" not in content
    assert "5004" in content


def test_unexpected_errors_carry_a_traceback_but_domain_errors_do_not():
    """領域例外的訊息自己就講完了；非預期例外才需要 traceback 找現場。"""
    try:
        {}["nope"]
    except KeyError as e:
        assert "```" in alerts.format_alert("炸了", error=e)

    assert "```" not in alerts.format_alert("炸了", error=FetcherError("說完了"))


def test_content_is_truncated_below_the_discord_limit():
    content = alerts.format_alert("x", fields={"long": "y" * 5000})
    assert len(content) <= 2000
    assert "已截斷" in content


def test_info_level_uses_a_quieter_icon():
    assert alerts.format_alert("今天沒有盤", level="info").startswith("ℹ️")


# --- 送出 -----------------------------------------------------------------

def test_send_alert_posts_to_the_resolved_webhook(monkeypatch):
    monkeypatch.setattr(alerts.settings, "discord_ops_webhook_url", SecretStr("https://ops"))
    sent = _capture(monkeypatch)
    assert alerts.send_alert("排程失敗", error=FetcherError("boom")) is True
    (url, payload), = sent
    assert url == "https://ops"
    assert "boom" in payload["content"]


def test_without_any_webhook_the_whole_alert_lands_in_the_log(caplog):
    """推不出去時至少 journal 裡要有完整內容，不能什麼都不留。"""
    with caplog.at_level(logging.ERROR):
        assert alerts.send_alert("排程失敗", error=FetcherError("boom")) is False
    assert "alert_undeliverable_no_webhook" in caplog.text
    assert "boom" in caplog.text


def test_a_failing_alert_never_masks_the_original_error(monkeypatch, caplog):
    monkeypatch.setattr(alerts.settings, "discord_ops_webhook_url", SecretStr("https://ops"))

    def boom(url, payload):
        raise RuntimeError("discord 502")
    monkeypatch.setattr(alerts, "send_to_discord", boom)

    with caplog.at_level(logging.ERROR):
        assert alerts.send_alert("排程失敗", error=FetcherError("原本的錯")) is False
    assert "alert_send_failed" in caplog.text
    assert "原本的錯" in caplog.text  # 原始內容仍留在 log
