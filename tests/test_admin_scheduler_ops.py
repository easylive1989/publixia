"""Tests for admin/scheduler_ops.py — cron validator only."""
from admin.scheduler_ops import validate_cron


def test_validate_cron_accepts_valid_expressions():
    valid = [
        "0 14 * * *",
        "*/30 * * * *",
        "30 7 * * 1-5",
        "0 9 1 * *",
        "0 0 * * 0",
        "5,10,15 * * * *",
        "0-30/5 * * * *",
    ]
    for expr in valid:
        assert validate_cron(expr) is None, f"rejected valid expr: {expr!r}"


def test_validate_cron_rejects_bad_expressions():
    invalid = [
        "",
        "0 14 * *",
        "0 14 * * * *",
        "61 0 * * *",
        "0 24 * * *",
        "0 0 32 * *",
        "0 0 * 13 *",
        "0 0 * * 8",
        "abc * * * *",
        "*/0 * * * *",
    ]
    for expr in invalid:
        assert validate_cron(expr) is not None, f"accepted bad expr: {expr!r}"
