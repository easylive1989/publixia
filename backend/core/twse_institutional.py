"""TWSE BFI82U 每日三大法人買賣金額 helper.

官網報表一次回傳一個交易日，單位是整數「元」。解析依單位名稱而不是列序，
避免證交所調整顯示順序時把法人身份對錯。外資自營商是獨立揭露列，但官方說明
指出它已包含於自營商金額，故不納入合計。
"""
from datetime import date

import requests

from core.errors import FetcherError, FetcherParseError

URL = "https://www.twse.com.tw/rwd/zh/fund/BFI82U"
_HEADERS = {"User-Agent": "Mozilla/5.0 (stock-dashboard institutional sync)"}
# 證交所自 2017-12-18 起才新增「外資自營商」獨立揭露列；在此之前的歷史報表無此項目，預設為 (0, 0)。
_FOREIGN_DEALER_START = date(2017, 12, 18)


def _amount(value: object) -> int:
    try:
        amount = int(str(value).replace(",", "").strip())
    except (TypeError, ValueError) as exc:
        raise FetcherParseError(f"TWSE BFI82U 金額格式錯誤 {value!r}") from exc
    if amount < 0:
        raise FetcherParseError(f"TWSE BFI82U 買賣金額不可為負數 {amount}")
    return amount


def _signed_amount(value: object) -> int:
    try:
        return int(str(value).replace(",", "").strip())
    except (TypeError, ValueError) as exc:
        raise FetcherParseError(f"TWSE BFI82U 差額格式錯誤 {value!r}") from exc


def _row_key(label: str) -> str | None:
    text = label.replace(" ", "")
    if text.startswith("自營商(自行買賣)") or text.startswith("自營商（自行買賣）"):
        return "dealer_proprietary"
    if text.startswith("自營商(避險)") or text.startswith("自營商（避險）"):
        return "dealer_hedge"
    if text == "投信":
        return "trust"
    if text.startswith("外資及陸資"):
        return "foreign"
    if text.startswith("外資自營商"):
        return "foreign_dealer"
    if text == "合計":
        return "total"
    return None


def fetch_day(day: date) -> dict | None:
    """取得一個交易日的 BFI82U 原始金額。

    回傳扁平 dict（date + 各分項 buy/sell，單位元）；官網正常回應「無資料」時
    回傳 ``None``。若回來的日期或欄位結構不符，丟解析錯誤，絕不把別天資料寫入。
    """
    requested = day.strftime("%Y%m%d")
    params = {
        "dayDate": requested,
        "monthDate": "",
        "response": "json",
        "type": "day",
    }
    try:
        response = requests.get(URL, params=params, headers=_HEADERS, timeout=20)
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise FetcherError(f"TWSE BFI82U {day.isoformat()}: {exc}") from exc

    if payload.get("stat") != "OK":
        return None
    if str(payload.get("date")) != requested:
        raise FetcherParseError(
            f"TWSE BFI82U 日期不符 requested={requested} got={payload.get('date')!r}"
        )

    parsed: dict[str, tuple[int, int]] = {}
    for raw in payload.get("data") or []:
        if not isinstance(raw, list) or len(raw) < 4:
            raise FetcherParseError(f"TWSE BFI82U row malformed {raw!r}")
        key = _row_key(str(raw[0]))
        if key is None:
            continue
        buy, sell = _amount(raw[1]), _amount(raw[2])
        difference = _signed_amount(raw[3])
        if buy - sell != difference:
            raise FetcherParseError(
                f"TWSE BFI82U {raw[0]!r} 差額不符 buy={buy} sell={sell} diff={difference}"
            )
        parsed[key] = (buy, sell)

    # 證交所自 2017-12-18 起才新增「外資自營商」獨立揭露列；在此之前無此分項，填 0 補齊。
    if "foreign_dealer" not in parsed and day < _FOREIGN_DEALER_START:
        parsed["foreign_dealer"] = (0, 0)

    required = {
        "dealer_proprietary", "dealer_hedge", "trust", "foreign",
        "foreign_dealer", "total",
    }
    missing = required - parsed.keys()
    if missing:
        raise FetcherParseError(
            f"TWSE BFI82U {day.isoformat()} 缺少分項 {sorted(missing)}"
        )

    row: dict[str, object] = {"date": day.isoformat()}
    for key in sorted(required):
        row[f"{key}_buy"], row[f"{key}_sell"] = parsed[key]
    return row
