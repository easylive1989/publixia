"""Alert-related request/response schemas."""
from pydantic import BaseModel


class AlertRequest(BaseModel):
    target_type: str
    target: str
    condition: str
    threshold: float
    indicator_key: str | None = None
    window_n: int | None = None


class AlertToggleRequest(BaseModel):
    enabled: bool
