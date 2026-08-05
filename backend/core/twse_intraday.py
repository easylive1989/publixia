"""TWSE 盤中大盤快照：加權指數 + 累計成交金額。

收盤後的權威來源是 FMTQIK（``core.twse``），但盤中判讀跑的時候當天還沒有
FMTQIK 資料，所以主要走 MIS 即時行情：

* 加權指數 — ``getStockInfo.jsp?ex_ch=tse_t00.tw``（發行量加權股價指數）
* 累計成交金額 — ``getStatis.jsp?ex=tse``（集中市場盤中成交統計）

MIS 拿不到時（休市、開盤前、或 job 因故延到收盤後才跑）退回 FMTQIK 當月，
撈當天那一列 —— 那已經是定案值，快照會標 ``is_final``。兩邊都沒有當天資料
就回 ``None``，呼叫端當作「今天沒有盤可判讀」直接跳過。

MIS 會擋掉沒有瀏覽器 header 的 client，所以帶 UA + Referer。
"""
import logging
from dataclasses import dataclass
from datetime import date

import requests

from core.errors import FetcherError, FetcherParseError, MarketClosed
from core.twse import fetch_month

logger = logging.getLogger(__name__)

INDEX_URL = "https://mis.twse.com.tw/stock/api/getStockInfo.jsp"
STATIS_URL = "https://mis.twse.com.tw/stock/api/getStatis.jsp"

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (stock-dashboard intraday heat)",
    "Referer": "https://mis.twse.com.tw/stock/index.jsp",
}

# 成交金額同 FMTQIK 以元計價；UI/模型單位是億元。
_YI = 1e8

# MIS 大盤統計裡的累計成交金額欄位。缺席時寧可炸掉（訊息會印出實際拿到的
# key），也不要拿 tv（成交「量」）之類的鄰居欄位頂替 —— 單位錯掉的判讀比沒有
# 判讀更糟。
_TURNOVER_KEY = "tm"

# 合理的單日成交金額區間（億元）。歷史最大約 1.1 兆元 = 11,469 億，這組界線
# 只擋數量級錯誤（欄位其實是億元、或抓到成交股數），不會誤殺真實行情。
_MIN_YI, _MAX_YI = 10.0, 100_000.0


@dataclass(frozen=True)
class IntradaySnapshot:
    """某一時點的大盤狀態。``turnover`` 是「累計至 ``time``」的成交金額(億元)，
    盤中就是部分金額，需要外推；``is_final`` 為真時已是全日定案值。"""
    date: str      # ISO
    time: str      # HH:MM:SS（MIS 回報的資料時間），FMTQIK 來源為 "收盤"
    taiex: float
    turnover: float
    is_final: bool


def _num(value) -> float | None:
    """MIS 用 ``"-"`` 表示尚無資料，數字帶千分位。無法解讀時回 None。"""
    try:
        return float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def _get(url: str, params: dict) -> dict:
    try:
        r = requests.get(url, params=params, headers=_HEADERS, timeout=15)
        r.raise_for_status()
        return r.json()
    except (requests.RequestException, ValueError) as e:
        raise FetcherError(f"TWSE MIS {url}: {e}") from e


def _first_msg(payload, what: str) -> dict:
    """``msgArray[0]``，形狀不對就丟出「實際拿到什麼」。

    這支端點的回應形狀沒對過真實 session，所以每個假設都要自己驗：payload
    可能根本不是物件。訊息裡一定要有 ``rtcode``/``rtmessage`` —— MIS 就是在
    那兩個欄位講「你沒有 session」的，通報看得到才修得動。
    """
    if not isinstance(payload, dict):
        raise FetcherParseError(
            f"TWSE MIS {what}: 回應不是物件而是 "
            f"{type(payload).__name__}（{payload!r:.200}）"
        )

    arr = payload.get("msgArray") or []
    if not arr:
        raise FetcherParseError(
            f"TWSE MIS {what}: msgArray 是空的 "
            f"rtcode={payload.get('rtcode')!r} "
            f"rtmessage={payload.get('rtmessage')!r} keys={sorted(payload)}"
        )

    row = arr[0]
    if not isinstance(row, dict):
        raise FetcherParseError(
            f"TWSE MIS {what}: msgArray[0] 不是物件（{row!r:.200}）"
        )
    return row


