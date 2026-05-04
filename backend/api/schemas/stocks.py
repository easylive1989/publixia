"""Stock-related request/response schemas."""
from pydantic import BaseModel


class AddStockRequest(BaseModel):
    ticker: str
