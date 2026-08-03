import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../backend"))
os.environ["DB_PATH"] = ":memory:"

import pytest
import db


@pytest.fixture(autouse=True)
def reset_db():
    """Reset the in-memory database before each test."""
    db.connection._memory_conn = None
    db.init_db()
    yield
    if db.connection._memory_conn is not None:
        db.connection._memory_conn.close()
        db.connection._memory_conn = None
