"""FastAPI application: claim submission API + decision-review UI.

Endpoints
  GET  /                 -> single-page UI
  GET  /api/health       -> liveness + policy summary
  GET  /api/policy       -> policy summary for the UI
  GET  /api/test-cases   -> the 12 eval cases (for the UI dropdown)
  POST /api/claims       -> run a claim through the pipeline, return ClaimResult
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse

from .llm import llm_available
from .models import ClaimResult, ClaimSubmission
from .orchestrator import run_claim
from .policy import get_policy

ROOT = Path(__file__).resolve().parent.parent
STATIC = Path(__file__).resolve().parent / "static"
TEST_CASES_PATH = ROOT / "test_cases.json"

# Pick up GEMINI_API_KEY / OPENAI_API_KEY from .env without a manual export
# (does not override variables already set in the environment).
load_dotenv(ROOT / ".env", override=False)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

app = FastAPI(
    title="Plum Claims Processing",
    description="Multi-agent health insurance claims adjudication pipeline.",
    version="1.0.0",
)


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok", "policy": get_policy().summary()}


@app.get("/api/policy")
async def policy_summary() -> dict:
    summary = get_policy().summary()
    summary["llm_configured"] = llm_available()
    return summary


@app.get("/api/test-cases")
async def test_cases() -> JSONResponse:
    if not TEST_CASES_PATH.exists():
        return JSONResponse({"test_cases": []})
    with open(TEST_CASES_PATH, "r", encoding="utf-8") as fh:
        return JSONResponse(json.load(fh))


@app.post("/api/claims", response_model=ClaimResult)
async def submit_claim(submission: ClaimSubmission) -> ClaimResult:
    # FastAPI validates the body against ClaimSubmission and returns a precise
    # 422 on bad input automatically; the OpenAPI schema is generated from it too.
    return await run_claim(submission)
