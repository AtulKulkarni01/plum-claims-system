"""Pipeline orchestrator.

Runs the agents in order and owns the single source of truth for a claim's
result and trace. Two design commitments live here:

  * The verification gate is the ONLY stage allowed to short-circuit the
    pipeline (document problems must stop everything before a decision).
  * Every other stage runs inside `_safe(...)`: if it raises, the failure is
    recorded in the trace, confidence is reduced, the claim is flagged for
    manual review, and the pipeline CONTINUES with whatever it has. The system
    degrades; it never crashes.
"""

from __future__ import annotations

import uuid
from typing import Callable, Optional, TypeVar

from .agents.adjudication import AdjudicationOutcome, adjudicate
from .agents.document_verification import verify_documents
from .agents.extraction import extract_claim
from .agents.fraud import detect_fraud
from .models import (
    ClaimResult,
    ClaimSubmission,
    Decision,
    ExtractedClaim,
    FraudSignal,
    ResultStatus,
    StepStatus,
)
from .policy import Policy, get_policy
from .trace import Trace

T = TypeVar("T")

BASE_CONFIDENCE = 0.95
COMPONENT_FAILURE_PENALTY = -0.35


def _safe(
    trace: Trace, step: str, fn: Callable[[], T], default: T
) -> tuple[T, bool]:
    """Run fn; on any exception record it and return (default, failed=True)."""
    try:
        return fn(), False
    except Exception as exc:  # noqa: BLE001 - resilience is the whole point
        trace.add(
            step,
            StepStatus.ERROR,
            f"Component failed and was skipped: {exc}",
            {"error": str(exc), "error_type": type(exc).__name__},
            confidence_delta=COMPONENT_FAILURE_PENALTY,
        )
        return default, True


async def run_claim(
    submission: ClaimSubmission, policy: Optional[Policy] = None
) -> ClaimResult:
    policy = policy or get_policy()
    trace = Trace()
    claim_id = f"CLM_{uuid.uuid4().hex[:10]}"

    result = ClaimResult(
        claim_id=claim_id,
        status=ResultStatus.COMPLETED,
        member_id=submission.member_id,
        claim_category=submission.claim_category,
        currency=policy.currency,
        claimed_amount=submission.claimed_amount,
    )

    # --- intake ------------------------------------------------------------ #
    member = policy.get_member(submission.member_id)
    if member:
        trace.add("intake.member", StepStatus.PASS,
                  f"Member resolved: {member.get('name')} ({submission.member_id})",
                  {"member_id": submission.member_id})
    else:
        trace.add("intake.member", StepStatus.WARN,
                  f"Member {submission.member_id} not found in roster",
                  {"member_id": submission.member_id}, confidence_delta=-0.2)
        result.requires_manual_review = True

    # --- verification gate (may stop the pipeline) ------------------------- #
    issues = verify_documents(submission, policy, trace)
    if issues:
        result.status = ResultStatus.DOCUMENT_ISSUE
        result.decision = None
        result.document_issues = issues
        result.member_message = " ".join(i.message + " " + i.action_required for i in issues)
        result.confidence_score = round(max(BASE_CONFIDENCE + trace.total_confidence_delta(), 0.0), 2)
        result.trace = trace.steps
        return result

    # --- extraction (async, degrades on per-doc failure) ------------------- #
    extracted = await extract_claim(submission, trace)
    result.extracted = extracted

    # --- adjudication ------------------------------------------------------ #
    fallback = AdjudicationOutcome(
        decision=Decision.MANUAL_REVIEW, reasons=["ADJUDICATION_FAILED"],
        messages=["Adjudication could not complete; routed to manual review."])
    outcome, adj_failed = _safe(
        trace, "adjudication", lambda: adjudicate(submission, extracted, policy, trace),
        fallback)
    if adj_failed:
        result.degraded = True
        result.requires_manual_review = True

    # --- fraud (the simulated-failure component) --------------------------- #
    signals, fraud_failed = _safe(
        trace, "fraud.detection", lambda: detect_fraud(submission, policy, trace), [])
    result.fraud_signals = list(signals)
    if fraud_failed:
        result.degraded = True
        result.requires_manual_review = True

    # --- assemble final decision ------------------------------------------- #
    _finalize(result, outcome, signals, trace)
    result.confidence_score = round(
        min(max(BASE_CONFIDENCE + trace.total_confidence_delta(), 0.0), 1.0), 2)
    result.trace = trace.steps
    return result


def _finalize(
    result: ClaimResult,
    outcome: AdjudicationOutcome,
    signals: list[FraudSignal],
    trace: Trace,
) -> None:
    result.line_item_results = outcome.line_item_results
    result.calculation = outcome.calculation
    result.approved_amount = outcome.approved_amount
    result.reasons = list(outcome.reasons)
    messages = list(outcome.messages)

    decision = outcome.decision

    # HIGH fraud signals route a payable claim to manual review (not auto-reject).
    high = [s for s in signals if s.severity == "HIGH"]
    if high and decision in (Decision.APPROVED, Decision.PARTIAL):
        decision = Decision.MANUAL_REVIEW
        result.requires_manual_review = True
        result.reasons.extend(s.code for s in signals)
        messages.append(
            "Routed to MANUAL_REVIEW due to fraud/anomaly signals: "
            + "; ".join(s.detail for s in high)
        )
        result.approved_amount = None
        trace.add("decision.route", StepStatus.WARN,
                  "Manual review due to fraud signals",
                  {"signals": [s.model_dump() for s in high]})

    # Degraded pipeline -> keep the decision but flag for human eyes.
    if result.degraded:
        messages.append(
            "NOTE: one or more components failed during processing. Confidence is "
            "reduced and manual review is recommended due to incomplete processing."
        )
        result.requires_manual_review = True

    result.decision = decision
    result.member_message = " ".join(m for m in messages if m).strip()
