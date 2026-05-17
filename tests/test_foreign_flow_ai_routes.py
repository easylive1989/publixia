"""End-to-end tests for /api/futures/tw/foreign-flow/ai-report and the
companion /markdown endpoint that the Cloudflare Worker calls.

Worker endpoints stay X-Worker-Token-gated (shared deploy-time secret).
Browser endpoints became public after the user/permission purge.
"""
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

import pytz
from fastapi.testclient import TestClient
from pydantic import SecretStr

from main import app
from core.settings import settings
from repositories.foreign_flow_ai import get_report, save_report
from repositories.futures import save_futures_daily_rows
from repositories.institutional_futures import save_institutional_futures_rows
from repositories.large_trader import save_large_trader_rows


client = TestClient(app)

WORKER_TOKEN = "test-worker-token-abcdef"

_TST = pytz.timezone("Asia/Taipei")


def _seed_minimum():
    """Seed enough rows for the /markdown route to return 200.

    The latest TX row is anchored to today's Taipei date so the
    non-trading-day check in /markdown doesn't 204 us.
    """
    today = datetime.now(_TST).date()
    yesterday = today - timedelta(days=1)
    d0 = yesterday.strftime("%Y-%m-%d")
    d1 = today.strftime("%Y-%m-%d")
    save_futures_daily_rows([
        {"symbol": "TX", "date": d0, "contract_date": "202505",
         "open": 17000, "high": 17100, "low": 16900, "close": 17000,
         "volume": 1, "open_interest": 1, "settlement": 17000},
        {"symbol": "TX", "date": d1, "contract_date": "202505",
         "open": 17000, "high": 17200, "low": 16950, "close": 17150,
         "volume": 1, "open_interest": 1, "settlement": 17150},
    ])
    save_institutional_futures_rows([
        {"symbol": "TX", "date": d0,
         "foreign_long_oi": 100, "foreign_short_oi": 0,
         "foreign_long_amount": 320_000.0, "foreign_short_amount": 0.0},
        {"symbol": "TX", "date": d1,
         "foreign_long_oi": 130, "foreign_short_oi": 0,
         "foreign_long_amount": 419_500.0, "foreign_short_amount": 0.0},
    ])
    save_large_trader_rows([
        {"date": d0, "market_oi": 100_000,
         "top5_long_oi": 0, "top5_short_oi": 0,
         "top10_long_oi": 60_000, "top10_short_oi": 70_000},
        {"date": d1, "market_oi": 100_000,
         "top5_long_oi": 0, "top5_short_oi": 0,
         "top10_long_oi": 65_000, "top10_short_oi": 60_000},
    ])


def _configure_worker_token(token: str | None = WORKER_TOKEN):
    settings.foreign_flow_worker_token = (
        SecretStr(token) if token is not None else None
    )


def _configure_worker_url(url: str | None = "http://worker.test/"):
    settings.foreign_flow_worker_url = url


# ── /markdown (Worker → Backend) ───────────────────────────────────────


def test_markdown_missing_worker_token_setting_returns_503():
    _configure_worker_token(None)
    _seed_minimum()
    r = client.get("/api/futures/tw/foreign-flow/markdown")
    assert r.status_code == 503


def test_markdown_wrong_worker_token_returns_401():
    _configure_worker_token()
    _seed_minimum()
    r = client.get(
        "/api/futures/tw/foreign-flow/markdown",
        headers={"X-Worker-Token": "wrong"},
    )
    assert r.status_code == 401


def test_markdown_missing_worker_token_header_returns_401():
    _configure_worker_token()
    _seed_minimum()
    r = client.get("/api/futures/tw/foreign-flow/markdown")
    assert r.status_code == 401


def test_markdown_returns_text_markdown_with_content():
    _configure_worker_token()
    _seed_minimum()
    r = client.get(
        "/api/futures/tw/foreign-flow/markdown?time_range=3Y",
        headers={"X-Worker-Token": WORKER_TOKEN},
    )
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/markdown")
    body = r.text
    assert "# 台指期 · 外資動向" in body
    assert "## AI 分析請求" in body
    assert "## TX 期貨日線" in body


def test_markdown_returns_404_when_no_tx_data():
    _configure_worker_token()
    r = client.get(
        "/api/futures/tw/foreign-flow/markdown",
        headers={"X-Worker-Token": WORKER_TOKEN},
    )
    assert r.status_code == 404


def test_markdown_204_when_latest_tx_is_not_today():
    """Non-trading day: latest TX bar predates today → 204 so the Worker skips."""
    _configure_worker_token()
    save_futures_daily_rows([
        {"symbol": "TX", "date": "2025-05-02", "contract_date": "202505",
         "open": 17000, "high": 17200, "low": 16950, "close": 17150,
         "volume": 1, "open_interest": 1, "settlement": 17150},
    ])
    save_institutional_futures_rows([
        {"symbol": "TX", "date": "2025-05-02",
         "foreign_long_oi": 130, "foreign_short_oi": 0,
         "foreign_long_amount": 419_500.0, "foreign_short_amount": 0.0},
    ])
    save_large_trader_rows([
        {"date": "2025-05-02", "market_oi": 100_000,
         "top5_long_oi": 0, "top5_short_oi": 0,
         "top10_long_oi": 65_000, "top10_short_oi": 60_000},
    ])
    r = client.get(
        "/api/futures/tw/foreign-flow/markdown?time_range=3Y",
        headers={"X-Worker-Token": WORKER_TOKEN},
    )
    assert r.status_code == 204
    assert r.text == ""


