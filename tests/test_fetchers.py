from unittest.mock import patch, MagicMock
import pandas as pd
import json

# conftest.py already sets DB_PATH=:memory: and calls db.init_db()
import db


def make_hist(prices):
    idx = pd.date_range("2026-01-01", periods=len(prices), freq="D")
    return pd.DataFrame({
        "Close": prices,
        "Open": prices,
        "High": prices,
        "Low": prices,
        "Volume": [0] * len(prices)
    }, index=idx)


def test_fetch_taiex_saves_indicator():
    mock_ticker = MagicMock()
    mock_ticker.history.return_value = make_hist([21334.0, 21458.0])
    mock_ticker.history_metadata = {"currency": "TWD"}

    with patch("fetchers.yfinance_fetcher.yf.Ticker", return_value=mock_ticker):
        from fetchers.yfinance_fetcher import fetch_taiex
        fetch_taiex()

    row = db.get_latest_indicator("taiex")
    assert row is not None
    assert row["value"] == 21458.0
    extra = json.loads(row["extra_json"])
    assert abs(extra["change_pct"] - 0.58) < 0.1
    assert extra["prev_close"] == 21334.0


def test_fetch_fx_saves_indicator():
    mock_ticker = MagicMock()
    mock_ticker.history.return_value = make_hist([32.11, 32.15])
    mock_ticker.history_metadata = {"currency": "USD"}

    with patch("fetchers.yfinance_fetcher.yf.Ticker", return_value=mock_ticker):
        from fetchers.yfinance_fetcher import fetch_fx
        fetch_fx()

    row = db.get_latest_indicator("fx")
    assert row is not None
    assert abs(row["value"] - 32.15) < 0.01


def test_fetch_all_stocks_saves_snapshots():
    db.add_watched_ticker(1, "0050.TW")
    mock_ticker = MagicMock()
    mock_ticker.history.return_value = make_hist([197.20, 198.35])
    mock_ticker.history_metadata = {"currency": "TWD"}
    mock_ticker.info = {"shortName": "元大台灣50"}

    with patch("fetchers.yfinance_fetcher.yf.Ticker", return_value=mock_ticker):
        from fetchers.yfinance_fetcher import fetch_all_stocks
        fetch_all_stocks()

    row = db.get_latest_stock("0050.TW")
    assert row is not None
    assert abs(row["price"] - 198.35) < 0.01
    assert row["currency"] == "TWD"


def test_fetch_stock_history_returns_indicators_and_candles():
    prices = [100 + i * 0.5 for i in range(120)]
    mock_ticker = MagicMock()
    mock_ticker.history.return_value = make_hist(prices)
    mock_ticker.history_metadata = {"currency": "TWD"}
    mock_ticker.info = {"shortName": "TEST"}

    with patch("fetchers.yfinance_fetcher.yf.Ticker", return_value=mock_ticker):
        from fetchers.yfinance_fetcher import fetch_stock_history
        data = fetch_stock_history("2330.TW", "1M")

    assert data is not None
    assert data["ticker"] == "2330.TW"
    assert data["name"] == "TEST"
    assert data["currency"] == "TWD"
    # 1M slices to 22 trading days
    assert len(data["dates"]) == 22
    assert len(data["candles"]) == 22
    for series in ("ma5", "ma20", "ma60", "rsi14", "macd", "macd_signal", "macd_histogram"):
        assert len(data["indicators"][series]) == 22
    # MA60 should be populated for the visible window after warm-up
    assert all(v is not None for v in data["indicators"]["ma60"])
    # RSI for a strictly rising series should be near 100
    assert data["indicators"]["rsi14"][-1] > 90


def test_fetch_stock_history_returns_none_when_empty():
    mock_ticker = MagicMock()
    mock_ticker.history.return_value = pd.DataFrame()

    with patch("fetchers.yfinance_fetcher.yf.Ticker", return_value=mock_ticker):
        from fetchers.yfinance_fetcher import fetch_stock_history
        assert fetch_stock_history("BOGUS", "3M") is None


def test_fetch_taiex_skips_on_empty_history():
    mock_ticker = MagicMock()
    mock_ticker.history.return_value = pd.DataFrame()

    with patch("fetchers.yfinance_fetcher.yf.Ticker", return_value=mock_ticker):
        from fetchers.yfinance_fetcher import fetch_taiex
        fetch_taiex()  # should not raise


