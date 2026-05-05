"""Response schema for GET /api/me."""
from pydantic import BaseModel, ConfigDict


class MeResponse(BaseModel):
    """Privacy note: discord_webhook_url MUST NOT appear here. extra='forbid'
    so any future MeResponse(**settings) call fails loudly instead of
    silently dropping the URL — keeps the leak invariant load-bearing in
    the type system, not just by happenstance."""

    model_config = ConfigDict(extra="forbid")

    user_id:          int
    name:             str
    can_use_strategy: bool
    has_webhook:      bool
