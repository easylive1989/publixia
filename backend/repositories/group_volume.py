"""Group volume (族群成交量) repository.

Backs ``/api/groups/heatmap``. Each row is one (trade_date, group_type,
group_code) tuple — see migration 0021. The ``save_*`` helper computes
``mean_20d_value`` + ``pct_vs_mean_20d`` from rows already in the table,
so backfill scripts must iterate dates **chronologically** (oldest first)
or the rolling mean stays NULL.
"""
from db.connection import get_connection


_LOOKBACK_DAYS = 20


def save_group_volume_batch(
    trade_date: str,
    group_type: str,
    aggregates: list[dict],
) -> int:
    """Upsert per-group aggregates for one (trade_date, group_type).

    Each aggregate dict must carry: ``group_code``, ``group_name``,
    ``total_value``, ``total_volume``, ``stock_count``. Rolling 20-day
    mean and pct vs that mean are computed here and persisted alongside.
    """
    if not aggregates:
        return 0
    with get_connection() as conn:
        for agg in aggregates:
            row = conn.execute(
                "SELECT AVG(total_value) AS mean_v, COUNT(*) AS n FROM ("
                "  SELECT total_value FROM group_volume_daily "
                "  WHERE group_type=? AND group_code=? AND trade_date<? "
                "  ORDER BY trade_date DESC LIMIT ?"
                ")",
                (group_type, agg["group_code"], trade_date, _LOOKBACK_DAYS),
            ).fetchone()
            mean_20d = row["mean_v"] if row and row["n"] == _LOOKBACK_DAYS else None
            pct = (
                (agg["total_value"] - mean_20d) / mean_20d
                if mean_20d
                else None
            )
            conn.execute(
                "INSERT INTO group_volume_daily ("
                "  trade_date, group_type, group_code, group_name, "
                "  total_value, total_volume, stock_count, "
                "  mean_20d_value, pct_vs_mean_20d"
                ") VALUES (?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(trade_date, group_type, group_code) DO UPDATE SET "
                "  group_name      = excluded.group_name, "
                "  total_value     = excluded.total_value, "
                "  total_volume    = excluded.total_volume, "
                "  stock_count     = excluded.stock_count, "
                "  mean_20d_value  = excluded.mean_20d_value, "
                "  pct_vs_mean_20d = excluded.pct_vs_mean_20d",
                (
                    trade_date, group_type,
                    agg["group_code"], agg["group_name"],
                    float(agg["total_value"]),
                    int(agg["total_volume"]),
                    int(agg["stock_count"]),
                    mean_20d, pct,
                ),
            )
    return len(aggregates)


def get_heatmap(
    group_type: str,
    days: int = 5,
    top_n: int = 10,
) -> dict:
    """Return the heatmap matrix for ``group_type`` over the most recent
    ``days`` trading days. Rows are the top ``top_n`` groups ranked by
    ``total_value`` on the latest available day.
    """
    with get_connection() as conn:
        date_rows = conn.execute(
            "SELECT DISTINCT trade_date FROM group_volume_daily "
            "WHERE group_type=? ORDER BY trade_date DESC LIMIT ?",
            (group_type, days),
        ).fetchall()
        if not date_rows:
            return {"type": group_type, "days": [], "groups": []}
        date_list = sorted(r["trade_date"] for r in date_rows)
        latest_date = date_list[-1]

        top_rows = conn.execute(
            "SELECT group_code, group_name, total_value "
            "FROM group_volume_daily "
            "WHERE group_type=? AND trade_date=? "
            "ORDER BY total_value DESC LIMIT ?",
            (group_type, latest_date, top_n),
        ).fetchall()
        if not top_rows:
            return {"type": group_type, "days": date_list, "groups": []}
        top_codes = [r["group_code"] for r in top_rows]

        code_ph = ",".join("?" for _ in top_codes)
        date_ph = ",".join("?" for _ in date_list)
        series_rows = conn.execute(
            f"SELECT group_code, trade_date, pct_vs_mean_20d "
            f"FROM group_volume_daily "
            f"WHERE group_type=? "
            f"  AND group_code IN ({code_ph}) "
            f"  AND trade_date IN ({date_ph})",
            (group_type, *top_codes, *date_list),
        ).fetchall()
        pct_map = {
            (r["group_code"], r["trade_date"]): r["pct_vs_mean_20d"]
            for r in series_rows
        }

        groups = [
            {
                "code":         r["group_code"],
                "name":         r["group_name"],
                "latest_value": r["total_value"],
                "pct_series":   [pct_map.get((r["group_code"], d)) for d in date_list],
            }
            for r in top_rows
        ]
    return {"type": group_type, "days": date_list, "groups": groups}