def test_markdown_400_on_unknown_time_range():
    _configure_worker_token()
    _seed_minimum()
    r = client.get(
        "/api/futures/tw/foreign-flow/markdown?time_range=2W",
        headers={"X-Worker-Token": WORKER_TOKEN},
    )
    assert r.status_code == 400


# ── POST /ai-report (Worker → Backend write) ────────────────────────────


def _good_body():
    return {
        "report_date":     "2026-05-14",
        "model":           "@cf/qwen/qwen3-30b-a3b-fp8",
        "prompt_version":  "v1",
        "input_markdown":  "## input",
        "output_markdown": "## output",
    }


def test_post_ai_report_rejects_missing_worker_token():
    _configure_worker_token()
    r = client.post(
        "/api/futures/tw/foreign-flow/ai-report",
        json=_good_body(),
    )
    assert r.status_code == 401


def test_post_ai_report_upserts_row():
    _configure_worker_token()
    body = _good_body()
    r = client.post(
        "/api/futures/tw/foreign-flow/ai-report",
        json=body,
        headers={"X-Worker-Token": WORKER_TOKEN},
    )
    assert r.status_code == 200
    assert r.json() == {"ok": True, "report_date": "2026-05-14"}

    body["model"]           = "model-v2"
    body["output_markdown"] = "## output v2"
    r2 = client.post(
        "/api/futures/tw/foreign-flow/ai-report",
        json=body,
        headers={"X-Worker-Token": WORKER_TOKEN},
    )
    assert r2.status_code == 200
    row = get_report("2026-05-14")
    assert row["model"]           == "model-v2"
    assert row["output_markdown"] == "## output v2"


def test_post_ai_report_validates_date_pattern():
    _configure_worker_token()
    bad = _good_body()
    bad["report_date"] = "not-a-date"
    r = client.post(
        "/api/futures/tw/foreign-flow/ai-report",
        json=bad,
        headers={"X-Worker-Token": WORKER_TOKEN},
    )
    assert r.status_code == 422


# ── GET /ai-report/latest (public) ─────────────────────────────────


def test_latest_returns_404_when_no_row():
    r = client.get("/api/futures/tw/foreign-flow/ai-report/latest")
    assert r.status_code == 404


def test_latest_returns_today_when_today_row_exists():
    from datetime import datetime
    import pytz
    today = datetime.now(pytz.timezone("Asia/Taipei")).strftime("%Y-%m-%d")
    save_report(today, "m", "v1", "in", "out")
    r = client.get("/api/futures/tw/foreign-flow/ai-report/latest")
    assert r.status_code == 200
    body = r.json()
    assert body["report_date"]     == today
    assert body["output_markdown"] == "out"


def test_latest_falls_back_to_most_recent_when_today_missing():
    # Two older rows; latest must be the chronologically last one.
    save_report("2026-05-10", "m", "v1", "in-10", "out-10")
    save_report("2026-05-14", "m", "v1", "in-14", "out-14")
    r = client.get("/api/futures/tw/foreign-flow/ai-report/latest")
    assert r.status_code == 200
    body = r.json()
    assert body["report_date"]     == "2026-05-14"
    assert body["output_markdown"] == "out-14"


# ── POST /ai-report/regenerate (public proxy → Worker) ─────────────


def test_regenerate_503_when_worker_not_configured():
    _configure_worker_token(None)
    _configure_worker_url(None)
    r = client.post("/api/futures/tw/foreign-flow/ai-report/regenerate")
    assert r.status_code == 503


def test_regenerate_proxies_to_worker_and_returns_new_row():
    _configure_worker_token()
    _configure_worker_url()

    from datetime import datetime
    import pytz
    today = datetime.now(pytz.timezone("Asia/Taipei")).strftime("%Y-%m-%d")

    def fake_post(url, headers=None, timeout=None, **_):
        save_report(today, "model-x", "v1", "in", "out-from-worker")
        m = MagicMock()
        m.status_code = 200
        m.text = "ok"
        return m

    with patch(
        "api.routes.foreign_flow_ai.requests.post",
        side_effect=fake_post,
    ):
        r = client.post("/api/futures/tw/foreign-flow/ai-report/regenerate")
    assert r.status_code == 200
    body = r.json()
    assert body["report_date"]     == today
    assert body["output_markdown"] == "out-from-worker"


def test_regenerate_502_when_worker_errors():
    _configure_worker_token()
    _configure_worker_url()
    m = MagicMock()
    m.status_code = 500
    m.text = "boom"
    with patch(
        "api.routes.foreign_flow_ai.requests.post",
        return_value=m,
    ):
        r = client.post("/api/futures/tw/foreign-flow/ai-report/regenerate")
    assert r.status_code == 502


def test_regenerate_502_when_worker_unreachable():
    _configure_worker_token()
    _configure_worker_url()
    import requests as _requests
    with patch(
        "api.routes.foreign_flow_ai.requests.post",
        side_effect=_requests.ConnectionError("nope"),
    ):
        r = client.post("/api/futures/tw/foreign-flow/ai-report/regenerate")
    assert r.status_code == 502
