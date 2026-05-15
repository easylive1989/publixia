"""族群成交量 API。

`/api/groups/heatmap` 回傳近 N 個交易日 × Top M 族群 的量能變化矩陣，
每格的數值為當日 ``total_value`` 相對過去 20 交易日均的 % 變化。
"""
from fastapi import APIRouter, HTTPException

from repositories.group_volume import get_heatmap

router = APIRouter(prefix="/api", tags=["groups"])

_ALLOWED_TYPES = {"industry", "theme"}


@router.get("/groups/heatmap")
def groups_heatmap(
    type: str = "industry",
    days: int = 5,
    top_n: int = 10,
):
    if type not in _ALLOWED_TYPES:
        raise HTTPException(status_code=400, detail="Unknown group type")
    if not (1 <= days <= 30):
        raise HTTPException(status_code=400, detail="days out of range")
    if not (1 <= top_n <= 50):
        raise HTTPException(status_code=400, detail="top_n out of range")
    return get_heatmap(type, days=days, top_n=top_n)
