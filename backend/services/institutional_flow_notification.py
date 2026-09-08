"""三大法人每日買賣金額 → Discord；同日金額未變不重送，修訂另行通知。"""
import hashlib
import json
import logging
import threading

import requests

from core.discord import send_to_discord
from core.errors import StockDashboardError
from core.markets import TW
from core.settings import settings
from repositories import institutional_flow as repo

logger = logging.getLogger(__name__)
_SEND_LOCK = threading.Lock()
_YI = 100_000_000


def format_message(row: dict, *, updated: bool = False) -> str:
    title = "三大法人買賣金額（更新）" if updated else "三大法人買賣金額"
    lines = [f"🏦 **{title}**　{row['date']}", "", "單位：億元"]
    amounts = [
        ("外資及陸資", row["foreign_buy"], row["foreign_sell"]),
        ("投信", row["trust_buy"], row["trust_sell"]),
        (
            "自營商",
            row["dealer_proprietary_buy"] + row["dealer_hedge_buy"],
            row["dealer_proprietary_sell"] + row["dealer_hedge_sell"],
        ),
        ("合計", row["total_buy"], row["total_sell"]),
    ]
    for label, buy, sell in amounts:
        net = buy - sell
        direction = "買超" if net > 0 else "賣超" if net < 0 else "買賣平衡"
        lines.append(
            f"**{label}**｜買進 {buy / _YI:,.2f}｜賣出 {sell / _YI:,.2f}"
            f"｜{direction} {abs(net) / _YI:,.2f}"
        )
    lines += [
        "",
        "※ 自營商含自行買賣與避險；外資自營商已計入自營商，不重複加總。",
        "來源：TWSE BFI82U｜https://stock.paul-learning.dev",
    ]
    return "\n".join(lines)


def notify_institutional_flow(row: dict) -> bool:
    """僅在送出成功後存指紋，失敗可由下一次同步重試。呼叫端只傳當日新抓資料。"""
    amounts = {
        key: value for key, value in row.items()
        if key.endswith(("_buy", "_sell"))
    }
    fingerprint = hashlib.sha256(
        json.dumps(amounts, sort_keys=True).encode("utf-8")
    ).hexdigest()
    # 早晚排程是不同 job；序列化同一程序的查重與送出，避免重疊時雙發。
    with _SEND_LOCK:
        previous = repo.notification_fingerprint(TW, row["date"])
        if previous == fingerprint:
            logger.info("institutional_flow_notification_unchanged date=%s", row["date"])
            return False

        webhook = None
        for candidate in (
            settings.discord_market_webhook_url,
            settings.discord_stock_webhook_url,
        ):
            url = candidate.get_secret_value().strip() if candidate else ""
            if url:
                webhook = url
                break
        if not webhook:
            raise StockDashboardError(
                f"{row['date']} 三大法人通知沒有 Discord webhook：請設定 "
                "DISCORD_MARKET_WEBHOOK_URL 或 DISCORD_STOCK_WEBHOOK_URL"
            )

        try:
            send_to_discord(webhook, {"content": format_message(row, updated=previous is not None)})
        except requests.RequestException as exc:
            # requests 的例外可能帶完整 webhook token，不寫進排程紀錄或維運通報。
            status = exc.response.status_code if exc.response is not None else "unavailable"
            raise StockDashboardError(
                f"{row['date']} 三大法人 Discord 通知失敗："
                f"{type(exc).__name__} HTTP={status}，下次同步會重試"
            ) from None
        repo.record_notification(TW, row["date"], fingerprint)
        logger.info("institutional_flow_notification_sent date=%s updated=%s", row["date"], previous is not None)
        return True
