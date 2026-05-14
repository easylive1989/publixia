"""Routes backing the 外資動向 daily AI report.

Two audiences, two auth surfaces:

* Cloudflare Worker (cron + manual). Authenticates with a shared
  ``X-Worker-Token`` header set at deploy time. Uses
  ``GET /markdown`` to fetch the 5-day input markdown, then writes the
  LLM output back via ``POST /ai-report``.

* Frontend user. Authenticates via the existing bearer-token + foreign
  futures permission gate. Reads today's row via ``GET /ai-report/today``
  and asks for a rerun via ``POST /ai-report/regenerate``, which simply
  proxies a HTTP call to the Worker so all AI calls stay in one place.
"""
from datetime import datetime
import logging

import pytz
import requests
from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from core.settings import settings
from repositories.foreign_flow_ai import (
    get_today_report,
    save_report,
)
from services.foreign_flow_markdown import build_foreign_flow_markdown
from services.foreign_flow_payload import assemble_foreign_flow_payload


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["foreign-flow-ai"])

_TST = pytz.timezone("Asia/Taipei")


def _require_worker_token(x_worker_token: str | None = Header(default=None)) -> None:
    """Compare ``X-Worker-Token`` against ``settings.foreign_flow_worker_token``.

    503 when the server has no token configured (deploy misconfiguration)
    so the worker can surface that distinctly from a key-mismatch 401.
    """
    expected_secret = settings.foreign_flow_worker_token
    if expected_secret is None:
        raise HTTPException(
            status_code=503,
            detail="foreign_flow_worker_token not configured",
        )
    if x_worker_token is None or x_worker_token != expected_secret.get_secret_value():
        raise HTTPException(status_code=401, detail="invalid worker token")


def _today_str() -> str:
    return datetime.now(_TST).strftime("%Y-%m-%d")


# ── Markdown rendering (shared by Worker + user download) ───────────────


def _render_foreign_flow_markdown(time_range: str) -> Response:
    try:
        payload = assemble_foreign_flow_payload(time_range)
    except ValueError:
        raise HTTPException(status_code=400, detail="Unknown time_range")
    if payload is None:
        raise HTTPException(status_code=404, detail="No TX history available")
    md = build_foreign_flow_markdown(payload, _today_str())
    return Response(content=md, media_type="text/markdown; charset=utf-8")


@router.get(
    "/futures/tw/foreign-flow/markdown",
    dependencies=[Depends(_require_worker_token)],
)
def get_foreign_flow_markdown_for_worker(time_range: str = "1M") -> Response:
    """Markdown for the Cloudflare Worker that calls Workers AI."""
    return _render_foreign_flow_markdown(time_range)


@router.get("/futures/tw/foreign-flow/markdown/download")
def download_foreign_flow_markdown(time_range: str = "1M") -> Response:
    """Markdown for the in-app "下載 5 日資料" button — same renderer,
    accessible to anyone hitting the dashboard."""
    return _render_foreign_flow_markdown(time_range)


# ── Worker-side: write output ───────────────────────────────────────────


class AiReportIn(BaseModel):
    report_date:     str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    model:           str = Field(..., min_length=1)
    prompt_version:  str = Field(..., min_length=1)
    input_markdown:  str = Field(..., min_length=1)
    output_markdown: str = Field(..., min_length=1)


@router.post("/futures/tw/foreign-flow/ai-report", dependencies=[Depends(_require_worker_token)])
def write_foreign_flow_ai_report(body: AiReportIn) -> dict:
    save_report(
        report_date     = body.report_date,
        model           = body.model,
        prompt_version  = body.prompt_version,
        input_markdown  = body.input_markdown,
        output_markdown = body.output_markdown,
    )
    return {"ok": True, "report_date": body.report_date}


# ── User-side: read today / trigger regenerate ──────────────────────────


@router.get("/futures/tw/foreign-flow/ai-report/today")
def read_today_ai_report() -> dict:
    row = get_today_report()
    if row is None:
        raise HTTPException(status_code=404, detail="No report for today")
    return row


@router.post("/futures/tw/foreign-flow/ai-report/regenerate")
def regenerate_today_ai_report() -> dict:
    """Forward to the Worker, then return the freshly-written DB row.

    Worker timeout is generous because Workers AI may take 10–30 s on a
    cold model and we want the user to see "done" without polling.
    """
    if settings.foreign_flow_worker_url is None or settings.foreign_flow_worker_token is None:
        raise HTTPException(
            status_code=503,
            detail="foreign-flow worker not configured",
        )
    try:
        resp = requests.post(
            settings.foreign_flow_worker_url,
            headers={"X-Worker-Token": settings.foreign_flow_worker_token.get_secret_value()},
            timeout=90,
        )
    except requests.RequestException as exc:
        logger.exception("foreign_flow_regenerate_failed url=%s", settings.foreign_flow_worker_url)
        raise HTTPException(status_code=502, detail=f"worker unreachable: {exc}") from exc

    if resp.status_code >= 400:
        logger.warning(
            "foreign_flow_regenerate_worker_error status=%d body=%s",
            resp.status_code, resp.text[:300],
        )
        raise HTTPException(
            status_code=502,
            detail=f"worker returned {resp.status_code}",
        )

    row = get_today_report()
    if row is None:
        raise HTTPException(status_code=502, detail="worker did not persist a report")
    return row
