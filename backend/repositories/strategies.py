"""Strategies + strategy_signals repository.

JSON columns (entry_dsl, take_profit_dsl, stop_loss_dsl) are stored as
TEXT in SQLite and parsed/serialised at the boundary so callers always
work with native Python dicts.
"""
import json
from datetime import datetime, timezone
from typing import Optional

from db.connection import get_connection


_ALLOWED_STATE_FIELDS = {
    "state",
    "entry_signal_date", "entry_fill_date", "entry_fill_price",
    "pending_exit_kind", "pending_exit_signal_date",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat()


def _row_to_strategy(row) -> dict:
    d = dict(row)
    d["entry_dsl"]       = json.loads(d["entry_dsl"])
    d["take_profit_dsl"] = json.loads(d["take_profit_dsl"])
    d["stop_loss_dsl"]   = json.loads(d["stop_loss_dsl"])
    d["notify_enabled"]  = bool(d["notify_enabled"])
    return d


def list_enabled_strategies(contract: str | None = None) -> list[dict]:
    """Strategies with notify_enabled=1, optionally on a single contract."""
    sql = "SELECT * FROM strategies WHERE notify_enabled = 1"
    args: tuple = ()
    if contract:
        sql += " AND contract = ?"
        args = (contract,)
    sql += " ORDER BY id"
    with get_connection() as conn:
        rows = conn.execute(sql, args).fetchall()
    return [_row_to_strategy(r) for r in rows]


def get_strategy(strategy_id: int) -> Optional[dict]:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM strategies WHERE id = ?", (strategy_id,),
        ).fetchone()
    return _row_to_strategy(row) if row else None


def update_strategy_state(strategy_id: int, **fields) -> None:
    """Update one or more state-machine columns. Pass None to set NULL.

    Allowed keys: state, entry_signal_date, entry_fill_date,
    entry_fill_price, pending_exit_kind, pending_exit_signal_date.
    """
    bad = set(fields) - _ALLOWED_STATE_FIELDS
    if bad:
        raise ValueError(f"unknown state fields: {sorted(bad)}")
    if not fields:
        return
    sets = ", ".join(f"{k}=?" for k in fields) + ", updated_at=?"
    values = list(fields.values()) + [_now_iso(), strategy_id]
    with get_connection() as conn:
        conn.execute(
            f"UPDATE strategies SET {sets} WHERE id=?", values,
        )
        conn.commit()


def write_signal(
    strategy_id: int, *,
    kind: str, signal_date: str,
    close_at_signal: float | None = None,
    fill_price: float | None = None,
    exit_reason: str | None = None,
    pnl_points: float | None = None,
    pnl_amount: float | None = None,
    message: str | None = None,
) -> int:
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO strategy_signals "
            "(strategy_id, kind, signal_date, close_at_signal, fill_price, "
            " exit_reason, pnl_points, pnl_amount, message, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (strategy_id, kind, signal_date, close_at_signal, fill_price,
             exit_reason, pnl_points, pnl_amount, message, _now_iso()),
        )
        conn.commit()
        return cur.lastrowid


def list_signals(strategy_id: int, limit: int = 50) -> list[dict]:
    """Newest first."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM strategy_signals WHERE strategy_id=? "
            "ORDER BY signal_date DESC, id DESC LIMIT ?",
            (strategy_id, limit),
        ).fetchall()
    return [dict(r) for r in rows]


def mark_strategy_error(strategy_id: int, error_message: str) -> None:
    """Set last_error + last_error_at, disable real-time notifications,
    AND write a RUNTIME_ERROR signal row so the failure surfaces in the
    user's signal history."""
    msg = (error_message or "")[:1000]
    now = _now_iso()
    today = now[:10]   # YYYY-MM-DD slice of the ISO timestamp
    with get_connection() as conn:
        conn.execute(
            "UPDATE strategies SET "
            "  last_error = ?, last_error_at = ?, "
            "  notify_enabled = 0, updated_at = ? "
            "WHERE id = ?",
            (msg, now, now, strategy_id),
        )
        conn.execute(
            "INSERT INTO strategy_signals "
            "(strategy_id, kind, signal_date, message, created_at) "
            "VALUES (?, 'RUNTIME_ERROR', ?, ?, ?)",
            (strategy_id, today, msg, now),
        )
        conn.commit()


