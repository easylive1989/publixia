"""Trade extraction: validation + parsing with a mocked Workers AI call."""
import services.trade_extraction as te


def _fake(response):
    return lambda system, user, json_schema=None, model=None, timeout=60: response


def test_clear_buy(monkeypatch):
    monkeypatch.setattr(te, "run_ai", _fake({"trades": [
        {"raw_symbol": "台積電", "direction": "buy", "confidence": 0.9},
    ]}))
    out = te.extract_trades("今天買進台積電")
    assert out == [{
        "raw_symbol": "台積電", "direction": "buy",
        "price": None, "quantity": None, "trade_date": None, "confidence": 0.9,
    }]


def test_slang_and_price_quantity(monkeypatch):
    monkeypatch.setattr(te, "run_ai", _fake({"trades": [
        {"raw_symbol": "小台電", "direction": "buy", "price": 50.5, "quantity": 3, "confidence": 0.7},
        {"raw_symbol": "2330", "direction": "sell", "price": 1050, "trade_date": "2026-06-03", "confidence": 0.8},
    ]}))
    out = te.extract_trades("小台電加碼，2330 出 @1050")
    assert len(out) == 2
    assert out[0]["quantity"] == 3.0 and out[0]["price"] == 50.5
    assert out[1]["direction"] == "sell" and out[1]["trade_date"] == "2026-06-03"


def test_non_trade_post_returns_empty(monkeypatch):
    monkeypatch.setattr(te, "run_ai", _fake({"trades": []}))
    assert te.extract_trades("今天天氣真好，跟家人出去玩") == []


def test_invalid_direction_dropped(monkeypatch):
    monkeypatch.setattr(te, "run_ai", _fake({"trades": [
        {"raw_symbol": "X", "direction": "invalid", "confidence": 0.5},
        {"raw_symbol": "2330", "direction": "hold", "confidence": 0.6},
    ]}))
    out = te.extract_trades("...")
    assert len(out) == 1 and out[0]["raw_symbol"] == "2330"


def test_blank_content_skips_ai(monkeypatch):
    called = {"n": 0}

    def boom(*a, **k):
        called["n"] += 1
        raise AssertionError("should not call AI")

    monkeypatch.setattr(te, "run_ai", boom)
    assert te.extract_trades("   ") == []
    assert called["n"] == 0


def test_prompt_version_bumped_to_v5():
    assert te.PROMPT_VERSION == "v5"


def test_prompt_excludes_allocation_abstractions():
    # 類別排除規則 + few-shot 反例的關鍵字必須在 system prompt 裡，
    # 避免日後不小心被刪（LLM 行為本身無法確定性 unit-test）。
    prompt = te._SYSTEM_PROMPT
    assert "題材分類" in prompt          # 排除規則
    assert "核心部位" in prompt          # 排除規則列舉
    assert "下半年趨勢題材" in prompt    # few-shot 反例原文
