"""Strategy notifier — Discord webhook poster.

Two surfaces:
  - notify_signal(strategy, kind, today_bar): per-user webhook only.
    No fallback — if the user has no webhook configured, we silently
    skip (the engine still writes the signal row, so the frontend
    history shows it).
  - notify_runtime_error(strategy, error): dual fan-out. Posts to the
    user's webhook (if set) AND the ops global webhook
    (settings.discord_ops_webhook_url). The ops post is the operator's
    monitoring surface; the user post lets them know their strategy
    is broken.

Both swallow Discord failures so a flaky webhook can't take down the
fetcher path.
"""
import logging
from typing import Optional

from core.discord import send_to_discord
from core.settings import settings
from repositories.users import get_user_with_settings


logger = logging.getLogger(__name__)


_ENTRY_TITLE = "📈 進場訊號"
_EXIT_TITLES = {
    "TAKE_PROFIT":  ("💰 停利訊號", 0x2ECC71),
    "STOP_LOSS":    ("🛑 停損訊號", 0xE67E22),
    "TIMEOUT":      ("⏰ 持倉到期",  0x95A5A6),
    "MANUAL_RESET": ("🔧 手動平倉", 0x95A5A6),
}


def _format_close(value: Optional[float]) -> str:
    if value is None:
        return "—"
    return f"{value:,.2f}"


def _build_signal_payload(strategy: dict, kind: str, today_bar: dict) -> dict:
    name = strategy.get("name", "(unnamed)")
    direction = strategy.get("direction", "")
    contract = strategy.get("contract", "")
    size = strategy.get("contract_size", 1)
    close = today_bar.get("close")
    date = today_bar.get("date", "")

    direction_text = "多" if direction == "long" else "空"
    fields = [
        {"name": "方向 / 商品 / 口數",
         "value": f"{direction_text} / {contract} / {size}",
         "inline": True},
        {"name": "訊號當日 close",
         "value": _format_close(close),
         "inline": True},
    ]

    if kind == "ENTRY_SIGNAL":
        title = f"{_ENTRY_TITLE} — {name}"
        color = 0xE74C3C if direction == "long" else 0x16A085
        description = "策略觸發進場條件,**明日 open 假想進場**。"
    else:
        reason = strategy.get("pending_exit_kind") or "MANUAL_RESET"
        icon_title, color = _EXIT_TITLES.get(reason, ("⚠️ 出場", 0x95A5A6))
        title = f"{icon_title} — {name}"
        if kind == "EXIT_FILLED":
            # force_close path: the trade is already settled at today's close.
            description = "**已用最新 close 假想結算。**"
        else:
            # EXIT_SIGNAL path: actual fill happens next bar at open.
            description = "**明日 open 假想出場。**"
        entry_price = strategy.get("entry_fill_price")
        if entry_price is not None and close is not None:
            if direction == "long":
                pnl = close - entry_price
            else:
                pnl = entry_price - close
            fields.append({
                "name": "預估 PnL(以當日 close 估算)",
                "value": f"{pnl:+,.2f} 點",
                "inline": True,
            })
        if strategy.get("entry_fill_date"):
            fields.append({
                "name": "進場價 / 進場日",
                "value": f"{_format_close(entry_price)} @ {strategy['entry_fill_date']}",
                "inline": True,
            })

    return {
        "embeds": [{
            "title":       title,
            "description": description,
            "color":       color,
            "fields":      fields,
            "footer":      {"text": f"Strategy #{strategy.get('id')} · {date}"},
        }]
    }


def _build_runtime_error_embed(strategy: dict, error: Exception, *,
                               audience: str) -> dict:
    name = strategy.get("name", "(unnamed)")
    msg = str(error)[:600]
    if audience == "user":
        description = (
            f"您的策略 **{name}** 發生錯誤、即時通知已暫停。"
            f"請檢查條件後重新啟用。\n\n`{msg}`"
        )
    else:
        description = (
            f"strategy_id={strategy.get('id')} "
            f"user_id={strategy.get('user_id')} "
            f"name={name!r} contract={strategy.get('contract')!r}\n\n"
            f"```\n{msg}\n```"
        )
    return {
        "embeds": [{
            "title":       "⚠️ 策略執行錯誤",
            "description": description,
            "color":       0xE74C3C,
        }]
    }


def notify_signal(strategy: dict, kind: str, today_bar: dict) -> None:
    """Post a Discord embed for ENTRY_SIGNAL / EXIT_SIGNAL / EXIT_FILLED.
    Silently skips if the user has no webhook configured."""
    user = get_user_with_settings(strategy["user_id"])
    webhook = (user or {}).get("discord_webhook_url")
    if not webhook:
        logger.warning(
            "strategy_notify_skip_no_webhook strategy_id=%s user_id=%s",
            strategy.get("id"), strategy.get("user_id"),
        )
        return
    payload = _build_signal_payload(strategy, kind, today_bar)
    try:
        send_to_discord(webhook, payload)
    except Exception as e:
        logger.warning(
            "strategy_notify_discord_failed strategy_id=%s err=%s",
            strategy.get("id"), str(e)[:200],
        )


def notify_runtime_error(strategy: dict, error: Exception) -> None:
    """Dual fan-out: post to the user's webhook (if configured) AND the
    ops global webhook (settings.discord_ops_webhook_url)."""
    user = get_user_with_settings(strategy["user_id"])
    user_webhook = (user or {}).get("discord_webhook_url")
    if user_webhook:
        try:
            send_to_discord(
                user_webhook,
                _build_runtime_error_embed(strategy, error, audience="user"),
            )
        except Exception as e:
            logger.warning(
                "strategy_notify_user_err_failed strategy_id=%s err=%s",
                strategy.get("id"), str(e)[:200],
            )

    ops_secret = getattr(settings, "discord_ops_webhook_url", None)
    if ops_secret is not None:
        ops_url = ops_secret.get_secret_value() if hasattr(ops_secret, "get_secret_value") else str(ops_secret)
        if ops_url:
            try:
                send_to_discord(
                    ops_url,
                    _build_runtime_error_embed(strategy, error, audience="ops"),
                )
            except Exception as e:
                logger.warning(
                    "strategy_notify_ops_err_failed strategy_id=%s err=%s",
                    strategy.get("id"), str(e)[:200],
                )
