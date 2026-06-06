"""Stock-reference repository.

Normalization map: a person writes 台積電 / 小台電 / 2330 / TSM, we resolve it
to a canonical ``(ticker, market)``. TW rows come from FinMind's stock list,
US rows from a maintained static table. ``aliases`` is a JSON array of
alternative names / nicknames stored as text.
"""
import json

from db.connection import get_connection


def upsert_reference_batch(rows: list[dict], source: str) -> int:
    """Upsert reference rows for one ``source``.

    Each row carries: ``ticker``, ``market``, ``canonical_name``, and
    optional ``aliases`` (a list of strings). Keyed on ``(market, ticker)``.
    """
    if not rows:
        return 0
    with get_connection() as conn:
        for r in rows:
            aliases = r.get("aliases")
            aliases_json = (
                json.dumps(aliases, ensure_ascii=False) if aliases else None
            )
            conn.execute(
                "INSERT INTO stock_reference ("
                "  ticker, market, canonical_name, aliases, source"
                ") VALUES (?,?,?,?,?) "
                "ON CONFLICT(market, ticker) DO UPDATE SET "
                "  canonical_name = excluded.canonical_name, "
                "  aliases        = excluded.aliases, "
                "  source         = excluded.source, "
                "  updated_at     = datetime('now')",
                (
                    r["ticker"],
                    r["market"],
                    r["canonical_name"],
                    aliases_json,
                    source,
                ),
            )
    return len(rows)


def find_by_alias_or_ticker(raw_symbol: str) -> tuple[str | None, str | None]:
    """Best-effort resolve a raw string to ``(ticker, market)``.

    Tries, in order: exact ticker (case-insensitive), exact canonical name,
    then an alias-array containment match. Returns ``(None, None)`` if nothing
    matches — the caller keeps the raw string regardless.
    """
    raw = (raw_symbol or "").strip()
    if not raw:
        return None, None
    with get_connection() as conn:
        row = conn.execute(
            "SELECT ticker, market FROM stock_reference "
            "WHERE ticker = ? COLLATE NOCASE LIMIT 1",
            (raw,),
        ).fetchone()
        if row:
            return row["ticker"], row["market"]

        row = conn.execute(
            "SELECT ticker, market FROM stock_reference "
            "WHERE canonical_name = ? COLLATE NOCASE LIMIT 1",
            (raw,),
        ).fetchone()
        if row:
            return row["ticker"], row["market"]

        # FinMind tags attention/disposition stocks with a trailing '*'
        # (e.g. 國巨*), which people never type. Match on the de-starred name.
        row = conn.execute(
            "SELECT ticker, market FROM stock_reference "
            "WHERE rtrim(canonical_name, '*') = ? COLLATE NOCASE LIMIT 1",
            (raw,),
        ).fetchone()
        if row:
            return row["ticker"], row["market"]

        # alias array stored as JSON text; match the quoted token to avoid
        # partial-substring false positives. NOCASE so English nicknames match
        # regardless of how the model cased them (NVIDIA / Nvidia / nvidia).
        row = conn.execute(
            "SELECT ticker, market FROM stock_reference "
            "WHERE aliases LIKE ? COLLATE NOCASE LIMIT 1",
            (f'%"{raw}"%',),
        ).fetchone()
        if row:
            return row["ticker"], row["market"]
    return None, None


def update_aliases(ticker: str, market: str, aliases: list[str]) -> int:
    """Overwrite the aliases of an existing reference row. Returns rows changed
    (0 if the ticker isn't in the roster yet). Lets code-defined alias overlays
    take effect without a full roster re-sync."""
    with get_connection() as conn:
        cur = conn.execute(
            "UPDATE stock_reference SET aliases=?, updated_at=datetime('now') "
            "WHERE market=? AND ticker=?",
            (json.dumps(aliases, ensure_ascii=False), market, ticker),
        )
        return cur.rowcount