_ALLOWED_UPDATE_FIELDS = {
    "name", "direction", "contract", "contract_size", "max_hold_days",
    "entry_dsl", "take_profit_dsl", "stop_loss_dsl",
    "notify_enabled",
}


def create_strategy(*,
                    user_id: int,
                    name: str,
                    direction: str,
                    contract: str,
                    contract_size: int,
                    entry_dsl: dict,
                    take_profit_dsl: dict,
                    stop_loss_dsl: dict,
                    max_hold_days: int | None = None,
                    notify_enabled: bool = False) -> int:
    """Insert a new strategy in `idle` state. Caller is responsible for
    pre-validating the DSL dicts (route layer does it via
    services.strategy_dsl.validator.validate)."""
    now = _now_iso()
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO strategies "
            "(user_id, name, direction, contract, contract_size, "
            " max_hold_days, entry_dsl, take_profit_dsl, stop_loss_dsl, "
            " notify_enabled, state, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'idle', ?, ?)",
            (user_id, name, direction, contract, contract_size,
             max_hold_days,
             json.dumps(entry_dsl),
             json.dumps(take_profit_dsl),
             json.dumps(stop_loss_dsl),
             1 if notify_enabled else 0,
             now, now),
        )
        conn.commit()
        return cur.lastrowid


def update_strategy(strategy_id: int, **fields) -> None:
    """Update one or more user-editable fields. Pass keys from
    _ALLOWED_UPDATE_FIELDS. DSL fields are JSON-serialised; bool fields
    encoded to 0/1."""
    bad = set(fields) - _ALLOWED_UPDATE_FIELDS
    if bad:
        raise ValueError(f"unknown update fields: {sorted(bad)}")
    if not fields:
        return
    encoded: dict = {}
    for k, v in fields.items():
        if k in ("entry_dsl", "take_profit_dsl", "stop_loss_dsl"):
            encoded[k] = json.dumps(v)
        elif k == "notify_enabled":
            encoded[k] = 1 if v else 0
        else:
            encoded[k] = v
    sets = ", ".join(f"{k}=?" for k in encoded) + ", updated_at=?"
    values = list(encoded.values()) + [_now_iso(), strategy_id]
    with get_connection() as conn:
        conn.execute(
            f"UPDATE strategies SET {sets} WHERE id=?", values,
        )
        conn.commit()


def delete_strategy(strategy_id: int) -> None:
    """Hard delete the strategy and its signals.

    SQLite FK cascades require PRAGMA foreign_keys=ON; we delete signals
    explicitly to stay compatible with connection pools that omit the pragma.
    """
    with get_connection() as conn:
        conn.execute(
            "DELETE FROM strategy_signals WHERE strategy_id=?",
            (strategy_id,),
        )
        conn.execute("DELETE FROM strategies WHERE id=?", (strategy_id,))
        conn.commit()


def reset_strategy(strategy_id: int) -> None:
    """Drop all signals + clear state machine columns + clear last_error.
    Keeps the strategy row itself; user can re-enable afterwards."""
    now = _now_iso()
    with get_connection() as conn:
        conn.execute(
            "DELETE FROM strategy_signals WHERE strategy_id=?",
            (strategy_id,),
        )
        conn.execute(
            "UPDATE strategies SET "
            "  state='idle', "
            "  entry_signal_date=NULL, entry_fill_date=NULL, "
            "  entry_fill_price=NULL, "
            "  pending_exit_kind=NULL, pending_exit_signal_date=NULL, "
            "  last_error=NULL, last_error_at=NULL, "
            "  updated_at=? "
            "WHERE id=?",
            (now, strategy_id),
        )
        conn.commit()
