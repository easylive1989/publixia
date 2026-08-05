"""TWSE 盤中大盤快照：加權指數 + 累計成交金額。

收盤後的權威來源是 FMTQIK（``core.twse``），但盤中判讀跑的時候當天還沒有
FMTQIK 資料，所以主要走 MIS 即時行情：

* 加權指數 — ``getStockInfo.jsp?ex_ch=tse_t00.tw``（發行量加權股價指數），
  取 ``msgArray[0]`` 的 ``d``（日期）/``t``（資料時間）/``z``（成交價）
* 累計成交金額 — ``getStatis.jsp?ex=tse``（集中市場成交統計），取 ``detail``
  物件的 ``tz``

MIS 拿不到時（休市、開盤前、或 job 因故延到收盤後才跑）退回 FMTQIK 當月，
撈當天那一列 —— 那已經是定案值，快照會標 ``is_final``。兩邊都沒有就丟例外，
不回 ``None``（見 ``fetch_snapshot``）。

2026-08-05 在 GitHub Actions runner 上對真實 MIS 實測過（沙箱連不到
mis.twse.com.tw），三件跟直覺不一樣、動到這裡就會踩到的事：

1. **``_=<epoch 毫秒>`` 是必要參數，不是快取破壞用的裝飾。** 少了它，
   ``getStatis`` 一律回 ``{"rtcode":"9999","rtmessage":"發生錯誤，請重新整理
   網頁。"}``，補 ``json=1``/``delay=0``/瀏覽器 header 都救不回來；只要補上
   ``_`` 就 ``rtcode=0000``。這支 job 上線後每天推的就是這個 9999。
2. **``getStatis`` 的回應沒有 ``msgArray``**，統計值在 ``detail`` 這個物件底下
   （``getStockInfo`` 才是 ``msgArray``）。
3. **成交金額欄位是 ``tz``（元），不是 ``tm``。** 鄰居 ``tv`` 是成交「張數」。
   實測 tz=1,144,162,599,970 元、tv=13,075,318 張 → 均價 87.5 元/股，而
   ``detail`` 裡各類別金額（``fz`` 一般股票 + ``sz`` ETF + ``cz`` 權證 + …）
   加總也回得到 ``tz``，兩邊都對得起來。

同一次實測還看到：MIS 的 ``tz`` 比當天 FMTQIK 定案值**系統性偏低約 3~4%**
（13:33 的 11,441 億 vs TWSE 大盤統計 11,865 億），因為 MIS 這份統計只算逐筆
交易，FMTQIK 另外含零股、盤後定價與鉅額。判讀吃的是 ln 殘差，這個等比例的
缺口只會讓盤中判讀比收盤後略偏冷一點點；只有一天的觀測，不值得為它硬塞一個
校正係數，但看到盤中與收盤判讀差一級時要想到這裡。

MIS 會擋掉沒有瀏覽器 header 的 client，所以帶 UA + Referer。
"""
import logging
import time
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

# MIS 大盤統計 detail 裡的累計成交金額欄位（元）。缺席時寧可炸掉（訊息會印出
# 實際拿到的 key），也不要拿 tv（成交「張數」）這種鄰居欄位頂替 —— 單位錯掉的
# 判讀比沒有判讀更糟。
_TURNOVER_KEY = "tz"

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
    """MIS GET。``_`` 每次都要帶**當下**的 epoch 毫秒 —— 見模組 docstring 第 1
    點，少了它 getStatis 只會回 rtcode 9999。所以它在這裡統一補、不散落在
    各呼叫點，免得哪天有人「清掉沒用到的參數」又把 job 弄壞。"""
    params = {**params, "_": str(int(time.time() * 1000))}
    try:
        r = requests.get(url, params=params, headers=_HEADERS, timeout=15)
        r.raise_for_status()
        return r.json()
    except (requests.RequestException, ValueError) as e:
        raise FetcherError(f"TWSE MIS {url}: {e}") from e


def _payload(raw, what: str) -> dict:
    """回應本體，形狀不對就丟出「實際拿到什麼」。

    每個假設都要自己驗：payload 可能根本不是物件。
    """
    if not isinstance(raw, dict):
        raise FetcherParseError(
            f"TWSE MIS {what}: 回應不是物件而是 "
            f"{type(raw).__name__}（{raw!r:.200}）"
        )
    return raw


def _first_msg(raw, what: str) -> dict:
    """``msgArray[0]``（``getStockInfo`` 的形狀）。

    訊息裡一定要有 ``rtcode``/``rtmessage`` —— MIS 就是在那兩個欄位講失敗原因
    的（9999 少參數、5004 沒 session…），通報看得到才修得動。
    """
    payload = _payload(raw, what)
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


def _detail(raw, what: str) -> dict:
    """``detail``（``getStatis`` 的形狀 —— 它沒有 ``msgArray``）。"""
    payload = _payload(raw, what)
    detail = payload.get("detail")
    if not isinstance(detail, dict):
        raise FetcherParseError(
            f"TWSE MIS {what}: 沒有 detail 物件（拿到 "
            f"{type(detail).__name__}）rtcode={payload.get('rtcode')!r} "
            f"rtmessage={payload.get('rtmessage')!r} keys={sorted(payload)}"
        )
    return detail


def _from_mis(today: date) -> IntradaySnapshot:
    today_stamp = today.strftime("%Y%m%d")
    index_row = _first_msg(
        _get(INDEX_URL, {"ex_ch": "tse_t00.tw", "json": "1", "delay": "0"}),
        "getStockInfo",
    )
    stamp = (index_row.get("d") or "").strip()
    if stamp != today_stamp:
        # 休市日 MIS 仍會回上一個交易日的快照 —— 別把它當成今天。MIS 有正常
        # 回話、只是資料不是今天的，這是「今天沒有盤」而不是「抓不到」。
        raise MarketClosed(
            f"TWSE MIS 指數資料停在 {stamp!r}，不是 {today} —— 今天沒有盤"
        )

    taiex = _num(index_row.get("z")) or _num(index_row.get("o"))
    if not taiex:
        raise FetcherParseError("TWSE MIS 指數尚未有成交價（開盤前）")

    statis = _detail(_get(STATIS_URL, {"ex": "tse"}), "getStatis")

    # detail.key 形如 "tse_20260805"。指數列已經是今天、統計卻還停在別天，
    # 代表 MIS 兩份資料不同步 —— 拿昨天的金額去外推會得到一個看起來很正常、
    # 其實完全錯的判讀，寧可炸掉。
    statis_key = (statis.get("key") or "").strip()
    if statis_key and not statis_key.endswith(today_stamp):
        raise FetcherParseError(
            f"TWSE MIS 大盤統計停在 {statis_key!r}，指數卻已經是 {today_stamp}"
            " —— 兩份資料不同步"
        )

    amount = _num(statis.get(_TURNOVER_KEY))
    if amount is None:
        raise FetcherParseError(
            f"TWSE MIS 成交金額欄位 {_TURNOVER_KEY!r} 不在 detail 中 "
            f"keys={sorted(statis)}"
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
