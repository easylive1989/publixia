"""GET /api/me — current user's identity + FSE feature flags.

This route is the single source of truth the frontend polls on app boot
to decide whether to render the strategy section and whether the
"enable notifications" toggle should be active.
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
        user_id          = settings["id"],
        name             = settings["name"],
        can_use_strategy = settings["can_use_strategy"],
        has_webhook      = settings["discord_webhook_url"] is not None,
    )
