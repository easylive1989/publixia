"""Tests for the real Discord notifier — patches send_to_discord to
capture payloads and assert embed structure."""
from unittest.mock import patch

from db.connection import get_connection
from services.strategy_notifier import (
    notify_signal, notify_runtime_error,
)


def _set_paul_webhook(url: str | None) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE users SET discord_webhook_url=? WHERE id=1",
            (url,),
        )
        conn.commit()


def test_notify_signal_no_webhook_silently_skips():
    """A user without a webhook still has signals written to DB; we just
    don't post anywhere. Logs a warning."""
    _set_paul_webhook(None)
    strategy = {"id": 1, "user_id": 1,
                "name": "s", "contract": "TX", "direction": "long"}
    today_bar = {"date": "2026-05-15", "close": 17250.0}
    with patch("services.strategy_notifier.send_to_discord") as mock_post:
        notify_signal(strategy, "ENTRY_SIGNAL", today_bar)
        mock_post.assert_not_called()


def test_notify_entry_signal_posts_embed_to_user_webhook():
    url = "https://discord.com/api/webhooks/1/" + "x" * 60
    _set_paul_webhook(url)
    strategy = {"id": 42, "user_id": 1, "name": "rsi_long",
                "contract": "TX", "direction": "long"}
    today_bar = {"date": "2026-05-15", "close": 17250.0}

    with patch("services.strategy_notifier.send_to_discord") as mock_post:
        notify_signal(strategy, "ENTRY_SIGNAL", today_bar)

    assert mock_post.call_count == 1
    args = mock_post.call_args.args
    sent_url, payload = args[0], args[1]
    assert sent_url == url
    assert "embeds" in payload
    embed = payload["embeds"][0]
    assert "📈" in embed["title"]
    assert "rsi_long" in embed["title"]
    fields = {f["name"]: f["value"] for f in embed["fields"]}
    assert "TX" in fields.get("方向 / 商品 / 口數", "")
    assert "17,250" in fields.get("訊號當日 close", "") or "17250" in fields.get("訊號當日 close", "")


def test_notify_exit_signal_take_profit_uses_green_color():
    url = "https://discord.com/api/webhooks/1/" + "x" * 60
    _set_paul_webhook(url)
    strategy = {"id": 5, "user_id": 1, "name": "x",
                "contract": "TX", "direction": "long",
                "entry_fill_price": 200.0,
                "entry_fill_date":  "2026-05-10",
                "pending_exit_kind": "TAKE_PROFIT"}
    today_bar = {"date": "2026-05-15", "close": 210.0}

    with patch("services.strategy_notifier.send_to_discord") as mock_post:
        notify_signal(strategy, "EXIT_SIGNAL", today_bar)

    payload = mock_post.call_args.args[1]
    embed = payload["embeds"][0]
    assert embed["color"] == 0x2ECC71
    assert "💰" in embed["title"]


def test_notify_runtime_error_posts_to_both_user_and_ops(monkeypatch):
    url = "https://discord.com/api/webhooks/1/" + "x" * 60
    _set_paul_webhook(url)
    import services.strategy_notifier as notifier_mod
    fake_settings = type("S", (), {
        "discord_ops_webhook_url": type("U", (), {
            "get_secret_value": lambda self: "https://ops/" + "y" * 60,
        })(),
    })()
    monkeypatch.setattr(notifier_mod, "settings", fake_settings)

    strategy = {"id": 9, "user_id": 1, "name": "x",
                "contract": "TX", "direction": "long"}
    err = ValueError("DSL exploded")

    with patch("services.strategy_notifier.send_to_discord") as mock_post:
        notify_runtime_error(strategy, err)

    sent_urls = [c.args[0] for c in mock_post.call_args_list]
    assert url in sent_urls
    assert any("ops" in s for s in sent_urls)


def test_notify_runtime_error_no_user_webhook_still_posts_to_ops(monkeypatch):
    _set_paul_webhook(None)
    import services.strategy_notifier as notifier_mod
    fake_settings = type("S", (), {
        "discord_ops_webhook_url": type("U", (), {
            "get_secret_value": lambda self: "https://ops/" + "y" * 60,
        })(),
    })()
    monkeypatch.setattr(notifier_mod, "settings", fake_settings)

    strategy = {"id": 9, "user_id": 1, "name": "x",
                "contract": "TX", "direction": "long"}
    err = RuntimeError("kaboom")

    with patch("services.strategy_notifier.send_to_discord") as mock_post:
        notify_runtime_error(strategy, err)

    sent_urls = [c.args[0] for c in mock_post.call_args_list]
    assert len(sent_urls) == 1
    assert "ops" in sent_urls[0]


def test_notify_signal_swallows_discord_failure(caplog):
    """Discord rejection must NOT raise — the engine call must complete
    so other strategies still evaluate. Failure is logged."""
    import logging
    url = "https://discord.com/api/webhooks/1/" + "x" * 60
    _set_paul_webhook(url)
    strategy = {"id": 1, "user_id": 1, "name": "s",
                "contract": "TX", "direction": "long"}
    today_bar = {"date": "2026-05-15", "close": 17250.0}

    def boom(*a, **kw):
        raise RuntimeError("Discord 503")

    with patch("services.strategy_notifier.send_to_discord", side_effect=boom):
        with caplog.at_level(logging.WARNING):
            notify_signal(strategy, "ENTRY_SIGNAL", today_bar)

    assert "503" in caplog.text or "discord" in caplog.text.lower()
