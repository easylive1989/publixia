"""Nasdaq Composite 日線（指數收盤 + composite volume）helper.

美股這一側配的是 **Nasdaq Composite 指數 ＋ Nasdaq 上市股票的 composite
volume**。挑這一組是因為指數與量能來自同一個宇宙（Nasdaq 上市股票）—— 美股
的成交量是碎的（NYSE / Nasdaq / Cboe / IEX 再加上約四成 off-exchange），
「全市場成交量」不是一個現成數字，拿 S&P 500 去配全市場量等於在比兩個不同
的東西，迴歸從第一步就錯了。

## 為什麼是成交股數，不是成交金額

美股沒有免費且穩定的「全市場成交金額」日資料源，而 composite volume 在美股
語境裡本來就是指股數。這對判讀的影響比直覺小：

    ln(成交金額) ≈ ln(成交股數) + ln(成交均價)

而成交均價大致隨指數等比例走，所以把 ln(量) 對 ln(指數) 做迴歸時，用股數只是
把擬合斜率整體平移約 1（台股成交金額對指數的彈性 ≈ 1.6，換成股數就 ≈ 0.6），
**殘差 —— 也就是判讀真正吃的東西 —— 幾乎不變**。差別只在圖上那條位階常態的
斜度，以及「均價 ∝ 指數」這個近似隨新上市/成分調整而慢慢失準的部分。

## 資料源

Yahoo Finance 的 chart endpoint（`^IXIC`）。免金鑰、一次要得到整段歷史（不像
FMTQIK 得一個月一個請求），daily bar 直接帶 close 與 volume。

**這個 endpoint 沒有在本環境實測過**（沙箱的網路政策把 finance 類 host 全擋
了，連現有的 TWSE 都連不到），所以照 `core/twse_intraday.py` 的作法：任何一步
對不上就 raise，訊息裡帶實際看到的 key / 長度 / 數值，讓失敗理由能一路傳到
Discord 通報。第一次上線要看的就是這裡 —— Yahoo 擋人時會回 401/429 或空的
`chart.result`，兩種都會在下面炸出可讀的訊息。
"""
import logging
from datetime import date, datetime, timedelta, timezone

import requests

from core.errors import FetcherError, FetcherParseError

logger = logging.getLogger(__name__)

URL = "https://query1.finance.yahoo.com/v8/finance/chart/%5EIXIC"
_HEADERS = {"User-Agent": "Mozilla/5.0 (stock-dashboard nasdaq sync)"}

# 成交股數以「億股」存，跟台股的億元對齊 —— 圖表刻度才不會是 10 位數。
_YI = 1e8

# 合理區間（億股）。Nasdaq composite 日成交股數 2016 年約 15–20 億股，2021 之後
# 常態 40–90 億股，恐慌日上看 200 億股。範圍抓寬是因為這道關卡要擋的不是「今天
# 量特別大」而是「單位錯了」：真的收到成交金額（~1e11 美元）會落在 1000 億以上。
_MIN_VOLUME_YI = 1.0
_MAX_VOLUME_YI = 1_000.0

# Nasdaq Composite 2016 年約 4,200 點。同樣只擋明顯不是指數的值。
_MIN_INDEX = 100.0
_MAX_INDEX = 1_000_000.0


def _iso(ts: int) -> str:
    """Yahoo 的 daily bar timestamp → ISO 交易日。

    日線的 timestamp 是當天開盤（09:30 ET = 13:30/14:30 UTC），不論夏令與否都
    落在同一個 UTC 日期，所以直接取 UTC date 就是交易日。
    """
    return datetime.fromtimestamp(ts, tz=timezone.utc).date().isoformat()


def fetch_range(start: date, end: date) -> list[dict]:
    """抓 ``start``–``end``（含頭含尾）的每日 Nasdaq Composite 收盤與成交股數。

    回傳 ``[{date, index_close, turnover}, ...]``（turnover 單位億股，日期遞增）。

    區間內一個交易日都解不出來就 raise —— 呼叫端保證請求區間至少橫跨 10 個
    日曆天，美股不存在連續 10 天全休市，所以「什麼都沒有」只可能是資料源壞了。
    """
    params = {
        "period1": int(datetime(start.year, start.month, start.day, tzinfo=timezone.utc).timestamp()),
        # period2 是開區間，往後推一天才含得到 end 當天。
        "period2": int(
            (datetime(end.year, end.month, end.day, tzinfo=timezone.utc) + timedelta(days=1)).timestamp()
        ),
        "interval": "1d",
    }
    try:
        r = requests.get(URL, params=params, headers=_HEADERS, timeout=30)
        r.raise_for_status()
        payload = r.json()
    except (requests.RequestException, ValueError) as e:
        raise FetcherError(f"Yahoo ^IXIC {start}~{end}: {e}") from e

    chart = payload.get("chart") or {}
    results = chart.get("result") or []
    if not results:
        raise FetcherParseError(
            f"Yahoo ^IXIC {start}~{end} 沒有 chart.result —— "
            f"chart.error={chart.get('error')!r}，payload keys={sorted(payload)}。"
            "Yahoo 擋人（401/429）或改了回應格式時會長這樣"
        )

    result = results[0]
    stamps = result.get("timestamp") or []
    quotes = (result.get("indicators") or {}).get("quote") or [{}]
    quote = quotes[0] or {}
    closes = quote.get("close")
    volumes = quote.get("volume")
    if closes is None or volumes is None:
        raise FetcherParseError(
            f"Yahoo ^IXIC {start}~{end} 的 quote 少了 close/volume —— "
            f"quote keys={sorted(quote)}，timestamp {len(stamps)} 筆"
        )
    if not len(stamps) == len(closes) == len(volumes):
        raise FetcherParseError(
            f"Yahoo ^IXIC {start}~{end} 陣列長度對不上 —— "
            f"timestamp={len(stamps)} close={len(closes)} volume={len(volumes)}"
        )

    rows: list[dict] = []
    for ts, close, volume in zip(stamps, closes, volumes):
        # Yahoo 對半日盤/資料缺漏的日子會塞 null，那不是故障，跳過就好；
        # 整段都是 null 才是問題，由下面的空值檢查處理。
        if close is None or not volume:
            continue
        turnover = volume / _YI
        if not _MIN_VOLUME_YI <= turnover <= _MAX_VOLUME_YI:
            raise FetcherParseError(
                f"Yahoo ^IXIC {_iso(ts)} 成交股數 {turnover:,.1f} 億股 不在合理區間 "
                f"[{_MIN_VOLUME_YI:,.0f}, {_MAX_VOLUME_YI:,.0f}] —— 原始值 {volume!r}，"
                "單位或欄位可能變了"
            )
        if not _MIN_INDEX <= close <= _MAX_INDEX:
            raise FetcherParseError(
                f"Yahoo ^IXIC {_iso(ts)} 指數收盤 {close!r} 不在合理區間 "
                f"[{_MIN_INDEX:,.0f}, {_MAX_INDEX:,.0f}]"
            )
        rows.append({
            "date": _iso(ts),
            "index_close": float(close),
            "turnover": turnover,
        })

    if not rows:
        raise FetcherParseError(
            f"Yahoo ^IXIC {start}~{end} 解不出任何交易日 —— "
            f"timestamp {len(stamps)} 筆，close/volume 全為 null"
        )
    rows.sort(key=lambda r: r["date"])
    logger.info("nasdaq_fetched start=%s end=%s rows=%d", start, end, len(rows))
    return rows
