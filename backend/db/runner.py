"""Hand-rolled SQL migration runner.

Applies forward-only `db/migrations/NNNN_*.sql` files in order, recording
applied versions in the `schema_migrations` table. See CONVENTIONS.md §2.4.
"""
import logging
import os
import re
import sqlite3
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

_VERSION_RE = re.compile(r"^(\d{4})_.+\.sql$")

# Tables known to exist in the pre-runner schema. If any of these are
# present in a DB that has no schema_migrations rows, we baseline the DB
# instead of re-running migrations.
_LEGACY_TABLES = frozenset({
    "indicator_snapshots",
    "watched_stocks",
    "stock_snapshots",
    "stock_broker_daily",
    "stock_chip_daily",
    "stock_per_daily",
    "stock_revenue_monthly",
    "stock_financial_quarterly",
    "stock_dividend_history",
    "price_alerts",
})


def _is_legacy_db(conn: sqlite3.Connection) -> bool:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()
    existing = {r[0] for r in rows}
    return bool(existing & _LEGACY_TABLES)


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat()


def _discover(migrations_dir: str) -> list[tuple[str, str]]:
    """Return [(version, full_path), ...] sorted by version."""
    if not os.path.isdir(migrations_dir):
        return []
    entries = []
    for name in os.listdir(migrations_dir):
        m = _VERSION_RE.match(name)
        if m:
            entries.append((m.group(1), os.path.join(migrations_dir, name)))
    entries.sort(key=lambda e: e[0])
    return entries


def run_migrations(conn: sqlite3.Connection, migrations_dir: str) -> None:
    """Apply any pending migrations, recording them in schema_migrations."""
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations ("
        "  version    TEXT PRIMARY KEY,"
        "  applied_at TEXT NOT NULL"
        ")"
    )
    conn.commit()

    applied = {
        r[0] for r in conn.execute("SELECT version FROM schema_migrations").fetchall()
    }

    discovered = _discover(migrations_dir)

    if not applied and _is_legacy_db(conn):
        # Pre-runner DBs have the schema from migration 0001 already in
        # place; only that version should be marked as baseline. Later
        # migrations (0002+) must run normally so any tables/columns they
        # add actually appear.
        if discovered:
            baseline_version = discovered[0][0]
            conn.execute(
                "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)",
                (baseline_version, _now_iso()),
            )
            applied.add(baseline_version)
            conn.commit()
            logger.info("migration_baselined version=%s", baseline_version)

    for version, path in discovered:
        if version in applied:
            continue
        with open(path, encoding="utf-8") as f:
            sql = f.read()
        try:
            conn.executescript("BEGIN; " + sql + "; COMMIT;")
        except sqlite3.Error:
            try:
                conn.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            logger.error("migration_failed version=%s path=%s", version, path)
            raise
        conn.execute(
            "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)",
            (version, _now_iso()),
        )
        conn.commit()
        logger.info("migration_applied version=%s", version)
