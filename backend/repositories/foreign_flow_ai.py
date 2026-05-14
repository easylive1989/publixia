"""AI-generated 外資動向 daily report repository.

Backs the "今日 AI 分析" section on the foreign-flow page. Rows are
written by the Cloudflare Worker (cron 18:30 TST or manual regenerate)
through the worker-token-gated POST .../ai-report endpoint, and read by
the frontend through the permission-gated GET .../ai-report/today.
"""
from datetime import datetime

import pytz

from db.connection import get_connection

TST = pytz.timezone("Asia/Taipei")


def save_report(
    report_date: str,
    model: str,
    prompt_version: str,
    input_markdown: str,
    output_markdown: str,
    generated_at: str | None = None,
) -> None:
    """Upsert a report. Same-date regenerate overwrites in place."""
    ts = generated_at or datetime.now(TST).isoformat()
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO foreign_flow_ai_reports ("
            "  report_date, model, prompt_version, "
            "  input_markdown, output_markdown, generated_at"
            ") VALUES (?,?,?,?,?,?) "
            "ON CONFLICT(report_date) DO UPDATE SET "
            "  model           = excluded.model, "
            "  prompt_version  = excluded.prompt_version, "
            "  input_markdown  = excluded.input_markdown, "
            "  output_markdown = excluded.output_markdown, "
            "  generated_at    = excluded.generated_at",
            (
                report_date, model, prompt_version,
                input_markdown, output_markdown, ts,
            ),
        )


def get_report(report_date: str) -> dict | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT report_date, model, prompt_version, "
            "       input_markdown, output_markdown, generated_at "
            "FROM foreign_flow_ai_reports WHERE report_date=?",
            (report_date,),
        ).fetchone()
        return dict(row) if row else None


def get_today_report() -> dict | None:
    """Return today's report using the Asia/Taipei calendar date."""
    today = datetime.now(TST).strftime("%Y-%m-%d")
    return get_report(today)
