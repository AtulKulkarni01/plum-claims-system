"""Document-intelligence (#1) and cross-field validation (#2)."""

from __future__ import annotations

from app.models import ClaimSubmission, Decision, StepStatus
from app.validation import expand_shorthand, validate_registration


def test_validate_registration():
    assert validate_registration("KA/45678/2015")
    assert validate_registration("AYUR/KL/2345/2019")
    assert not validate_registration("NOTAREALREG")
    assert not validate_registration(None)


def test_expand_shorthand():
    assert expand_shorthand("Patient has HTN") == "Patient has Hypertension"
    assert expand_shorthand("T2DM noted") == "Type 2 Diabetes Mellitus noted"
    assert expand_shorthand("Viral Fever") == "Viral Fever"  # untouched
    assert expand_shorthand(None) is None


def _consult(docs):
    return ClaimSubmission.model_validate({
        "member_id": "EMP001", "policy_id": "PLUM_GHI_2024",
        "claim_category": "CONSULTATION", "treatment_date": "2024-11-01",
        "claimed_amount": 1500, "documents": docs,
    })


def test_document_alteration_routes_to_manual_review(submit):
    sub = _consult([
        {"file_id": "P", "actual_type": "PRESCRIPTION",
         "content": {"diagnosis": "Viral Fever", "patient_name": "Rajesh Kumar"}},
        {"file_id": "B", "actual_type": "HOSPITAL_BILL",
         "content": {"patient_name": "Rajesh Kumar", "total": 1500,
                     "line_items": [{"description": "Consultation", "amount": 1500}],
                     "alterations": ["consultation fee overwritten 1000 -> 1500"]}},
    ])
    result = submit(sub)
    assert result.decision == Decision.MANUAL_REVIEW
    assert "DOCUMENT_ALTERATION" in result.reasons


def test_duplicate_stamp_surfaced_as_signal(submit):
    sub = _consult([
        {"file_id": "P", "actual_type": "PRESCRIPTION",
         "content": {"diagnosis": "Viral Fever", "patient_name": "Rajesh Kumar"}},
        {"file_id": "B", "actual_type": "HOSPITAL_BILL",
         "content": {"patient_name": "Rajesh Kumar", "total": 1500,
                     "line_items": [{"description": "Consultation", "amount": 1500}],
                     "duplicate_stamps": ["ORIGINAL", "DUPLICATE"]}},
    ])
    result = submit(sub)
    assert any(s.code == "DUPLICATE_STAMP" for s in result.fraud_signals)


def test_invalid_registration_flagged_in_trace(submit):
    sub = _consult([
        {"file_id": "P", "actual_type": "PRESCRIPTION",
         "content": {"diagnosis": "Viral Fever", "patient_name": "Rajesh Kumar",
                     "doctor_registration": "NOTAREALREG"}},
        {"file_id": "B", "actual_type": "HOSPITAL_BILL",
         "content": {"patient_name": "Rajesh Kumar", "total": 1500,
                     "line_items": [{"description": "Consultation", "amount": 1500}]}},
    ])
    result = submit(sub)
    assert any(s.step == "extraction.registration" and s.status == StepStatus.WARN
               for s in result.trace)


def test_cross_field_total_mismatch_flagged(submit):
    sub = _consult([
        {"file_id": "P", "actual_type": "PRESCRIPTION",
         "content": {"diagnosis": "Viral Fever", "patient_name": "Rajesh Kumar"}},
        {"file_id": "B", "actual_type": "HOSPITAL_BILL",
         "content": {"patient_name": "Rajesh Kumar", "total": 1500,  # != 1300 sum
                     "line_items": [{"description": "Consultation", "amount": 1000},
                                    {"description": "Test", "amount": 300}]}},
    ])
    result = submit(sub)
    assert any(s.step == "extraction.cross_check" for s in result.trace)
    assert result.confidence_score < 0.95
