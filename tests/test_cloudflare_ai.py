"""Tolerant JSON extraction from Workers AI responses (model-agnostic)."""
import pytest

from core.cloudflare_ai import CloudflareAIError, _extract_json


def test_passthrough_dict():
    assert _extract_json({"trades": []}) == {"trades": []}


def test_bare_json_string():
    assert _extract_json('{"trades": [{"raw_symbol": "2330"}]}') == {
        "trades": [{"raw_symbol": "2330"}]
    }


def test_code_fenced_json():
    text = "好的，分析結果如下：\n```json\n{\"trades\": [{\"raw_symbol\": \"緯創\"}]}\n```\n以上。"
    assert _extract_json(text) == {"trades": [{"raw_symbol": "緯創"}]}


def test_prose_wrapped_json():
    text = '這篇貼文提到 {"trades": [{"raw_symbol": "長榮", "direction": "sell"}]} 就這樣'
    assert _extract_json(text)["trades"][0]["direction"] == "sell"


def test_non_json_raises():
    with pytest.raises(CloudflareAIError):
        _extract_json("這篇貼文沒有任何結構化內容")