def test_fetch_chip_total_saves_indicators():
    MARGIN_RESPONSE = {
        "status": 200,
        "data": [
            {"name": "MarginPurchase",      "date": "2026-04-29", "TodayBalance": 8672780},
            {"name": "ShortSale",            "date": "2026-04-29", "TodayBalance": 197420},
            {"name": "MarginPurchaseMoney", "date": "2026-04-29", "TodayBalance": 460963803000},
        ],
    }
    INST_RESPONSE = {
        "status": 200,
        "data": [
            {"name": "Foreign_Investor",   "date": "2026-04-29", "buy": 100_000_000_000, "sell": 50_000_000_000},
            {"name": "Foreign_Dealer_Self","date": "2026-04-29", "buy": 0,                "sell": 0},
            {"name": "Investment_Trust",   "date": "2026-04-29", "buy": 10_000_000_000,  "sell": 5_000_000_000},
            {"name": "Dealer_self",        "date": "2026-04-29", "buy": 1_000_000_000,   "sell": 2_000_000_000},
            {"name": "Dealer_Hedging",     "date": "2026-04-29", "buy": 5_000_000_000,   "sell": 4_000_000_000},
        ],
    }

    def fake_get(url, params=None, headers=None, timeout=None):
        mock = MagicMock()
        mock.raise_for_status = MagicMock()
        if params and params.get("dataset") == "TaiwanStockTotalMarginPurchaseShortSale":
            mock.json.return_value = MARGIN_RESPONSE
        elif params and params.get("dataset") == "TaiwanStockTotalInstitutionalInvestors":
            mock.json.return_value = INST_RESPONSE
        return mock

    with patch("fetchers.chip_total.requests.get", side_effect=fake_get):
        from fetchers.chip_total import fetch_chip_total
        fetch_chip_total(start_date="2026-04-25")

    # margin indicators
    row = db.get_latest_indicator("margin_balance")
    assert row is not None
    assert abs(row["value"] - 4609.638) < 1.0
    assert db.get_latest_indicator("short_balance") is not None
    assert db.get_latest_indicator("short_margin_ratio") is not None
    # institutional indicators
    assert db.get_latest_indicator("total_foreign_net") is not None
    assert db.get_latest_indicator("total_trust_net")   is not None
    assert db.get_latest_indicator("total_dealer_net")  is not None


def test_fetch_chip_total_handles_empty_response():
    fake_payload = {"status": 200, "data": []}
    with patch("fetchers.chip_total.requests.get") as mock_get:
        mock_get.return_value.json.return_value = fake_payload
        mock_get.return_value.raise_for_status = MagicMock()
        from fetchers.chip_total import fetch_chip_total
        fetch_chip_total(start_date="2026-04-25")  # should not raise


def test_fetch_ndc_saves_indicator():
    page_html = '<meta name="csrf-token" content="csrf123">'
    api_response = {
        "line": {
            "12": {"data": [
                {"x": "202601", "y": 23},
                {"x": "202602", "y": 24},
            ]},
            "2": {"data": [
                {"x": "202601", "y": 3},
                {"x": "202602", "y": 4},
            ]},
        }
    }
    page_resp = MagicMock()
    page_resp.text = page_html
    api_resp = MagicMock()
    api_resp.json.return_value = api_response
    api_resp.raise_for_status = MagicMock()

    scraper = MagicMock()
    scraper.get.return_value = page_resp
    scraper.post.return_value = api_resp

    with patch("fetchers.ndc.cloudscraper.create_scraper", return_value=scraper):
        from fetchers.ndc import fetch_ndc
        fetch_ndc()
    row = db.get_latest_indicator("ndc")
    assert row is not None
    assert row["value"] == 24.0
    extra = json.loads(row["extra_json"])
    assert extra["light"] == "黃紅燈"
    assert extra["period"] == "2026/02"


def test_fetch_fear_greed_saves_indicator():
    # CNN Fear & Greed Index API response shape.
    fake_json = {
        "fear_and_greed": {"score": 58.0, "rating": "greed"},
    }
    with patch("fetchers.fear_greed.requests.get") as mock_get:
        mock_get.return_value.json.return_value = fake_json
        mock_get.return_value.raise_for_status = MagicMock()
        from fetchers.fear_greed import fetch_fear_greed
        fetch_fear_greed()
    row = db.get_latest_indicator("fear_greed")
    assert row is not None
    assert row["value"] == 58.0
    extra = json.loads(row["extra_json"])
    assert extra["label"] == "貪婪"
    assert extra["rating_en"] == "greed"


def test_fetch_tw_volume_calls_check_alerts():
    """fetch_tw_volume 寫入後呼叫 check_alerts(Phase 4 follow-up)。"""
    db.init_db()
    sample = {"Date": "20260501", "TradeValue": "500000000000"}
    with patch("fetchers.volume.requests.get") as mock_get, \
         patch("fetchers.volume.check_alerts") as mock_check:
        mock_get.return_value.json.return_value = [sample]
        mock_get.return_value.raise_for_status = lambda: None
        from fetchers.volume import fetch_tw_volume
        fetch_tw_volume()
    mock_check.assert_called_once()
    args = mock_check.call_args[0]
    assert args[0] == "indicator"
    assert args[1] == "tw_volume"


def test_fetch_us_volume_calls_check_alerts():
    """fetch_us_volume 寫入後呼叫 check_alerts(Phase 4 follow-up)。"""
    db.init_db()
    import pandas as pd
    fake_hist = pd.DataFrame(
        {"Volume": [1_000_000_000]},
        index=pd.to_datetime(["2026-05-01"]),
    )
    with patch("yfinance.Ticker") as mock_ticker, \
         patch("fetchers.volume.check_alerts") as mock_check:
        mock_ticker.return_value.history.return_value = fake_hist
        from fetchers.volume import fetch_us_volume
        fetch_us_volume()
    mock_check.assert_called_once()
    args = mock_check.call_args[0]
    assert args[0] == "indicator"
    assert args[1] == "us_volume"
