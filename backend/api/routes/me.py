"""GET /api/me — current user's identity + feature flags.

This route is the single source of truth the frontend polls on app boot
to decide which gated sections (e.g. 外資動向) to render.
"""
from fastapi import APIRouter, Depends, HTTPException

from api.dependencies import require_user
from api.schemas.me import MeResponse
from repositories.users import get_user_with_settings

router = APIRouter(prefix="/api", tags=["me"])


@router.get("/me", response_model=MeResponse)
def get_me(user: dict = Depends(require_user)) -> MeResponse:
    settings = get_user_with_settings(user["id"])
    if settings is None:                       # defensive — should not happen
        raise HTTPException(status_code=401, detail="Token user not found")
    return MeResponse(
        user_id                  = settings["id"],
        name                     = settings["name"],
        can_view_foreign_futures = settings["can_view_foreign_futures"],
    )
