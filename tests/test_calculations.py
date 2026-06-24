"""Financial calculation order: network discount BEFORE co-pay."""

from __future__ import annotations

from app.models import ClaimSubmission, Decision


def test_copay_only_consultation(submit, test_cases):
    result = submit(ClaimSubmission.model_validate(test_cases["TC004"]["input"]))
    assert result.decision == Decision.APPROVED
    assert result.approved_amount == 1350  # 1500 - 10% co-pay
    assert result.confidence_score > 0.85


def test_network_discount_applied_before_copay(submit, test_cases):
    result = submit(ClaimSubmission.model_validate(test_cases["TC010"]["input"]))
    assert result.decision == Decision.APPROVED
    assert result.approved_amount == 3240  # 4500 *0.8 (network) *0.9 (copay)
    labels = [c.label for c in result.calculation]
    # network discount must appear before the co-pay step
    net_idx = next(i for i, lbl in enumerate(labels) if "Network discount" in lbl)
    copay_idx = next(i for i, lbl in enumerate(labels) if "Co-pay" in lbl)
    assert net_idx < copay_idx


def test_non_network_hospital_gets_no_discount(submit):
    sub = ClaimSubmission.model_validate({
        "member_id": "EMP001", "policy_id": "PLUM_GHI_2024",
        "claim_category": "CONSULTATION", "treatment_date": "2024-11-01",
        "claimed_amount": 1000, "hospital_name": "Tiny Local Clinic",
        "documents": [
            {"file_id": "A", "actual_type": "PRESCRIPTION",
             "content": {"diagnosis": "Viral Fever"}},
            {"file_id": "B", "actual_type": "HOSPITAL_BILL",
             "content": {"line_items": [{"description": "Consultation", "amount": 1000}]}},
        ],
    })
    result = submit(sub)
    assert result.approved_amount == 900  # only 10% co-pay, no discount
    assert not any("Network discount" in c.label for c in result.calculation)
