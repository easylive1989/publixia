"""Replace semantics + re-extraction of stale-prompt posts."""
import services.trade_extraction as te
from repositories import posts as posts_repo
from repositories import trades as trades_repo
from repositories import tracked_accounts as accounts_repo
from services import extraction_runner as er


def _post(ext_id="P", content="一些貼文內容"):
    acc = accounts_repo.list_accounts()[0]
    pid, _ = posts_repo.upsert_post(
        acc["id"], "threads", ext_id, "u", content, "2026-06-01T00:00:00"
    )
    return pid


def test_save_trades_replaces_old_set():
    pid = _post()
    trades_repo.save_trades(
        pid,
        [
            {"raw_symbol": "A", "direction": "buy", "confidence": 0.9},
            {"raw_symbol": "B", "direction": "sell", "confidence": 0.8},
        ],
        model="m", prompt_version="v1",
    )
    assert len(trades_repo.list_trades_for_posts([pid])[pid]) == 2

    # re-save with a smaller set → B is dropped, not kept
    trades_repo.save_trades(
        pid, [{"raw_symbol": "A", "direction": "buy", "confidence": 0.9}],
        model="m", prompt_version="v2",
    )
    rows = trades_repo.list_trades_for_posts([pid])[pid]
    assert [r["raw_symbol"] for r in rows] == ["A"]


def test_list_stale_extraction_posts():
    # a post extracted by an old version (even one with NO trades) is stale
    pid = _post()
    empty = _post("EMPTY")
    posts_repo.mark_extracted(pid, "v1")
    posts_repo.mark_extracted(empty, "v1")  # wrongly-empty post must also be caught

    stale_ids = {p["id"] for p in posts_repo.list_stale_extraction_posts("v2")}
    assert pid in stale_ids and empty in stale_ids

    # after re-extracting with the current version they're no longer stale
    posts_repo.mark_extracted(pid, "v2")
    posts_repo.mark_extracted(empty, "v2")
    assert all(p["id"] not in (pid, empty) for p in posts_repo.list_stale_extraction_posts("v2"))


def test_runner_reextracts_and_cleans_bad_trade(monkeypatch):
    pid = _post(content="大叔多年來拒買國巨")
    # an old, wrong extraction (treated 拒買 as buy) lands as v1/done
    trades_repo.save_trades(
        pid, [{"raw_symbol": "國巨", "ticker": "2327", "market": "TW", "direction": "buy", "confidence": 0.5}],
        model="m", prompt_version="v1",
    )
    posts_repo.set_extraction_status(pid, "done")

    # v2 prompt correctly extracts nothing from a "拒買" post
    monkeypatch.setattr(te, "run_ai", lambda *a, **k: {"trades": []})
    summary = er.run_extraction()

    assert summary["processed"] >= 1
    assert trades_repo.list_trades_for_posts([pid])[pid] == []     # bad trade removed
    assert all(p["id"] != pid for p in posts_repo.list_stale_extraction_posts(te.PROMPT_VERSION))
