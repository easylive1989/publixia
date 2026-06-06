"""Long-transcript extraction: chunk + merge; short content stays single-call."""
import services.trade_extraction as te


def test_short_content_is_single_call(monkeypatch):
    calls = {"n": 0}

    def fake(system, user, json_schema=None, model=None, timeout=60):
        calls["n"] += 1
        return {"trades": [{"raw_symbol": "台積電", "direction": "buy", "confidence": 0.9}]}

    monkeypatch.setattr(te, "run_ai", fake)
    out = te.extract_trades("今天買進台積電")
    assert calls["n"] == 1
    assert len(out) == 1


def test_long_content_is_chunked_and_merged(monkeypatch):
    # Long transcript → multiple windows. Return a different trade per window,
    # plus a duplicate (different confidence) to exercise the merge.
    responses = [
        {"trades": [{"raw_symbol": "台積電", "direction": "buy", "confidence": 0.6}]},
        {"trades": [{"raw_symbol": "聯發科", "direction": "bullish", "confidence": 0.8}]},
        {"trades": [{"raw_symbol": "台積電", "direction": "buy", "confidence": 0.95}]},  # dup, higher conf
        {"trades": [{"raw_symbol": "長榮", "direction": "sell", "confidence": 0.7}]},
    ]
    calls = {"n": 0}

    def fake(system, user, json_schema=None, model=None, timeout=60):
        i = min(calls["n"], len(responses) - 1)
        calls["n"] += 1
        return responses[i]

    monkeypatch.setattr(te, "run_ai", fake)

    long_text = "股票討論。" * 3000  # 15000 chars → 4 windows
    out = te.extract_trades(long_text)

    assert calls["n"] > 1  # actually chunked

    by_key = {(t["raw_symbol"], t["direction"]): t for t in out}
    #台積電/buy deduped to the higher-confidence occurrence
    assert by_key[("台積電", "buy")]["confidence"] == 0.95
    # distinct trades preserved
    assert ("聯發科", "bullish") in by_key
    assert ("長榮", "sell") in by_key
    # no duplicate rows
    assert len(out) == len(by_key)


def test_split_windows_overlap():
    content = "abcdefghij" * 1000  # 10000 chars
    windows = te._split(content)
    assert len(windows) > 1
    # reassembling the non-overlapped step covers the whole input
    assert windows[0].startswith("abc")
    # overlap: end of window 0 reappears at start of window 1
    step = te._CHUNK_SIZE - te._CHUNK_OVERLAP
    assert content[step:step + 10] == windows[1][:10]
