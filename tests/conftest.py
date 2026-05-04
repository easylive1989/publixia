import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../backend"))
os.environ["DB_PATH"] = ":memory:"

import pytest
import db
from main import app
from api.dependencies import require_token, require_user


def _fake_token():
    """Bypass auth in tests — returns a synthetic token row tied to paul."""
    return {
        "id": 0,
        "prefix": "test_",
        "label": "test",
        "user_id": 1,
        "created_at": "2026-01-01T00:00:00",
        "expires_at": None,
        "last_used_at": None,
        "revoked_at": None,
    }


def _fake_user():
    return {"id": 1, "name": "paul", "created_at": "2026-01-01T00:00:00"}


# Module-level overrides: apply to every TestClient(app) request.
app.dependency_overrides[require_token] = _fake_token
app.dependency_overrides[require_user] = _fake_user


@pytest.fixture(autouse=True)
def reset_db():
    """Reset the in-memory database before each test."""
    db.connection._memory_conn = None
    db.init_db()
    yield
    if db.connection._memory_conn is not None:
        db.connection._memory_conn.close()
        db.connection._memory_conn = None
