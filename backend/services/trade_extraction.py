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

PROMPT_VERSION = "v2"

_DIRECTIONS = {"buy", "sell", "hold", "bullish", "bearish"}

_SYSTEM_PROMPT = """你是一個專門解析中文股票社群貼文的助手。讀者會給你一篇貼文（多為繁體中文口語，可能含俚語、表情符號），你要找出貼文作者對「特定個股」的買賣動作或多空看法。

請依下列規則輸出 JSON：

【只抓具體個股，忽略大盤】
- 只擷取「具體個股或具名 ETF」（如 台積電、緯創、2330、NVDA、00632R）。
- 一律忽略：大盤／加權指數／「台股」「美股」「大盤」「指數」這類整體市場、產業或板塊的籠統說法、原物料、匯率、純情緒抒發、與投資無關的生活內容。
- 不確定是不是真的在講某一檔股票時，寧可不抓。

【方向 direction，僅能下列之一】
  - buy：實際買進、加碼、All in、進場、抄底、建倉
  - sell：實際賣出、減碼、出脫、停利、停損、清倉、獲利了結
  - hold：續抱、抱緊處理、留倉、不動
  - bullish：看多、看好、認為會漲（但未明確說已買）
  - bearish：看空、看壞、認為會跌（但未明確說已賣）

【否定與未發生的動作，不可當成交易】
- 出現否定或尚未發生的字眼——「拒買、不買、沒買、不會買、不碰、避開、空手、觀望、還沒進場、想買但還沒買」——絕對不可輸出 buy 或 sell。
- 例：「拒買國巨」「避開某股」代表她不買、看法偏負面 → 若語氣明確看壞才用 bearish，否則整筆略過；千萬不要記成 buy。
- 「停損」是先前買進後賣出認賠＝sell，不是放空。不要腦補沒寫的動作。

【標的名稱 raw_symbol】
- 照原文寫的正式股票名稱或代號（台積電、小台電、緯創、2330、NVDA），不要自行轉代號。
- 必須是「真的像股票名稱或代號」的字串。不要輸出日期、亂碼、看不懂的代號（如 403A 這種非標準字串）；認不出就略過。
- 不要用她的暱稱（王、渣男、股王…）；若無法對應到某一檔具體個股就略過。

【其他】
- price / quantity / trade_date：只有貼文「明確寫出」才填，否則 null。quantity 以「張」或股數的數字表示；trade_date 用 YYYY-MM-DD。
- confidence：0~1，是你判斷「這是一筆真實個股訊號」的把握。語氣含糊、像玩笑、或不確定是否真的下單 → 給低分（<0.5）。
- 同一檔股票同時有動作與看法時，以實際動作（buy/sell/hold）為主。
- 若整篇沒有任何具體個股訊號，回傳空陣列 trades: []。

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


def extract_trades(content: str) -> list[dict]:
    """Return a list of validated trade dicts for one post (may be empty).

    Invalid rows from the model are dropped rather than failing the post.
    """
    if not content or not content.strip():
        return []
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
