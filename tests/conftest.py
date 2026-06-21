"""Shared test fixtures and helpers."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.models import ClaimResult, ClaimSubmission  # noqa: E402
from app.orchestrator import run_claim  # noqa: E402
from app.policy import get_policy  # noqa: E402


def run(submission: ClaimSubmission) -> ClaimResult:
    """Synchronously drive the async pipeline (keeps tests dependency-light)."""
    return asyncio.run(run_claim(submission))


@pytest.fixture(scope="session")
def policy():
    return get_policy()


@pytest.fixture(scope="session")
def test_cases() -> dict[str, dict]:
    with open(ROOT / "test_cases.json", "r", encoding="utf-8") as fh:
        cases = json.load(fh)["test_cases"]
    return {c["case_id"]: c for c in cases}


@pytest.fixture
def submit():
    return run
