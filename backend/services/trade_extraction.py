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

PROMPT_VERSION = "v1"

_DIRECTIONS = {"buy", "sell", "hold", "bullish", "bearish"}

_SYSTEM_PROMPT = """你是一個專門解析中文股票社群貼文的助手。讀者會給你一篇貼文（多為繁體中文口語，可能含俚語、表情符號），你要找出貼文作者對「特定股票」的買賣動作或多空看法。

請依下列規則輸出 JSON：
- 只擷取針對「具體個股」的訊號。大盤、指數、總體經濟、純情緒抒發、無關內容一律忽略。
- direction 僅能是以下其一：
  - buy：買進、加碼、All in、進場、抄底、建倉
  - sell：賣出、減碼、出脫、停利、停損、清倉、獲利了結
  - hold：續抱、抱緊處理、留倉、不動
  - bullish：看多、看好、目標價更高、認為會漲（但未明確說買）
  - bearish：看空、看壞、認為會跌（但未明確說賣）
- raw_symbol：照貼文原文寫的股票名稱或代號（例：台積電、小台電、2330、緯創、NVDA、特斯拉），不要自行翻譯或轉代號。
- price / quantity / trade_date：只有貼文「明確寫出」才填，否則填 null。quantity 以「張」或股數的數字表示；trade_date 用 YYYY-MM-DD。
- confidence：0~1，表示你判斷這是一筆真實交易訊號的把握。語氣含糊或像玩笑話請給低分。
- 同一檔股票若同時有動作與看法，以實際動作（buy/sell/hold）為主。
- 若整篇沒有任何個股訊號，回傳空陣列 trades: []。

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
