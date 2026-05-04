import os
import sys
import sqlite3

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../backend"))
os.environ.setdefault("DB_PATH", ":memory:")

from db import runner


def _fresh_conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    return conn


def test_runner_creates_schema_migrations_table(tmp_path):
    conn = _fresh_conn()
    runner.run_migrations(conn, str(tmp_path))  # empty migrations dir

    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_migrations'"
    ).fetchall()
    assert len(rows) == 1


def test_runner_applies_pending_migration(tmp_path):
    (tmp_path / "0001_create_widgets.sql").write_text(
        "CREATE TABLE widgets (id INTEGER PRIMARY KEY, name TEXT);"
    )
    conn = _fresh_conn()
    runner.run_migrations(conn, str(tmp_path))

    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}
    assert "widgets" in tables

    versions = [r[0] for r in conn.execute(
        "SELECT version FROM schema_migrations ORDER BY version"
    ).fetchall()]
    assert versions == ["0001"]


def test_runner_skips_already_applied_migrations(tmp_path):
    (tmp_path / "0001_create_widgets.sql").write_text(
        "CREATE TABLE widgets (id INTEGER PRIMARY KEY);"
    )
    conn = _fresh_conn()
    runner.run_migrations(conn, str(tmp_path))
    runner.run_migrations(conn, str(tmp_path))  # second call must be a no-op

    versions = [r[0] for r in conn.execute(
        "SELECT version FROM schema_migrations"
    ).fetchall()]
    assert versions == ["0001"]


def test_runner_applies_multiple_migrations_in_order(tmp_path):
    (tmp_path / "0002_add_color.sql").write_text(
        "ALTER TABLE widgets ADD COLUMN color TEXT;"
    )
    (tmp_path / "0001_create_widgets.sql").write_text(
        "CREATE TABLE widgets (id INTEGER PRIMARY KEY);"
    )
    conn = _fresh_conn()
    runner.run_migrations(conn, str(tmp_path))

    cols = [r[1] for r in conn.execute("PRAGMA table_info(widgets)").fetchall()]
    assert "color" in cols
    versions = [r[0] for r in conn.execute(
        "SELECT version FROM schema_migrations ORDER BY version"
    ).fetchall()]
    assert versions == ["0001", "0002"]


def test_runner_baselines_existing_db(tmp_path):
    """If the DB already has the legacy schema but no schema_migrations,
    mark all migrations as applied without running them."""
    conn = _fresh_conn()
    # Simulate an existing VPS DB by creating a known legacy table directly.
    conn.execute(
        "CREATE TABLE indicator_snapshots ("
        "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "  indicator TEXT NOT NULL,"
        "  timestamp TEXT NOT NULL,"
        "  value REAL NOT NULL,"
        "  extra_json TEXT"
        ")"
    )
    conn.commit()

    # A migration that WOULD fail if executed (the table already exists).
    (tmp_path / "0001_initial.sql").write_text(
        "CREATE TABLE indicator_snapshots (x INTEGER);"
    )

    runner.run_migrations(conn, str(tmp_path))

    # Migration is recorded as applied, but was NOT executed
    # (otherwise the CREATE TABLE would have errored).
    versions = [r[0] for r in conn.execute(
        "SELECT version FROM schema_migrations"
    ).fetchall()]
    assert versions == ["0001"]
    # Original schema preserved.
    cols = [r[1] for r in conn.execute(
        "PRAGMA table_info(indicator_snapshots)"
    ).fetchall()]
    assert "indicator" in cols and "x" not in cols


def test_runner_does_not_baseline_fresh_db(tmp_path):
    """Fresh DB (no known legacy tables) goes through the normal path."""
    (tmp_path / "0001_initial.sql").write_text(
        "CREATE TABLE indicator_snapshots (id INTEGER PRIMARY KEY, indicator TEXT);"
    )
    conn = _fresh_conn()
    runner.run_migrations(conn, str(tmp_path))

    cols = [r[1] for r in conn.execute(
        "PRAGMA table_info(indicator_snapshots)"
    ).fetchall()]
    assert cols == ["id", "indicator"]  # came from the migration


def test_runner_rolls_back_on_bad_migration(tmp_path):
    """A SQL error must rollback the transaction and not record the version."""
    import pytest as _pytest

    (tmp_path / "0001_good.sql").write_text(
        "CREATE TABLE good (id INTEGER);"
    )
    (tmp_path / "0002_bad.sql").write_text(
        "CREATE TABLE bad (id INTEGER);\n"
        "THIS IS NOT VALID SQL;"
    )
    conn = _fresh_conn()

    with _pytest.raises(sqlite3.Error):
        runner.run_migrations(conn, str(tmp_path))

    versions = {r[0] for r in conn.execute(
        "SELECT version FROM schema_migrations"
    ).fetchall()}
    # 0001 succeeded and was recorded; 0002 must NOT be recorded.
    assert versions == {"0001"}
    # 'bad' table must not exist (rolled back).
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}
    assert "good" in tables
    assert "bad" not in tables
