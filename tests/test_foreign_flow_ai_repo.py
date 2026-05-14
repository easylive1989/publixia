"""Repository tests for repositories.foreign_flow_ai."""
from datetime import datetime

import pytz

from repositories.foreign_flow_ai import (
    get_report,
    get_today_report,
    save_report,
)


def test_save_and_read_round_trip():
    save_report(
        "2026-05-14",
        "@cf/qwen/qwen3-30b-a3b-fp8",
        "v1",
        "# input md",
        "# output md",
        generated_at="2026-05-14T18:35:00+08:00",
    )
    row = get_report("2026-05-14")
    assert row is not None
    assert row["report_date"]     == "2026-05-14"
    assert row["model"]           == "@cf/qwen/qwen3-30b-a3b-fp8"
    assert row["prompt_version"]  == "v1"
    assert row["input_markdown"]  == "# input md"
    assert row["output_markdown"] == "# output md"
    assert row["generated_at"]    == "2026-05-14T18:35:00+08:00"


def test_upsert_overwrites_same_date():
    save_report("2026-05-14", "model-a", "v1", "in1", "out1")
    save_report("2026-05-14", "model-b", "v2", "in2", "out2")
    row = get_report("2026-05-14")
    assert row["model"]           == "model-b"
    assert row["prompt_version"]  == "v2"
    assert row["input_markdown"]  == "in2"
    assert row["output_markdown"] == "out2"


def test_get_returns_none_when_missing():
    assert get_report("2099-12-31") is None


def test_get_today_uses_asia_taipei():
    today = datetime.now(pytz.timezone("Asia/Taipei")).strftime("%Y-%m-%d")
    save_report(today, "model", "v1", "in", "out")
    row = get_today_report()
    assert row is not None
    assert row["report_date"] == today


def test_default_generated_at_is_set_when_omitted():
    save_report("2026-05-14", "m", "v1", "in", "out")
    row = get_report("2026-05-14")
    assert row["generated_at"]  # truthy / non-empty
