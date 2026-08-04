"""維運通報：排程或抓取一出事就推 Discord，訊息裡直接寫清楚出了什麼事。

為什麼要有這支：判讀類的 job 一天只跑一次，靜默跳過跟成功長得一模一樣 ——
壞掉可以壞好幾天沒人發現（盤中判讀第一次上線那天就是這樣沒聲沒息）。所以
規則改成：**任何一條沒有推出判讀的路徑都要留下 Discord 痕跡**，而且訊息要
帶上「哪支 job、哪一步、拿到什麼、例外是什麼」，能照著訊息直接去修。

Webhook 取用順序：``DISCORD_OPS_WEBHOOK_URL`` → ``DISCORD_MARKET_WEBHOOK_URL``
→ ``DISCORD_STOCK_WEBHOOK_URL``。想把維運噪音跟判讀分頻道就設第一支；沒設也
不會靜音，只是跟判讀擠同一個頻道 —— 吵一點永遠好過沒聲音。

``send_alert`` 自己絕不往外丟例外：通報掛掉不能反過來蓋掉原本的錯誤。
"""
import logging
import traceback

from core.discord import send_to_discord
from core.errors import StockDashboardError
from core.settings import settings

logger = logging.getLogger(__name__)

_ICON = {"error": "🚨", "warning": "⚠️", "info": "ℹ️"}

# Discord 單則上限 2000 字，留餘裕給截斷標記。
_MAX_CONTENT = 1900
_MAX_TRACEBACK = 700
_TRUNCATED = "\n…（訊息過長已截斷，完整內容見 journalctl -u stock-dashboard）"


def _webhook() -> str | None:
    """第一個真的有值的 webhook。

    空字串要當成沒設定 —— deploy 時 GitHub Actions 會把未設定的 secret 寫成
    ``DISCORD_OPS_WEBHOOK_URL=``，pydantic 收到的是 ``SecretStr('')`` 而不是
    ``None``，直接拿去 POST 只會得到一個看不懂的 4xx。
    """
    for candidate in (
        settings.discord_ops_webhook_url,
        settings.discord_market_webhook_url,
        settings.discord_stock_webhook_url,
    ):
        url = candidate.get_secret_value().strip() if candidate else ""
        if url:
            return url
    return None


def _traceback_tail(error: BaseException) -> str | None:
    """非預期例外才附 traceback。

    領域例外（``StockDashboardError`` 家族）的訊息本身就把該講的講完了，
    再貼一份 traceback 只會把重點推出畫面外。
    """
    if isinstance(error, StockDashboardError):
        return None
    text = "".join(
        traceback.format_exception(type(error), error, error.__traceback__)
    )
    return text[-_MAX_TRACEBACK:]


def format_alert(
    title: str,
    *,
    fields: dict | None = None,
    error: BaseException | None = None,
    level: str = "error",
) -> str:
    lines = [f"{_ICON.get(level, _ICON['error'])} **{title}**"]

    if error is not None:
        lines.append(f"`{type(error).__name__}: {error}`")
        cause = error.__cause__
        # 外層訊息常常已經把原因整句包進去了（fetch_snapshot 就是這樣做的），
        # 那時再貼一次只是把有用的欄位擠出畫面。
        if cause is not None and cause is not error and str(cause) not in str(error):
            lines.append(f"起因　`{type(cause).__name__}: {cause}`")

    for key, value in (fields or {}).items():
        lines.append(f"・{key}　{value}")

    if error is not None:
        tail = _traceback_tail(error)
        if tail:
            lines.append(f"```\n{tail}\n```")

    content = "\n".join(lines)
    if len(content) > _MAX_CONTENT:
        content = content[: _MAX_CONTENT - len(_TRUNCATED)] + _TRUNCATED
    return content


def send_alert(
    title: str,
    *,
    fields: dict | None = None,
    error: BaseException | None = None,
    level: str = "error",
) -> bool:
    """推一則維運通報到 Discord。回傳是否真的送出去了。"""
    content = format_alert(title, fields=fields, error=error, level=level)

    webhook = _webhook()
    if not webhook:
        # 連通報都推不出去時，至少把整則內容留在 journal 裡。
        logger.error(
            "alert_undeliverable_no_webhook title=%s content=%s", title, content
        )
        return False

    try:
        send_to_discord(webhook, {"content": content})
    except Exception:
        logger.exception("alert_send_failed title=%s content=%s", title, content)
        return False

    logger.info("alert_sent level=%s title=%s", level, title)
    return True
