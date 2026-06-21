"""Regression tests for bugs found in review (edge cases the 12 cases miss)."""

from __future__ import annotations

from app.models import ClaimSubmission, Decision, ResultStatus, StepStatus


def _consult(member="EMP001", **overrides):
    base = {
        "member_id": member, "policy_id": "PLUM_GHI_2024",
        "claim_category": "CONSULTATION", "treatment_date": "2024-11-01",
        "claimed_amount": 1500,
        "documents": [
            {"file_id": "P", "actual_type": "PRESCRIPTION",
             "content": {"diagnosis": "Viral Fever", "patient_name": "Rajesh Kumar"}},
            {"file_id": "B", "actual_type": "HOSPITAL_BILL",
             "content": {"patient_name": "Rajesh Kumar", "total": 1500}},
        ],
    }
    base.update(overrides)
    return ClaimSubmission.model_validate(base)


def test_malformed_content_degrades_not_crashes(submit):
    """A non-numeric amount must NOT 500 the pipeline (ValidationError caught)."""
    sub = ClaimSubmission.model_validate({
        "member_id": "EMP001", "policy_id": "PLUM_GHI_2024",
        "claim_category": "CONSULTATION", "treatment_date": "2024-11-01",
        "claimed_amount": 1500,
        "documents": [
            {"file_id": "P", "actual_type": "PRESCRIPTION",
             "content": {"diagnosis": "Viral Fever"}},
            {"file_id": "B", "actual_type": "HOSPITAL_BILL",
             "content": {"total": "twelve hundred"}},  # bad type
        ],
    })
    result = submit(sub)  # must not raise
    assert result.status == ResultStatus.COMPLETED
    assert any(s.step == "extraction.document" and s.status == StepStatus.WARN
               for s in result.trace)


def test_consultation_with_mri_line_item_not_preauth_rejected(submit):
    """Pre-auth is a DIAGNOSTIC rule; an MRI word in a consultation bill must
    not trigger a false PRE_AUTH_MISSING (the old wrong-threshold bug)."""
    sub = _consult(documents=[
        {"file_id": "P", "actual_type": "PRESCRIPTION",
         "content": {"diagnosis": "Back pain"}},
        {"file_id": "B", "actual_type": "HOSPITAL_BILL",
         "content": {"line_items": [
             {"description": "MRI referral note", "amount": 1500}]}},
    ])
    result = submit(sub)
    assert "PRE_AUTH_MISSING" not in result.reasons
    assert result.decision == Decision.APPROVED


def test_ct_substring_does_not_false_match(submit):
    """'Injection' contains 'ct' — must not be read as a CT scan."""
    sub = ClaimSubmission.model_validate({
        "member_id": "EMP007", "policy_id": "PLUM_GHI_2024",
        "claim_category": "DIAGNOSTIC", "treatment_date": "2024-11-01",
        "claimed_amount": 800,
        "documents": [
            {"file_id": "P", "actual_type": "PRESCRIPTION",
             "content": {"diagnosis": "Allergy"}},
            {"file_id": "L", "actual_type": "LAB_REPORT", "content": {}},
            {"file_id": "B", "actual_type": "HOSPITAL_BILL",
             "content": {"line_items": [
                 {"description": "Injection therapy", "amount": 800}]}},
        ],
    })
    result = submit(sub)
    assert "PRE_AUTH_MISSING" not in result.reasons


def test_annual_limit_exhausted_rejects_cleanly(submit):
    """ytd == annual limit must REJECT, not 'APPROVE for 0'."""
    result = submit(_consult(ytd_claims_amount=50000, claimed_amount=1000,
                             documents=[
        {"file_id": "P", "actual_type": "PRESCRIPTION",
         "content": {"diagnosis": "Viral Fever"}},
        {"file_id": "B", "actual_type": "HOSPITAL_BILL", "content": {"total": 1000}},
    ]))
    assert result.decision == Decision.REJECTED
    assert "ANNUAL_LIMIT_EXCEEDED" in result.reasons
    assert result.approved_amount == 0.0


def test_total_not_double_counted_across_documents(submit):
    """A stray total on the prescription must not inflate the covered amount."""
    sub = _consult(documents=[
        {"file_id": "P", "actual_type": "PRESCRIPTION",
         "content": {"diagnosis": "Viral Fever", "total": 500}},  # stray total
        {"file_id": "B", "actual_type": "HOSPITAL_BILL",
         "content": {"total": 1500}},
    ])
    result = submit(sub)
    assert result.approved_amount == 1350  # 1500 - 10% co-pay, NOT 2000-based


def test_unknown_member_routes_to_manual_review(submit):
    result = submit(_consult(member="EMP999"))
    assert result.decision == Decision.MANUAL_REVIEW
    assert result.requires_manual_review
    assert "MEMBER_NOT_FOUND" in result.reasons


def test_high_value_routed_even_when_fraud_component_fails(submit):
    """auto_manual_review_above must hold even if fraud detection crashes."""
    sub = ClaimSubmission.model_validate({
        "member_id": "EMP001", "policy_id": "PLUM_GHI_2024",
        "claim_category": "PHARMACY", "treatment_date": "2024-11-01",
        "claimed_amount": 30000, "simulate_component_failure": True,
        "documents": [
            {"file_id": "P", "actual_type": "PRESCRIPTION",
             "content": {"diagnosis": "Chronic condition"}},
            {"file_id": "B", "actual_type": "PHARMACY_BILL",
             "content": {"total": 12000}},
        ],
    })
    result = submit(sub)
    assert result.decision == Decision.MANUAL_REVIEW
    assert "HIGH_VALUE_CLAIM" in result.reasons
