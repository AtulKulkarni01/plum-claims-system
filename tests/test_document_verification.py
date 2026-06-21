"""Document Verification gate (TC001–TC003) plus unit-level checks."""

from __future__ import annotations

from app.agents.document_verification import verify_documents
from app.models import ClaimSubmission, ResultStatus
from app.policy import get_policy
from app.trace import Trace


def _codes(result):
    return {i.code for i in result.document_issues}


def test_missing_required_document_stops_and_names_types(submit, test_cases):
    result = submit(ClaimSubmission.model_validate(test_cases["TC001"]["input"]))
    assert result.status == ResultStatus.DOCUMENT_ISSUE
    assert result.decision is None
    assert "MISSING_REQUIRED_DOCUMENT" in _codes(result)
    # message must name uploaded type AND the missing required type
    msg = result.member_message.lower()
    assert "prescription" in msg
    assert "hospital bill" in msg


def test_unreadable_document_asks_reupload_not_reject(submit, test_cases):
    result = submit(ClaimSubmission.model_validate(test_cases["TC002"]["input"]))
    assert result.status == ResultStatus.DOCUMENT_ISSUE
    assert result.decision is None  # not REJECTED
    issue = next(i for i in result.document_issues if i.code == "UNREADABLE_DOCUMENT")
    assert "pharmacy bill" in issue.message.lower()
    assert "re-upload" in issue.action_required.lower()


def test_patient_mismatch_surfaces_both_names(submit, test_cases):
    result = submit(ClaimSubmission.model_validate(test_cases["TC003"]["input"]))
    assert result.status == ResultStatus.DOCUMENT_ISSUE
    assert "PATIENT_MISMATCH" in _codes(result)
    msg = result.member_message
    assert "Rajesh Kumar" in msg and "Arjun Mehta" in msg


def test_clean_documents_pass_the_gate():
    sub = ClaimSubmission.model_validate({
        "member_id": "EMP001", "policy_id": "PLUM_GHI_2024",
        "claim_category": "CONSULTATION", "treatment_date": "2024-11-01",
        "claimed_amount": 1000,
        "documents": [
            {"file_id": "A", "actual_type": "PRESCRIPTION",
             "content": {"patient_name": "Rajesh Kumar"}},
            {"file_id": "B", "actual_type": "HOSPITAL_BILL",
             "content": {"patient_name": "Rajesh Kumar"}},
        ],
    })
    issues = verify_documents(sub, get_policy(), Trace())
    assert issues == []
