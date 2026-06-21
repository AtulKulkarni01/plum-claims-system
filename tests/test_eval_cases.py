"""End-to-end eval: every case in test_cases.json must match its expected outcome."""

from __future__ import annotations

import pytest

from scripts.run_evals import evaluate, load_cases
from app.models import ClaimSubmission
from tests.conftest import run

CASES = load_cases()


@pytest.mark.parametrize("case", CASES, ids=[c["case_id"] for c in CASES])
def test_eval_case_matches_expected(case):
    result = run(ClaimSubmission.model_validate(case["input"]))
    matched, notes = evaluate(case, result)
    assert matched, f"{case['case_id']} mismatch: {notes}"


def test_every_result_carries_a_trace():
    for case in CASES:
        result = run(ClaimSubmission.model_validate(case["input"]))
        assert result.trace, f"{case['case_id']} produced no trace"
        assert result.claim_id