def _from_mis(today: date) -> IntradaySnapshot:
    index_row = _first_msg(
        _get(INDEX_URL, {"ex_ch": "tse_t00.tw", "json": "1", "delay": "0"}),
        "getStockInfo",
    )
    stamp = (index_row.get("d") or "").strip()
    if stamp != today.strftime("%Y%m%d"):
        # 休市日 MIS 仍會回上一個交易日的快照 —— 別把它當成今天。MIS 有正常
        # 回話、只是資料不是今天的，這是「今天沒有盤」而不是「抓不到」。
        raise MarketClosed(
            f"TWSE MIS 指數資料停在 {stamp!r}，不是 {today} —— 今天沒有盤"
        )

    taiex = _num(index_row.get("z")) or _num(index_row.get("o"))
    if not taiex:
        raise FetcherParseError("TWSE MIS 指數尚未有成交價（開盤前）")

    statis_row = _first_msg(_get(STATIS_URL, {"ex": "tse"}), "getStatis")
    amount = _num(statis_row.get(_TURNOVER_KEY))
    if amount is None:
        raise FetcherParseError(
            f"TWSE MIS 成交金額欄位 {_TURNOVER_KEY!r} 不在回應中 "
            f"keys={sorted(statis_row)}"
        )

    turnover = amount / _YI
    if not _MIN_YI <= turnover <= _MAX_YI:
        raise FetcherParseError(
            # 用 %g：欄位單位若差好幾個數量級，%.1f 會把它印成無意義的 0.0
            f"TWSE MIS 成交金額 {turnover:,.6g} 億元 超出合理範圍 —— "
            f"{_TURNOVER_KEY!r} 的單位可能不是元 (raw={amount!r})"
        )

    return IntradaySnapshot(
        date=today.isoformat(),
        time=(index_row.get("t") or "").strip(),
        taiex=taiex,
        turnover=turnover,
        is_final=False,
    )


def _from_fmtqik(today: date) -> IntradaySnapshot | None:
    """收盤後的定案值。當天還沒收盤（或休市）時 FMTQIK 沒有這一列 → None。"""
    for row in fetch_month(today.year, today.month):
        if row["date"] == today.isoformat():
            return IntradaySnapshot(
                date=row["date"],
                time="收盤",
                taiex=row["index_close"],
                turnover=row["turnover"],
                is_final=True,
            )
    return None


def fetch_snapshot(today: date) -> IntradaySnapshot:
    """今天的大盤快照，MIS 優先、FMTQIK 墊底。

    拿不到時一律丟例外、不回 None：回 None 會讓「今天休市」和「MIS 壞掉」
    長得一模一樣，呼叫端就沒辦法決定該安靜跳過還是該吵人。休市丟
    ``MarketClosed``，其餘丟 ``FetcherError`` 且訊息裡帶著 MIS 那邊的實際
    失敗原因 —— 通報就是靠這句話定位的。
    """
    mis_error: FetcherError
    try:
        return _from_mis(today)
    except FetcherError as e:
        mis_error = e
        logger.info("mis_intraday_unavailable date=%s err=%s", today, e)

    try:
        # job 延到收盤後才跑時，FMTQIK 已經有定案值可以救回來。
        final = _from_fmtqik(today)
    except FetcherError as e:
        raise FetcherError(
            f"MIS 取不到 {today} 的盤中快照（{mis_error}），"
            f"FMTQIK 退路也失敗（{e}）"
        ) from e

    if final is not None:
        return final

    if isinstance(mis_error, MarketClosed):
        raise MarketClosed(f"{mis_error}；FMTQIK 當月也沒有 {today} 這一列") from mis_error
    raise FetcherError(
        f"MIS 取不到 {today} 的盤中快照（{mis_error}），FMTQIK 當月也沒有這一列"
    ) from mis_error
