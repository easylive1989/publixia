"""HTTP API for the Futures Strategy Engine.

All endpoints sit behind require_strategy_permission so the user has
both a valid token AND can_use_strategy=True. Ownership is enforced per
endpoint by matching strategy.user_id to the request's user. A request
for someone else's strategy returns 404 (not 403) so id enumeration
can't distinguish "doesn't exist" from "not yours".
"""
import json as _json

from fastapi import APIRouter, Depends, HTTPException

from api.dependencies import require_strategy_permission
from api.schemas.strategy import (
    StrategyResponse, SignalResponse,
)
from api.strategy_dsl_schema import DSL_SCHEMA
from repositories.strategies import (
    get_strategy, list_signals,
)
from db.connection import get_connection


router = APIRouter(
    prefix="/api/strategies",
    tags=["strategies"],
    dependencies=[Depends(require_strategy_permission)],
)


def _list_user_strategies(user_id: int) -> list[dict]:
    """Read all strategies for a user (regardless of notify_enabled)."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM strategies WHERE user_id=? ORDER BY id",
            (user_id,),
        ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["entry_dsl"] = _json.loads(d["entry_dsl"])
        d["take_profit_dsl"] = _json.loads(d["take_profit_dsl"])
        d["stop_loss_dsl"] = _json.loads(d["stop_loss_dsl"])
        d["notify_enabled"] = bool(d["notify_enabled"])
        out.append(d)
    return out


def _own_or_404(strategy_id: int, user: dict) -> dict:
    s = get_strategy(strategy_id)
    if s is None or s["user_id"] != user["id"]:
        raise HTTPException(status_code=404, detail="Strategy not found")
    return s


@router.get("", response_model=list[StrategyResponse])
def list_strategies(user: dict = Depends(require_strategy_permission)):
    return _list_user_strategies(user["id"])


@router.get("/dsl/schema")
def get_dsl_schema(user: dict = Depends(require_strategy_permission)):
    return DSL_SCHEMA


@router.get("/{strategy_id}", response_model=StrategyResponse)
def get_one_strategy(strategy_id: int,
                     user: dict = Depends(require_strategy_permission)):
    return _own_or_404(strategy_id, user)


@router.get("/{strategy_id}/signals", response_model=list[SignalResponse])
def get_strategy_signals(strategy_id: int, limit: int = 50,
                          user: dict = Depends(require_strategy_permission)):
    _own_or_404(strategy_id, user)
    return list_signals(strategy_id, limit=limit)
