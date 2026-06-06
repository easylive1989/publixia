#!/usr/bin/env python3
"""Manually correct a post's extracted trade signals on the production DB.

Runs ON THE VPS against /opt/stock-dashboard/backend so it reuses the project's
own normalize() + price tracking — corrections look exactly like real extractions.

Commands:
  find  <query>        list posts whose content/title contains <query> (to get post_id)
  show  <post_id>      print the post + its current extracted_trades
  set   <post_id> <json>   replace the post's signals with <json> (a JSON array)

`set` is a full replace: pass the COMPLETE desired signal list for the post.
Each signal: {"raw_symbol": "台積電", "direction": "buy",
              "price": null, "quantity": null, "trade_date": null}
direction ∈ buy|sell|hold|bullish|bearish. ticker/market are filled by normalize().
Pass [] to clear all signals (e.g. a post wrongly flagged as a trade).

The post is left as-is otherwise; extraction_status stays 'done' so the scheduled
extractor won't touch it (stale re-extraction is disabled).
"""
import argparse
import json
import sys

sys.path.insert(0, "/opt/stock-dashboard/backend")

from db.connection import get_connection  # noqa: E402
from repositories import trades as trades_repo  # noqa: E402
from services.normalization import normalize  # noqa: E402


def find(query: str) -> None:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT p.id, t.display_name, p.platform, p.title, "
            "       substr(p.content,1,70) AS head, p.posted_at "
            "FROM posts p JOIN tracked_accounts t ON t.id = p.account_id "
            "WHERE p.content LIKE ? OR p.title LIKE ? "
            "ORDER BY p.posted_at DESC LIMIT 20",
            (f"%{query}%", f"%{query}%"),
        ).fetchall()
    if not rows:
        print("(no posts match)")
    for r in rows:
        print(f"#{r['id']:<6} {r['display_name']}  {r['platform']:<8} "
              f"{r['posted_at']}  {r['title'] or ''} {r['head']!r}")


def show(post_id: int) -> None:
    with get_connection() as conn:
        p = conn.execute(
            "SELECT id, platform, title, substr(content,1,160) AS head, "
            "posted_at, extraction_status FROM posts WHERE id=?", (post_id,),
        ).fetchone()
        if not p:
            print(f"(no post #{post_id})")
            return
        print(f"POST #{p['id']} [{p['platform']}] status={p['extraction_status']} "
              f"{p['posted_at']}\n  {p['title'] or ''}\n  {p['head']!r}")
        rows = conn.execute(
            "SELECT raw_symbol, ticker, market, direction, price, quantity, "
            "trade_date, confidence FROM extracted_trades WHERE post_id=? ORDER BY id",
            (post_id,),
        ).fetchall()
        if not rows:
            print("  TRADES: (none)")
        for r in rows:
            print(f"  TRADE {r['direction']:<8} raw={r['raw_symbol']!r} "
                  f"ticker={r['ticker']} market={r['market']} "
                  f"price={r['price']} qty={r['quantity']} date={r['trade_date']}")


def set_trades(post_id: int, signals: list[dict]) -> None:
    with get_connection() as conn:
        if not conn.execute("SELECT 1 FROM posts WHERE id=?", (post_id,)).fetchone():
            print(f"(no post #{post_id}) — aborting")
            return
    for s in signals:
        ticker, market = normalize(s["raw_symbol"])
        s["ticker"], s["market"] = ticker, market
        s.setdefault("confidence", 1.0)
    trades_repo.save_trades(post_id, signals, model="manual-fix", prompt_version="manual")
    # lock the post as 'done' so the scheduled extractor's pending queue can't
    # overwrite this manual fix.
    from repositories import posts as posts_repo
    posts_repo.set_extraction_status(post_id, "done")
    # price windows are keyed on (post_id, ticker); clear the post's rows so a
    # changed/added ticker is recomputed cleanly, then recompute.
    with get_connection() as conn:
        conn.execute("DELETE FROM trade_price_tracking WHERE post_id=?", (post_id,))
    from services.price_tracking_runner import run_price_tracking
    run_price_tracking()
    print("✓ updated. now:")
    show(post_id)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    pf = sub.add_parser("find"); pf.add_argument("query")
    ps = sub.add_parser("show"); ps.add_argument("post_id", type=int)
    pt = sub.add_parser("set"); pt.add_argument("post_id", type=int)
    pt.add_argument("signals_json", help="a JSON array, or '-' to read it from stdin")
    a = ap.parse_args()
    if a.cmd == "find":
        find(a.query)
    elif a.cmd == "show":
        show(a.post_id)
    elif a.cmd == "set":
        raw = sys.stdin.read() if a.signals_json == "-" else a.signals_json
        set_trades(a.post_id, json.loads(raw))
