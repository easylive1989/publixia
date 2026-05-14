"""FastAPI Depends providers."""
import logging

from fastapi import Depends, Header, HTTPException, Request

from repositories.users import get_user_by_id, get_user_with_settings
from services.token_service import verify_token, track_auth_failure

logger = logging.getLogger(__name__)


async def require_token(
    request: Request,
    authorization: str | None = Header(None),
) -> dict:
    """Verify Authorization: Bearer <token>. Raises 401 on miss/invalid.

    On failure, tracks the client IP for Discord ops-burst notification.
    The returned record now includes `user_id` (added by migration 0003).
    """
    client_ip = request.client.host if request.client else "unknown"

    if not authorization or not authorization.startswith("Bearer "):
        track_auth_failure(client_ip)
        raise HTTPException(
            status_code=401,
            detail="Missing or malformed Authorization header",
        )

    token = authorization[len("Bearer "):].strip()
    record = verify_token(token)
    if record is None:
        track_auth_failure(client_ip)
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired token",
        )

    return record


async def require_user(record: dict = Depends(require_token)) -> dict:
    """Resolve the user backing the token. Returns {id, name, created_at}.

    Raises 401 if the user record is missing (orphaned token, theoretically
    impossible after the 0003 migration but defensive).
    """
    user = get_user_by_id(record["user_id"])
    if user is None:
        raise HTTPException(status_code=401, detail="Token user not found")
    return user


async def require_foreign_futures_permission(
    user: dict = Depends(require_user),
) -> dict:
    """Extend require_user with the foreign-futures-flow page gate.

    Re-queries via get_user_with_settings to read can_view_foreign_futures
    and returns the merged dict. 403 with a stable detail string on
    failure so the frontend can distinguish "no permission" from
    "missing token" / 404.
    """
    settings = get_user_with_settings(user["id"])
    if settings is None or not settings["can_view_foreign_futures"]:
        raise HTTPException(status_code=403, detail="no foreign futures permission")
    return {**user, **settings}
