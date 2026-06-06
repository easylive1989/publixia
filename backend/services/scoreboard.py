"""Scoreboard standings — grade each tracked person's past stock calls.

Scoring rule (single source of truth; the frontend's per-call verdict mirrors it):
- side: buy/bullish → long; sell/bearish → sell; hold → excluded (not a call).
- a call is "evaluated" once its ``pct_latest`` is known (price tracking ran).
- copy-trade P&L of a call = +pct_latest for long, −pct_latest for sell.
- win = P&L ≥ 0, loss = P&L < 0.
- per person: win/loss counts, win_rate = W/(W+L), cum_return = Σ P&L (fraction),
  form = last 5 evaluated results newest-first.
- ranking: by cum_return desc; people with no evaluated call are DNP (rank null),
  listed last.
"""
from repositories import scoreboard as scoreboard_repo
from repositories import tracked_accounts as accounts_repo

_LONG = {"buy", "bullish"}
_SELL = {"sell", "bearish"}


def _side(direction: str) -> str | None:
    if direction in _LONG:
        return "long"
    if direction in _SELL:
        return "sell"
    return None  # hold / unknown → not a tradeable call


def _pnl(side: str, pct_latest: float | None) -> float | None:
    if pct_latest is None:
        return None
    return pct_latest if side == "long" else -pct_latest


def compute_standings() -> list[dict]:
    """Return per-person standings, ranked. Includes every enabled person — those
    with no evaluated call appear as DNP at the end."""
    people = accounts_repo.list_people_with_stats()
    # rows are newest-first; collect per person preserving that order
    by_person: dict[str, list[dict]] = {}
    for row in scoreboard_repo.list_scored_trades():
        by_person.setdefault(row["person_key"], []).append(row)

    standings = []
    for p in people:
        key = p["person_key"]
        wins = losses = signal_count = 0
        cum = 0.0
        form: list[str] = []
        for row in by_person.get(key, []):
            side = _side(row["direction"])
            if side is None:
                continue  # hold etc. — not a call
            signal_count += 1
            pl = _pnl(side, row["pct_latest"])
            if pl is None:
                continue  # not yet evaluated (追蹤中)
            cum += pl
            if pl >= 0:
                wins += 1
                if len(form) < 5:
                    form.append("w")
            else:
                losses += 1
                if len(form) < 5:
                    form.append("l")

        evaluated = wins + losses
        dnp = evaluated == 0
        standings.append({
            "person_key": key,
            "display_name": p["display_name"],
            "win_count": wins,
            "loss_count": losses,
            "signal_count": signal_count,
            "win_rate": (wins / evaluated) if evaluated else None,
            "cum_return": cum if not dnp else None,
            "form": form,
            "dnp": dnp,
        })

    # rank: scored by cum_return desc, DNP last (stable order among DNP)
    scored = [s for s in standings if not s["dnp"]]
    dnp = [s for s in standings if s["dnp"]]
    scored.sort(key=lambda s: s["cum_return"], reverse=True)
    for i, s in enumerate(scored):
        s["rank"] = i + 1
    for s in dnp:
        s["rank"] = None
    return scored + dnp
