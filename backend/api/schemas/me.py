"""Response schema for GET /api/me."""
from pydantic import BaseModel, ConfigDict


class MeResponse(BaseModel):
    """Identity + per-user feature gate flags the frontend polls on boot.

    ``extra='forbid'`` so any future per-user secret we add can't silently
    leak through a ``MeResponse(**settings)`` splat without a schema bump.
    """

    model_config = ConfigDict(extra="forbid")

    user_id:                  int
    name:                     str
    can_view_foreign_futures: bool
