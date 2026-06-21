"""Fraud routing (TC009) and graceful degradation on component failure (TC011)."""

from __future__ import annotations

from app.agents.fraud import ComponentFailure, detect_fraud
from app.models import ClaimSubmission, Decision, StepStatus
from app.policy import get_policy
from app.trace import Trace


def test_same_day_volume_routes_to_manual_review(submit, test_cases):
    result = submit(ClaimSubmission.model_validate(test_cases["TC009"]["input"]))
    assert result.decision == Decision.MANUAL_REVIEW
    assert result.requires_manual_review
    assert any(s.code == "SAME_DAY_CLAIM_VOLUME" for s in result.fraud_signals)
    # the specific triggering signal is surfaced in the message
    assert "manual_review" in result.member_message.lower()
    assert "4 claims" in result.member_message


def test_fraud_not_triggered_for_normal_claim():
    sub = ClaimSubmission.model_validate({
        "member_id": "EMP001", "policy_id": "PLUM_GHI_2024",
        "claim_category": "CONSULTATION", "treatment_date": "2024-11-01",
        "claimed_amount": 1000,
        "documents": [{"file_id": "A", "actual_type": "HOSPITAL_BILL",
                       "content": {"total": 1000}}],
    })
    signals = detect_fraud(sub, get_policy(), Trace())
    assert signals == []


def test_component_failure_raises_when_simulated():
    sub = ClaimSubmission.model_validate({
        "member_id": "EMP006", "policy_id": "PLUM_GHI_2024",
        "claim_category": "CONSULTATION", "treatment_date": "2024-10-28",
        "claimed_amount": 1000, "simulate_component_failure": True,
        "documents": [{"file_id": "A", "actual_type": "HOSPITAL_BILL",
                       "content": {"total": 1000}}],
    })
    try:
        detect_fraud(sub, get_policy(), Trace())
        assert False, "expected ComponentFailure"
    except ComponentFailure:
        pass


def test_pipeline_degrades_but_does_not_crash(submit, test_cases):
    result = submit(ClaimSubmission.model_validate(test_cases["TC011"]["input"]))
    # decision still produced
    assert result.decision == Decision.APPROVED
    assert result.degraded
    assert result.requires_manual_review
    # confidence lower than a clean full-pipeline approval (0.95)
    assert result.confidence_score < 0.85
    # failure is visible in the trace
    assert any(s.status == StepStatus.ERROR for s in result.trace)
    assert "incomplete processing" in result.member_message.lower()
