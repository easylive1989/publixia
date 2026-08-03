"""Market API routes over an in-memory DB."""
import math
from unittest.mock import patch

from fastapi.testclient import TestClient

import main
from repositories import market_volume as repo

client = TestClient(main.app)


def _seed(n=120):
    rows = []
    for i in range(n):
        index = 8000.0 + 40.0 * i
        rows.append({
            "date": f"2026-{1 + i // 28:02d}-{1 + i % 28:02d}",
            "taiex_close": index,
            "turnover": math.exp(-7.75 + 1.608 * math.log(index)),
        })
    repo.upsert_days(rows)


def test_volume_heat_shape():
    _seed()
    r = client.get("/api/market/volume-heat?days=10")
    assert r.status_code == 200
    body = r.json()
    assert len(body["days"]) == 10
    latest = body["latest"]
    assert latest["date"] == body["days"][-1]["date"]
    for key in ("taiex_close", "turnover", "expected_turnover",
                "volume_ratio", "residual", "percentile", "level", "label"):
        assert key in latest


def test_volume_heat_empty_db_is_not_an_error():
    r = client.get("/api/market/volume-heat")
    assert r.status_code == 200
    assert r.json() == {"latest": None, "days": []}


def test_volume_heat_days_out_of_range():
    assert client.get("/api/market/volume-heat?days=0").status_code == 400
    assert client.get("/api/market/volume-heat?days=999").status_code == 400


def test_refresh_schedules_background_sync():
    with patch("services.market_volume_sync.run_market_volume_sync") as run:
        r = client.post("/api/market/volume-heat/refresh")
    assert r.status_code == 200
    assert r.json() == {"status": "scheduled"}
    run.assert_called_once()
