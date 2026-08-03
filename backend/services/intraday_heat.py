"""盤中大盤冷熱判讀 → Discord。

``market_volume_sync`` 收盤後（16:00）抓的才是定案值；這支在盤中（預設 13:00，
離 13:30 收盤還有半小時）先抓一次 MIS 即時快照，把「已成交的部分金額」線性
外推成全日估計，丟進既有的 ``market_heat`` 迴歸模型算出當下判讀，推 Discord。

刻意 **不寫入** ``market_volume_daily``：估計值一旦落地，前端在收盤資料回補前
會把它當成定案數字顯示，圖表也會多一根假的長條。判讀在這裡算完只進 Discord。
"""
import logging
from datetime import date, datetime, time as dtime

import pytz

from core.discord import send_to_discord
from core.settings import settings
from core.twse_intraday import IntradaySnapshot, fetch_snapshot
from repositories import market_volume as repo
from services.market_heat import compute_heat

logger = logging.getLogger(__name__)

TST = pytz.timezone("Asia/Taipei")

SESSION_OPEN = dtime(9, 0)
SESSION_CLOSE = dtime(13, 30)
SESSION_MINUTES = 270  # 09:00–13:30

_EMOJI = {
    "very_cold": "🧊",
    "cold": "🔵",
    "normal": "⚪",
    "hot": "🟠",
    "very_hot": "🔥",
}


def _minutes(t: dtime) -> int:
    return t.hour * 60 + t.minute


def extrapolate_turnover(partial: float, at: dtime) -> float:
    """把截至 ``at`` 的累計成交金額線性外推成全日估計。

    成交量在開盤與尾盤兩端偏重，所以線性外推不是無偏的；13:00 已經走完
    4/4.5 場（×1.125），剩下的權重小，誤差在判讀等級上通常吃得下 —— 但它終究
    是估計值，Discord 訊息會標明，收盤後 16:00 的 sync 會用實際金額重算。
    """
    elapsed = _minutes(at) - _minutes(SESSION_OPEN)
    elapsed = max(1, min(elapsed, SESSION_MINUTES))
    return partial * SESSION_MINUTES / elapsed


def _snapshot_time(snapshot: IntradaySnapshot) -> dtime:
    """MIS 的 ``HH:MM:SS`` 資料時間；解不出來就當作收盤（不外推）。"""
    parts = snapshot.time.split(":")
    try:
        return dtime(int(parts[0]), int(parts[1]))
    except (IndexError, ValueError):
        return SESSION_CLOSE


def build_reading(snapshot: IntradaySnapshot) -> dict | None:
    """快照 → 判讀。歷史不足以迴歸時回 None。"""
    at = _snapshot_time(snapshot)
    estimated = (
        snapshot.turnover
        if snapshot.is_final
        else extrapolate_turnover(snapshot.turnover, at)
    )

    # 今天若已經有列（收盤 sync 跑過了）就換掉，別讓同一天出現兩列。
    rows = [r for r in repo.list_days() if r["date"] < snapshot.date]
    rows.append({
        "date": snapshot.date,
        "taiex_close": snapshot.taiex,
        "turnover": estimated,
    })

    heat = compute_heat(rows)
    if not heat:
        return None
    return {
        "today": heat[-1],
        "prev": heat[-2] if len(heat) > 1 else None,
        "partial_turnover": snapshot.turnover,
        "at": at.strftime("%H:%M"),
        "is_final": snapshot.is_final,
    }


def _yi(n: float) -> str:
    return f"{round(n):,}"


def format_message(reading: dict) -> str:
    today = reading["today"]
    prev = reading["prev"]
    header = "收盤定案" if reading["is_final"] else f"盤中 {reading['at']} 估計"

    lines = [
        f"📊 **大盤成交金額冷熱判讀（{header}）**　{today['date']}",
        "",
        f"{_EMOJI.get(today['level'], '')} **{today['label']}**"
        f"（近一年百分位 PR {round(today['percentile'] * 100)}）",
        f"加權指數　{today['taiex_close']:,.2f}",
    ]
    if reading["is_final"]:
        lines.append(f"成交金額　{_yi(today['turnover'])} 億")
    else:
        lines.append(
            f"成交金額　盤中累計 {_yi(reading['partial_turnover'])} 億"
            f" → 全日估計 {_yi(today['turnover'])} 億"
        )
    lines.append(
        f"位階常態　{_yi(today['expected_turnover'])} 億"
        f"（量能比 {today['volume_ratio']:.2f}）"
    )
    if prev:
        lines.append(
            f"前一交易日　{prev['label']}（PR {round(prev['percentile'] * 100)}）"
        )
    if not reading["is_final"]:
        lines += ["", "※ 盤中線性外推估計，收盤後會以實際成交金額重算"]
    return "\n".join(lines)


def _webhook() -> str | None:
    url = settings.discord_market_webhook_url or settings.discord_stock_webhook_url
    return url.get_secret_value() if url else None


def run_intraday_heat_signal(today: date | None = None) -> dict:
    """Scheduler entry point（每個交易日盤中跑一次）。

    休市、開盤前、或今天還沒有任何成交資料時安靜跳過 —— 不推 Discord、也不
    算失敗。Discord 送不出去才是真的錯誤，讓它往上拋給 scheduler 記 error。
    """
    today = today or datetime.now(TST).date()

    snapshot = fetch_snapshot(today)
    if snapshot is None:
        logger.info("intraday_heat_skipped reason=no_snapshot date=%s", today)
        return {"sent": False, "reason": "no_snapshot"}

    reading = build_reading(snapshot)
    if reading is None:
        logger.warning("intraday_heat_skipped reason=insufficient_history date=%s", today)
        return {"sent": False, "reason": "insufficient_history"}

    webhook = _webhook()
    if not webhook:
        logger.warning("intraday_heat_skipped reason=no_webhook date=%s", today)
        return {"sent": False, "reason": "no_webhook"}

    send_to_discord(webhook, {"content": format_message(reading)})
    result = {
        "sent": True,
        "level": reading["today"]["level"],
        "percentile": reading["today"]["percentile"],
        "is_final": reading["is_final"],
    }
    logger.info("intraday_heat_sent %s", result)
    return result
