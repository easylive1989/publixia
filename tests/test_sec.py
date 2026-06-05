"""SEC company_tickers.json fetch helper."""
import core.sec as sec


class _Resp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def test_fetch_company_tickers_flattens_and_sets_user_agent(monkeypatch):
    captured = {}

    def _fake_get(url, headers=None, timeout=None):
        captured["url"] = url
        captured["headers"] = headers or {}
        return _Resp({
            "0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."},
            "1": {"cik_str": 50863, "ticker": "INTC", "title": "Intel Corp."},
        })

    monkeypatch.setattr(sec.requests, "get", _fake_get)

    rows = sec.fetch_company_tickers()

    # SEC 的 fair-access 政策要求帶 User-Agent，否則 403
    assert "User-Agent" in captured["headers"]
    assert {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."} in rows
    assert len(rows) == 2
