"""Policy rule adjudication: waiting period, exclusions, pre-auth, limits."""

from __future__ import annotations

from app.models import ClaimSubmission, Decision


def test_waiting_period_states_eligibility_date(submit, test_cases):
    result = submit(ClaimSubmission.model_validate(test_cases["TC005"]["input"]))
    assert result.decision == Decision.REJECTED
    assert "WAITING_PERIOD" in result.reasons
    # diabetes waiting = 90d from join 2024-09-01 -> eligible 2024-11-30
    assert "2024-11-30" in result.member_message


def test_excluded_condition_rejected_high_confidence(submit, test_cases):
    result = submit(ClaimSubmission.model_validate(test_cases["TC012"]["input"]))
    assert result.decision == Decision.REJECTED
    assert "EXCLUDED_CONDITION" in result.reasons
    assert result.confidence_score > 0.90


def test_pre_auth_missing_explains_and_guides(submit, test_cases):
    result = submit(ClaimSubmission.model_validate(test_cases["TC007"]["input"]))
    assert result.decision == Decision.REJECTED
    assert result.reasons == ["PRE_AUTH_MISSING"]
    assert "pre-authorization" in result.member_message.lower()


def test_per_claim_limit_states_limit_and_amount(submit, test_cases):
    result = submit(ClaimSubmission.model_validate(test_cases["TC008"]["input"]))
    assert result.decision == Decision.REJECTED
    assert "PER_CLAIM_EXCEEDED" in result.reasons
    assert "5,000" in result.member_message and "7,500" in result.member_message


def test_disc_herniation_does_not_trip_hernia_waiting(submit):
    """Regression: 'Lumbar Disc Herniation' must not match the 'hernia' rule."""
    sub = ClaimSubmission.model_validate({
        "member_id": "EMP007", "policy_id": "PLUM_GHI_2024",
        "claim_category": "CONSULTATION", "treatment_date": "2024-11-02",
        "claimed_amount": 1200,
        "documents": [
            {"file_id": "A", "actual_type": "PRESCRIPTION",
             "content": {"diagnosis": "Suspected Lumbar Disc Herniation"}},
            {"file_id": "B", "actual_type": "HOSPITAL_BILL",
             "content": {"total": 1200}},
        ],
    })
    result = submit(sub)
    assert "WAITING_PERIOD" not in result.reasons


def test_partial_itemizes_each_line(submit, test_cases):
    result = submit(ClaimSubmission.model_validate(test_cases["TC006"]["input"]))
    assert result.decision == Decision.PARTIAL
    assert result.approved_amount == 8000
    statuses = {li.description: li.status for li in result.line_item_results}
    assert statuses["Root Canal Treatment"] == "APPROVED"
    assert statuses["Teeth Whitening"] == "REJECTED"
    rejected = next(li for li in result.line_item_results if li.status == "REJECTED")
    assert rejected.reason  # every rejection has a line-level reason
