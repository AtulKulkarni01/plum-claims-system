"""Fraud & Anomaly Detection Agent.

Computes anomaly signals against policy fraud thresholds. Any HIGH signal routes
an otherwise-payable claim to MANUAL_REVIEW (never an auto-reject — a human
decides). Thresholds come from `policy.fraud_thresholds`.

This agent intentionally raises when `simulate_component_failure` is set, to
exercise the pipeline's graceful-degradation path (see orchestrator).
"""

from __future__ import annotations

from ..models import ClaimSubmission, FraudSeverity, FraudSignal, StepStatus
from ..policy import Policy
from ..trace import Trace


class ComponentFailure(RuntimeError):
    """Simulated/real failure of this component."""


def detect_fraud(
    submission: ClaimSubmission, policy: Policy, trace: Trace
) -> list[FraudSignal]:
    if submission.simulate_component_failure:
        raise ComponentFailure("fraud detection component failed (simulated)")

    thresholds = policy.fraud_thresholds
    signals: list[FraudSignal] = []

    # same-day claim volume (history + this claim)
    same_day = [
        h for h in submission.claims_history if h.date == submission.treatment_date
    ]
    same_day_count = len(same_day) + 1
    limit = thresholds.get("same_day_claims_limit", 99)
    if same_day_count > limit:
        signals.append(FraudSignal(
            code="SAME_DAY_CLAIM_VOLUME",
            detail=(
                f"{same_day_count} claims on {submission.treatment_date.isoformat()} "
                f"(limit {limit}). Providers: "
                f"{', '.join(h.provider or '?' for h in same_day)} + current."
            ),
            severity=FraudSeverity.HIGH,
        ))

    # monthly volume
    month_count = sum(
        1 for h in submission.claims_history
        if (h.date.year, h.date.month)
        == (submission.treatment_date.year, submission.treatment_date.month)
    ) + 1
    monthly_limit = thresholds.get("monthly_claims_limit", 99)
    if month_count > monthly_limit:
        signals.append(FraudSignal(
            code="MONTHLY_CLAIM_VOLUME",
            detail=f"{month_count} claims this month (limit {monthly_limit}).",
            severity=FraudSeverity.MEDIUM,
        ))

    # high-value claim
    hv = thresholds.get("high_value_claim_threshold", float("inf"))
    if submission.claimed_amount > hv:
        signals.append(FraudSignal(
            code="HIGH_VALUE_CLAIM",
            detail=f"Claimed ₹{submission.claimed_amount:,.0f} exceeds ₹{hv:,.0f}.",
            severity=FraudSeverity.HIGH,
        ))

    # document-integrity signals from extracted content (populated by perception /
    # extraction for real uploads; empty for the structured eval inputs).
    alterations = [a for d in submission.documents for a in (d.content or {}).get("alterations", [])]
    if alterations:
        signals.append(FraudSignal(
            code="DOCUMENT_ALTERATION",
            detail="Altered/overwritten amount(s): " + "; ".join(alterations),
            severity=FraudSeverity.HIGH,
        ))
    stamps = [s for d in submission.documents for s in (d.content or {}).get("duplicate_stamps", [])]
    if stamps:
        signals.append(FraudSignal(
            code="DUPLICATE_STAMP",
            detail="Duplicate document stamp(s): " + "; ".join(stamps),
            severity=FraudSeverity.MEDIUM,
        ))

    status = StepStatus.WARN if signals else StepStatus.PASS
    trace.add(
        "fraud.detection",
        status,
        (f"{len(signals)} fraud signal(s) detected" if signals
         else "No fraud signals detected"),
        {"signals": [s.model_dump() for s in signals],
         "same_day_count": same_day_count},
    )
    return signals
