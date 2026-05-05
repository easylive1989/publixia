"""Scheduler-job operations for the admin CLI.

Reads / writes the same `scheduler_jobs` table the backend reads on
startup. Stays self-contained (no backend imports) so the admin tool
can run with its own thin venv.
"""
import re
import subprocess
from datetime import datetime, timezone

from .db import connect


_FIELD_RE = re.compile(r"^[\d*,\-/]+$")


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat()


def list_jobs() -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT name, cron_expr, enabled, last_run_at, last_status, "
            "       last_error, updated_at "
            "FROM scheduler_jobs ORDER BY name"
        ).fetchall()
    return [dict(r) for r in rows]


def update_cron(name: str, cron_expr: str) -> bool:
    with connect() as conn:
        cur = conn.execute(
            "UPDATE scheduler_jobs SET cron_expr = ?, updated_at = ? "
            "WHERE name = ?",
            (cron_expr, _now_iso(), name),
        )
        conn.commit()
        return cur.rowcount > 0


def set_enabled(name: str, enabled: bool) -> bool:
    with connect() as conn:
        cur = conn.execute(
            "UPDATE scheduler_jobs SET enabled = ?, updated_at = ? "
            "WHERE name = ?",
            (1 if enabled else 0, _now_iso(), name),
        )
        conn.commit()
        return cur.rowcount > 0


def validate_cron(expr: str) -> str | None:
    """Light syntactic check for a 5-field cron expression.

    Returns an error message if the expression is malformed, otherwise
    None. Authoritative validation still happens in the backend on
    boot via APScheduler — invalid rows are logged & skipped there.
    """
    parts = expr.strip().split()
    if len(parts) != 5:
        return f"need exactly 5 fields, got {len(parts)}"
    ranges = [(0, 59), (0, 23), (1, 31), (1, 12), (0, 7)]
    for part, (lo, hi) in zip(parts, ranges):
        if not _FIELD_RE.match(part):
            return f"field {part!r} contains invalid characters"
        for tok in part.split(","):
            if "/" in tok:
                base, step = tok.split("/", 1)
                if not step.isdigit() or int(step) <= 0:
                    return f"bad step in {tok!r}"
                tok = base
            if tok == "*":
                continue
            if "-" in tok:
                a, b = tok.split("-", 1)
                if not (a.isdigit() and b.isdigit()):
                    return f"bad range in {tok!r}"
                if not (lo <= int(a) <= hi and lo <= int(b) <= hi):
                    return f"value out of range in {tok!r} (expected {lo}-{hi})"
            else:
                if not tok.isdigit():
                    return f"bad value {tok!r}"
                if not (lo <= int(tok) <= hi):
                    return f"value {tok} out of range (expected {lo}-{hi})"
    return None


def restart_backend(service: str = "stock-dashboard") -> tuple[bool, str]:
    """Restart the backend systemd service. Returns (ok, output)."""
    try:
        proc = subprocess.run(
            ["systemctl", "restart", service],
            capture_output=True, text=True, timeout=30,
        )
    except FileNotFoundError:
        return False, "systemctl not found on this machine"
    except subprocess.TimeoutExpired:
        return False, "systemctl restart timed out"
    if proc.returncode != 0:
        return False, (proc.stderr or proc.stdout or "unknown error").strip()
    return True, "service restarted"
