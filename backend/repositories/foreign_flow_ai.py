"""AI-generated 外資動向 daily report repository.

Backs the "近日 AI 分析" page. Rows are written by the Cloudflare Worker
(cron 18:30 TST or manual regenerate) through the worker-token-gated
POST .../ai-report endpoint, and read by the frontend through GET
.../ai-report/latest, which falls back to the most recent row when
today's hasn't been generated yet.
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
    """Look up one report by its calendar date."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT report_date, model, prompt_version, "
            "       input_markdown, output_markdown, generated_at "
            "FROM foreign_flow_ai_reports WHERE report_date=?",
            (report_date,),
        ).fetchone()
        return dict(row) if row else None


def get_latest_report() -> dict | None:
    """Return the most-recent report row by ``report_date``, or ``None``
    when the table is empty."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT report_date, model, prompt_version, "
            "       input_markdown, output_markdown, generated_at "
            "FROM foreign_flow_ai_reports "
            "ORDER BY report_date DESC LIMIT 1"
        ).fetchone()
        return dict(row) if row else None
