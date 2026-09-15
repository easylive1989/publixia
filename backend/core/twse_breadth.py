"""TWSE MI_INDEX 每日上市股票市場寬度 helper。

``type=MS`` 只下載大盤統計，不抓數 MB 的逐檔收盤行情。需要的列是
「漲跌證券數合計」，需要的欄是「股票」；括號內漲跌停家數已包含於總家數，
例如 ``207(5)`` 解析為上漲 207 家，不另外加 5。
"""
from datetime import date

import requests

from core.errors import FetcherError, FetcherParseError

URL = "https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX"
_HEADERS = {"User-Agent": "Mozilla/5.0 (stock-dashboard breadth sync)"}


def _count(value: object) -> int:
    try:
        count = int(str(value).split("(", 1)[0].replace(",", "").strip())
    except (TypeError, ValueError) as exc:
        raise FetcherParseError(f"TWSE MI_INDEX 家數格式錯誤 {value!r}") from exc
    if count < 0:
        raise FetcherParseError(f"TWSE MI_INDEX 家數不可為負數 {count}")
    return count


def _breadth_rows(payload: dict) -> list[list]:
    """支援目前的 ``tables`` schema 與舊版 ``data8`` schema。"""
    for table in payload.get("tables") or []:
        fields = [str(field).strip() for field in table.get("fields") or []]
        if fields[:3] == ["類型", "整體市場", "股票"]:
            return table.get("data") or []
    if [str(field).strip() for field in payload.get("fields8") or []][:3] == [
        "類型", "整體市場", "股票",
    ]:
        return payload.get("data8") or []
    raise FetcherParseError("TWSE MI_INDEX 找不到漲跌證券數合計表")


def parse_payload(payload: dict, requested: str) -> dict | None:
    if payload.get("stat") != "OK":
        return None
    if str(payload.get("date")) != requested:
        raise FetcherParseError(
            f"TWSE MI_INDEX 日期不符 requested={requested} "
            f"got={payload.get('date')!r}"
        )

    counts: dict[str, int] = {}
    for raw in _breadth_rows(payload):
        if not isinstance(raw, list) or len(raw) < 3:
            raise FetcherParseError(f"TWSE MI_INDEX row malformed {raw!r}")
        label = str(raw[0]).split("(", 1)[0].strip()
        if label == "上漲":
            counts["advancing"] = _count(raw[2])
        elif label == "下跌":
            counts["declining"] = _count(raw[2])
        elif label == "持平":
            counts["unchanged"] = _count(raw[2])

    required = {"advancing", "declining", "unchanged"}
    if counts.keys() < required:
        raise FetcherParseError(
            f"TWSE MI_INDEX 缺少市場寬度欄位 {sorted(required - counts.keys())}"
        )
    if sum(counts.values()) == 0:
        raise FetcherParseError("TWSE MI_INDEX 市場寬度合計為 0")
    return {
        "date": f"{requested[:4]}-{requested[4:6]}-{requested[6:]}",
        **counts,
    }


def fetch_day(day: date) -> dict | None:
    requested = day.strftime("%Y%m%d")
    params = {"date": requested, "type": "MS", "response": "json"}
    try:
        response = requests.get(URL, params=params, headers=_HEADERS, timeout=20)
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise FetcherError(f"TWSE MI_INDEX {day.isoformat()}: {exc}") from exc
    return parse_payload(payload, requested)
