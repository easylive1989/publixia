"""Tests for the scheduler_jobs repository + start_scheduler seeding."""
import db
from repositories.scheduler import (
    insert_default, list_jobs, get_job, update_cron, set_enabled, record_run,
)


def test_insert_default_only_inserts_once():
    db.init_db()
    assert insert_default("test_job", "0 9 * * *") is True
    assert insert_default("test_job", "0 18 * * *") is False  # not overwritten

    job = get_job("test_job")
    assert job is not None
    assert job["cron_expr"] == "0 9 * * *"
    assert job["enabled"] == 1


def test_update_cron_and_set_enabled():
    db.init_db()
    insert_default("foo", "0 6 * * *")

    assert update_cron("foo", "30 7 * * 1-5") is True
    assert get_job("foo")["cron_expr"] == "30 7 * * 1-5"

    assert set_enabled("foo", False) is True
    assert get_job("foo")["enabled"] == 0
    assert set_enabled("foo", True) is True
    assert get_job("foo")["enabled"] == 1


def test_record_run_stamps_status():
    db.init_db()
    insert_default("bar", "* * * * *")

    record_run("bar", "ok", None)
    row = get_job("bar")
    assert row["last_status"] == "ok"
    assert row["last_run_at"] is not None
    assert row["last_error"] is None

    record_run("bar", "error", "boom")
    row = get_job("bar")
    assert row["last_status"] == "error"
    assert row["last_error"] == "boom"


def test_list_jobs_sorted_by_name():
    db.init_db()
    insert_default("zeta", "0 0 * * *")
    insert_default("alpha", "0 0 * * *")
    names = [j["name"] for j in list_jobs()]
    assert names == sorted(names)


def test_start_scheduler_seeds_registry_defaults(monkeypatch):
    """Seeding inserts a row for every registered job using its default cron."""
    db.init_db()

    # Prevent APScheduler from starting a real background thread / firing jobs.
    import scheduler as scheduler_module

    class _StubScheduler:
        def __init__(self, *a, **kw): self.jobs = []
        def add_job(self, fn, trigger, **kw): self.jobs.append((kw.get("id"), trigger))
        def start(self): pass

    monkeypatch.setattr(scheduler_module, "BackgroundScheduler", _StubScheduler)

    scheduler_module.start_scheduler()

    from jobs.registry import JOBS
    rows = {r["name"]: r for r in list_jobs()}
    for name, spec in JOBS.items():
        assert name in rows, f"missing seeded row for {name}"
        assert rows[name]["cron_expr"] == spec.default_cron


def test_start_scheduler_respects_disabled_rows(monkeypatch):
    """Rows with enabled=0 are not added to the running scheduler."""
    db.init_db()
    import scheduler as scheduler_module

    added_ids: list[str] = []

    class _StubScheduler:
        def __init__(self, *a, **kw): pass
        def add_job(self, fn, trigger, **kw): added_ids.append(kw.get("id"))
        def start(self): pass

    monkeypatch.setattr(scheduler_module, "BackgroundScheduler", _StubScheduler)

    # Seed once so rows exist, then turn one off, then re-run start.
    scheduler_module.start_scheduler()
    set_enabled("news", False)

    added_ids.clear()
    scheduler_module.start_scheduler()
    assert "news" not in added_ids
    # Other jobs still present.
    assert "taiex" in added_ids
