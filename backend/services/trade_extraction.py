"""Extract buy/sell signals from a post via Cloudflare Workers AI.

The hard part is Traditional-Chinese colloquial trading talk: 加碼/減碼/出脫/
存股/All in/空/翻多/抱緊處理/停利/停損, stock nicknames (小台電, 護國神山), and
mixing opinions with actual trades. The prompt asks for both real trades
(buy/sell/hold) and directional opinions (bullish/bearish), with price /
quantity / date only when explicitly stated.
"""
import logging

from pydantic import BaseModel, ValidationError, field_validator

from core.cloudflare_ai import run_ai

logger = logging.getLogger(__name__)

PROMPT_VERSION = "v5"

_DIRECTIONS = {"buy", "sell", "hold", "bullish", "bearish"}

_SYSTEM_PROMPT = """你是一個專門解析中文股票社群貼文的助手。讀者會給你一篇貼文（多為繁體中文口語，可能含俚語、表情符號），你要找出貼文作者對「特定個股」的買賣動作或多空看法。

請依下列規則輸出 JSON：

【抓取範圍】
- 抓「具體個股或具名 ETF」（台積電、緯創、2330、NVDA、00632R）。
- 大盤也要抓：當作者談「台股、大盤、加權、加權指數、指數」整體走勢或對大盤的多空／操作時，raw_symbol 照原文填「台股」或「大盤」（系統會對應到加權指數，用點數算成效）。
- 一律忽略：個別產業／板塊的籠統說法、原物料、匯率、純情緒抒發、與投資無關的生活內容。美股大盤（道瓊、那斯達克、S&P）目前先略過。
- 一律忽略「投資組合配置／選股策略／題材分類」這類抽象說法——動能、價值股、成長股、趨勢題材、某某題材、核心部位、衛星部位、現金部位、存股部位等，都不是具名個股。即使句中對它們有買賣動作（砍掉動能部位、布局趨勢題材、核心部位續抱），也不可當成交易；raw_symbol 必須能對應到某一檔具體個股／ETF。
- 不確定是不是在講某一檔具體標的或大盤時，寧可不抓。

【方向 direction，僅能下列之一】
  - buy：實際買進、加碼、All in、進場、抄底、建倉
  - sell：實際賣出、減碼、出脫、停利、停損、清倉、獲利了結
  - hold：續抱、抱緊處理、留倉、不動
  - bullish：看多、看好、認為會漲（但未明確說已買）
  - bearish：看空、看壞、認為會跌（但未明確說已賣）

【區分「實際動作」與「否定／未發生」——這段最重要】
- **已經發生的動作一定要抓**：買了、賣了、加碼、減碼、停利、停損、全數售出、清倉、續抱。即使同一句也提到未來計畫（如「預計轉投其他個股」「之後有買賣會通知大家」），那筆「已發生的動作」仍要照實記錄，不可因為有未來語句就略過。
- **只有當作者對某檔『根本沒有實際買賣』時才不要記 buy/sell**：出現「拒買、不買、沒買、不會買、不碰、避開、空手、還在觀望、想買但還沒買」等＝沒有動作——不可記成 buy/sell；若語氣明確看壞可用 bearish，否則該檔略過。例：「拒買國巨」→ 不可記成 buy。
- 「停損」是先前買進後賣出認賠＝sell，不是放空。不要腦補貼文沒明寫的動作。

【標的名稱 raw_symbol】
- 照原文寫的正式股票名稱或代號（台積電、小台電、緯創、2330、NVDA），不要自行轉代號。
- 必須是「真的像股票名稱或代號」的字串。不要輸出日期、亂碼、看不懂的代號（如 403A 這種非標準字串）；認不出就略過。
- 不要用她的暱稱（王、渣男、股王…）；若無法對應到某一檔具體個股就略過。

【其他】
- price / quantity / trade_date：只有貼文「明確寫出」才填，否則 null。quantity 以「張」或股數的數字表示；trade_date 用 YYYY-MM-DD。
- confidence：0~1，是你判斷「這是一筆真實個股訊號」的把握。語氣含糊、像玩笑、或不確定是否真的下單 → 給低分（<0.5）。
- 同一檔股票同時有動作與看法時，以實際動作（buy/sell/hold）為主。
- 若整篇沒有任何具體個股訊號，回傳空陣列 trades: []。

【範例】（務必照這些模式判斷，尤其是「已完成動作＋未來語句」）
貼文：「家父持股之一，長榮海運已全數賣出，預計轉投其他個股，有任何買賣動作會馬上通知大家。」
輸出：{"trades":[{"raw_symbol":"長榮海運","direction":"sell","confidence":0.9}]}
（「已全數賣出」是已發生的賣出，後面的「預計轉投／會通知」是未來語句，不影響這筆 sell）

貼文：「早盤重大訊息！家父重新買回緯創，看來是改變心意了。」
輸出：{"trades":[{"raw_symbol":"緯創","direction":"buy","confidence":0.9}]}

貼文：「盤中緯創持續漲停，家父已售出絕大部分，僅留一張。」
輸出：{"trades":[{"raw_symbol":"緯創","direction":"sell","quantity":1,"confidence":0.85}]}

貼文：「早盤台股再創新高，已經沒有人可以阻擋台股的漲勢，家父看多。」
輸出：{"trades":[{"raw_symbol":"台股","direction":"bullish","confidence":0.7}]}

貼文：「大叔本人多年來因為董事長品德原因，一直拒買國巨的股票。」
輸出：{"trades":[]}
（「拒買」＝沒有實際買賣，不可記成 buy）

貼文：「我的做法是把前陣子追動能的部位砍掉，剛好有現金可以逢低布局下半年趨勢題材，核心部位就是Hold&Hold。」
輸出：{"trades":[]}
（動能／下半年趨勢題材／核心部位是配置與題材分類的抽象說法，不是具名個股，即使有砍掉／布局／Hold 動作也不抓）

只輸出符合 schema 的 JSON，不要額外解釋。"""

