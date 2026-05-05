"""Response schema for GET /api/me."""
from pydantic import BaseModel


class MeResponse(BaseModel):
    user_id:          int
    name:             str
    can_use_strategy: bool
    has_webhook:      bool
