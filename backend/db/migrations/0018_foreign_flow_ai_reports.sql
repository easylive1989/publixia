-- 0018_foreign_flow_ai_reports.sql
--
-- Stores the daily AI-generated 外資動向 analysis. One row per trading
-- date (Asia/Taipei calendar day). The Cloudflare Worker that calls
-- Workers AI writes here via the worker-token-gated POST endpoint;
-- the frontend reads "today's row" via a permission-gated GET.
--
-- Both `input_markdown` (the tables/prompt sent to the LLM) and
-- `output_markdown` (the LLM's response) are persisted so we can audit
-- regressions when prompts or models change without re-fetching the
-- underlying data.

CREATE TABLE IF NOT EXISTS foreign_flow_ai_reports (
    report_date     TEXT PRIMARY KEY,
    model           TEXT NOT NULL,
    prompt_version  TEXT NOT NULL,
    input_markdown  TEXT NOT NULL,
    output_markdown TEXT NOT NULL,
    generated_at    TEXT NOT NULL
);