_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "trades": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "raw_symbol": {"type": "string"},
                    "direction": {
                        "type": "string",
                        "enum": ["buy", "sell", "hold", "bullish", "bearish"],
                    },
                    "price": {"type": ["number", "null"]},
                    "quantity": {"type": ["number", "null"]},
                    "trade_date": {"type": ["string", "null"]},
                    "confidence": {"type": "number"},
                },
                "required": ["raw_symbol", "direction", "confidence"],
            },
        }
    },
    "required": ["trades"],
}


class _Trade(BaseModel):
    raw_symbol: str
    direction: str
    price: float | None = None
    quantity: float | None = None
    trade_date: str | None = None
    confidence: float = 0.0

    @field_validator("raw_symbol")
    @classmethod
    def _strip(cls, v: str) -> str:
        return (v or "").strip()

    @field_validator("direction")
    @classmethod
    def _dir(cls, v: str) -> str:
        v = (v or "").strip().lower()
        if v not in _DIRECTIONS:
            raise ValueError(f"bad direction {v!r}")
        return v


# Podcast transcripts can run to tens of thousands of characters — past the
# model's context window and well into the range where quality degrades. So we
# extract long content in overlapping windows and merge the results. Short
# posts (Threads) stay on the single-call path unchanged.
_CHUNK_THRESHOLD = 6000
_CHUNK_SIZE = 4000
_CHUNK_OVERLAP = 200


def _split(content: str) -> list[str]:
    """Overlapping windows over long content. The overlap avoids dropping a
    trade that straddles a window boundary (it just gets deduped on merge)."""
    step = _CHUNK_SIZE - _CHUNK_OVERLAP
    return [content[i:i + _CHUNK_SIZE] for i in range(0, len(content), step)]


def _extract_one(content: str) -> list[dict]:
    """Run the model once over one piece of text and return validated trades."""
    raw = run_ai(_SYSTEM_PROMPT, content, json_schema=_JSON_SCHEMA)
    items = raw.get("trades", []) if isinstance(raw, dict) else []
    out: list[dict] = []
    for item in items:
        try:
            trade = _Trade(**item)
        except (ValidationError, TypeError):
            logger.warning("dropping invalid trade item=%s", item)
            continue
        if not trade.raw_symbol:
            continue
        out.append(trade.model_dump())
    return out


def _merge(trades: list[dict]) -> list[dict]:
    """Dedupe on ``(raw_symbol, direction)`` — the same key the DB enforces —
    keeping the highest-confidence occurrence of each."""
    best: dict[tuple[str, str], dict] = {}
    for t in trades:
        key = (t["raw_symbol"], t["direction"])
        if key not in best or t["confidence"] > best[key]["confidence"]:
            best[key] = t
    return list(best.values())


def extract_trades(content: str) -> list[dict]:
    """Return a list of validated trade dicts for one post (may be empty).

    Invalid rows from the model are dropped rather than failing the post. Long
    content is extracted in overlapping windows and merged; short content makes
    a single model call.
    """
    if not content or not content.strip():
        return []
    if len(content) <= _CHUNK_THRESHOLD:
        return _extract_one(content)
    all_trades: list[dict] = []
    for window in _split(content):
        all_trades.extend(_extract_one(window))
    return _merge(all_trades)
