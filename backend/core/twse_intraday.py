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

from core.errors import FetcherError, FetcherParseError
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


def _first_msg(payload: dict, what: str) -> dict:
    arr = payload.get("msgArray") or []
    if not arr:
        raise FetcherParseError(f"TWSE MIS {what}: msgArray 是空的 ({payload!r:.200})")
    return arr[0]


def _from_mis(today: date) -> IntradaySnapshot:
    index_row = _first_msg(
        _get(INDEX_URL, {"ex_ch": "tse_t00.tw", "json": "1", "delay": "0"}),
        "getStockInfo",
    )
    stamp = (index_row.get("d") or "").strip()
    if stamp != today.strftime("%Y%m%d"):
        # 休市日 MIS 仍會回上一個交易日的快照 —— 別把它當成今天。
        raise FetcherParseError(f"TWSE MIS 指數日期 {stamp!r} 不是 {today}")

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
            f"TWSE MIS 成交金額 {turnover:,.1f} 億元 超出合理範圍 —— "
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
                taiex=row["taiex_close"],
                turnover=row["turnover"],
                is_final=True,
            )
    return None


def fetch_snapshot(today: date) -> IntradaySnapshot | None:
    """今天的大盤快照，MIS 優先、FMTQIK 墊底；都沒有當天資料時回 None。"""
    try:
        return _from_mis(today)
    except FetcherError as e:
        # 休市/開盤前是常態，不是故障 —— 記 info 等級，讓 FMTQIK 決定有沒有資料。
        logger.info("mis_intraday_unavailable date=%s err=%s", today, e)
    return _from_fmtqik(today)
