"""HTTP API for the Futures Strategy Engine.

All endpoints sit behind require_strategy_permission. Ownership enforced
via 404. DSL bodies on write go through services.strategy_dsl.validator
.validate(check_translatability=True) so anything Backtrader can't
represent fails 422 before it hits the DB.
"""
import json as _json

from fastapi import APIRouter, Depends, HTTPException

from api.dependencies import require_strategy_permission
from api.schemas.strategy import (
    StrategyCreate, StrategyUpdate, StrategyResponse, SignalResponse,
)
from api.strategy_dsl_schema import DSL_SCHEMA
from repositories.strategies import (
    get_strategy, list_signals, create_strategy, update_strategy,
    delete_strategy, reset_strategy,
)
from services.strategy_dsl.validator import validate, DSLValidationError
from services.strategy_engine import force_close
from db.connection import get_connection


router = APIRouter(
    prefix="/api/strategies",
    tags=["strategies"],
    dependencies=[Depends(require_strategy_permission)],
)


def _list_user_strategies(user_id: int) -> list[dict]:
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


def _validate_dsls(entry_dsl, take_profit_dsl, stop_loss_dsl) -> None:
    try:
        validate(entry_dsl, kind="entry", check_translatability=True)
        validate(take_profit_dsl, kind="take_profit", check_translatability=True)
        validate(stop_loss_dsl, kind="stop_loss", check_translatability=True)
    except DSLValidationError as e:
        raise HTTPException(status_code=422, detail=str(e))


# ── read endpoints ──────────────────────────────────────────────────

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


# ── write endpoints ─────────────────────────────────────────────────

@router.post("")
def create_strategy_route(req: StrategyCreate,
                          user: dict = Depends(require_strategy_permission)):
    _validate_dsls(req.entry_dsl, req.take_profit_dsl, req.stop_loss_dsl)
    try:
        new_id = create_strategy(
            user_id=user["id"],
            name=req.name,
            direction=req.direction,
            contract=req.contract,
            contract_size=req.contract_size,
            max_hold_days=req.max_hold_days,
            entry_dsl=req.entry_dsl,
            take_profit_dsl=req.take_profit_dsl,
            stop_loss_dsl=req.stop_loss_dsl,
            notify_enabled=False,
        )
    except Exception as e:
        raise HTTPException(status_code=409, detail=f"create failed: {e}")
    return {"id": new_id}


@router.patch("/{strategy_id}")
def update_strategy_route(strategy_id: int, req: StrategyUpdate,
                          user: dict = Depends(require_strategy_permission)):
    s = _own_or_404(strategy_id, user)
    fields = req.model_dump(exclude_unset=True)
    if not fields:
        return {"ok": True}

    in_position = s["state"] != "idle"
    dsl_keys = {"entry_dsl", "take_profit_dsl", "stop_loss_dsl",
                "direction", "contract", "max_hold_days"}
    if in_position and (set(fields) & dsl_keys):
        raise HTTPException(
            status_code=422,
            detail=("strategy is in_position; only metadata "
                    "(name / contract_size) can be edited until reset"),
        )

    if any(k in fields for k in ("entry_dsl", "take_profit_dsl", "stop_loss_dsl")):
        _validate_dsls(
            fields.get("entry_dsl",       s["entry_dsl"]),
            fields.get("take_profit_dsl", s["take_profit_dsl"]),
            fields.get("stop_loss_dsl",   s["stop_loss_dsl"]),
        )

    update_strategy(strategy_id, **fields)
    return {"ok": True}


@router.delete("/{strategy_id}")
def delete_strategy_route(strategy_id: int,
                          user: dict = Depends(require_strategy_permission)):
    _own_or_404(strategy_id, user)
    delete_strategy(strategy_id)
    return {"ok": True}


# ── state actions ───────────────────────────────────────────────────

@router.post("/{strategy_id}/enable")
def enable_strategy(strategy_id: int,
                    user: dict = Depends(require_strategy_permission)):
    _own_or_404(strategy_id, user)
    if not user.get("discord_webhook_url"):
        raise HTTPException(
            status_code=422,
            detail="discord webhook not set for user; ask admin to set one",
        )
    update_strategy(strategy_id, notify_enabled=True)
    return {"ok": True}


@router.post("/{strategy_id}/disable")
def disable_strategy(strategy_id: int,
                     user: dict = Depends(require_strategy_permission)):
    _own_or_404(strategy_id, user)
    update_strategy(strategy_id, notify_enabled=False)
    return {"ok": True}


@router.post("/{strategy_id}/force_close")
def force_close_strategy(strategy_id: int,
                          user: dict = Depends(require_strategy_permission)):
    s = _own_or_404(strategy_id, user)
    try:
        force_close(s)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return {"ok": True}


@router.post("/{strategy_id}/reset")
def reset_strategy_route(strategy_id: int,
                          user: dict = Depends(require_strategy_permission)):
    _own_or_404(strategy_id, user)
    reset_strategy(strategy_id)
    return {"ok": True}
