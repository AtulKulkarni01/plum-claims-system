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

import asyncio
import logging
import uuid
from typing import Callable, Optional, TypeVar

from .agents.adjudication import AdjudicationOutcome, adjudicate
from .agents.document_verification import verify_documents
from .agents.extraction import extract_claim
from .agents.fraud import detect_fraud
from .agents.perception import perceive
from .models import (
    ClaimResult,
    ClaimSubmission,
    Decision,
    ExtractionSource,
    FraudSeverity,
    FraudSignal,
    ResultStatus,
    StepStatus,
)
from .policy import Policy, get_policy
from .trace import Trace

logger = logging.getLogger(__name__)

T = TypeVar("T")

BASE_CONFIDENCE = 0.95
COMPONENT_FAILURE_PENALTY = -0.35
MANUAL_REVIEW_PENALTY = -0.1  # a routed-to-human claim is, by definition, less certain


def _safe(
    trace: Trace, step: str, fn: Callable[[], T], default: T
) -> tuple[T, bool]:
    """Run fn; on any exception record it and return (default, failed=True)."""
    try:
        return fn(), False
    except Exception as exc:  # noqa: BLE001 - resilience is the whole point
        logger.error("Component '%s' failed and was skipped: %s", step, exc, exc_info=True)
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
    logger.info("Claim %s intake: member=%s category=%s amount=%s",
                claim_id, submission.member_id, submission.claim_category.value,
                submission.claimed_amount)

    result = ClaimResult(
        claim_id=claim_id,
        status=ResultStatus.IN_PROGRESS,
        member_id=submission.member_id,
        claim_category=submission.claim_category,
        currency=policy.currency,
        claimed_amount=submission.claimed_amount,
    )

    # The submitted policy_id must match the policy this system is configured with.
    if submission.policy_id != policy.policy_id:
        trace.add("intake.policy", StepStatus.WARN,
                  f"Submitted policy_id '{submission.policy_id}' does not match the "
                  f"configured policy '{policy.policy_id}'",
                  {"submitted": submission.policy_id, "configured": policy.policy_id},
                  confidence_delta=-0.2)
        result.requires_manual_review = True
    else:
        trace.add("intake.policy", StepStatus.PASS,
                  f"Policy {policy.policy_id} resolved",
                  {"policy_id": policy.policy_id})

    member = policy.get_member(submission.member_id)
    if member:
        trace.add("intake.member", StepStatus.PASS,
                  f"Member resolved: {member.get('name')} ({submission.member_id})",
                  {"member_id": submission.member_id})
    else:
        trace.add("intake.member", StepStatus.WARN,
                  f"Member {submission.member_id} not found in roster",
                  {"member_id": submission.member_id}, confidence_delta=-0.2)
        result.requires_manual_review = True # if member is not found in the roster, we need to manually review the claim

    # perception - read any uploaded document images into structured fields first
    # (returns a new submission with enriched documents; input is not mutated)
    submission = await perceive(submission, trace)

    # verification gate - may stop the pipeline for faulty / missing documents
    issues = verify_documents(submission, policy, trace)
    if issues:
        result.status = ResultStatus.DOCUMENT_ISSUE
        result.decision = None
        result.document_issues = issues
        result.member_message = " ".join(i.message + " " + i.action_required for i in issues)
        result.confidence_score = round(max(BASE_CONFIDENCE + trace.total_confidence_delta(), 0.0), 2)
        result.trace = trace.steps
        return result

    # extraction - async, degrades on per-doc failure
    extracted = await extract_claim(submission, trace)
    result.extracted = extracted

    # a document we could not read means we'd be deciding on unverified data ->
    # flag for a human rather than silently trusting the claimed amount
    if any(d.source == ExtractionSource.DEGRADED for d in extracted.documents):
        result.degraded = True
        result.requires_manual_review = True

    # Adjudication and fraud detection are independent, so run them concurrently.
    # Each writes to its OWN trace (Trace is not concurrency-safe), then we merge
    # in a stable order so the combined trace reads adjudication-then-fraud.
    adj_trace, fraud_trace = Trace(), Trace()
    fallback = AdjudicationOutcome(
        decision=Decision.MANUAL_REVIEW, reasons=["ADJUDICATION_FAILED"],
        messages=["Adjudication could not complete; routed to manual review."])

    (outcome, adj_failed), (signals, fraud_failed) = await asyncio.gather(
        asyncio.to_thread(
            _safe, adj_trace, "adjudication",
            lambda: adjudicate(submission, extracted, policy, adj_trace), fallback),
        asyncio.to_thread(
            _safe, fraud_trace, "fraud.detection",
            lambda: detect_fraud(submission, policy, fraud_trace), []),
    )
    trace.merge(adj_trace)
    trace.merge(fraud_trace)

    result.fraud_signals = list(signals)
    if adj_failed or fraud_failed:
        result.degraded = True
        result.requires_manual_review = True

    # assemble final decision
    _finalize(result, outcome, signals, trace, policy, member is not None)
    result.status = ResultStatus.COMPLETED
    result.confidence_score = round(
        min(max(BASE_CONFIDENCE + trace.total_confidence_delta(), 0.0), 1.0), 2)
    result.trace = trace.steps
    logger.info("Claim %s decision=%s approved=%s confidence=%s",
                claim_id, result.decision.value if result.decision else None,
                result.approved_amount, result.confidence_score)
    return result


def _finalize(
    result: ClaimResult,
    outcome: AdjudicationOutcome,
    signals: list[FraudSignal],
    trace: Trace,
    policy: Policy,
    member_known: bool,
) -> None:
    result.line_item_results = outcome.line_item_results
    result.calculation = outcome.calculation
    result.approved_amount = outcome.approved_amount
    result.reasons = list(outcome.reasons)
    messages = list(outcome.messages)
    decision = outcome.decision
    payable = decision in (Decision.APPROVED, Decision.PARTIAL)

    def route(code: Optional[str], message: str, detail: str, data: dict) -> None:
        """Send a payable claim to MANUAL_REVIEW (never auto-reject)."""
        nonlocal decision
        decision = Decision.MANUAL_REVIEW
        result.requires_manual_review = True
        if code and code not in result.reasons:
            result.reasons.append(code)
        messages.append(message)
        result.approved_amount = None
        # Routing to a human means the automated path was not conclusive — reflect
        # that with a confidence penalty so MANUAL_REVIEW never reads as certain.
        trace.add("decision.route", StepStatus.WARN, detail, data,
                  confidence_delta=MANUAL_REVIEW_PENALTY)

    # HIGH fraud signals route a payable claim to manual review.
    high = [s for s in signals if s.severity == FraudSeverity.HIGH]
    if payable and high:
        result.reasons.extend(s.code for s in signals)
        route(None,
              "Routed to MANUAL_REVIEW due to fraud/anomaly signals: "
              + "; ".join(s.detail for s in high),
              "Manual review due to fraud signals",
              {"signals": [s.model_dump() for s in high]})
        payable = False

    # High-value claims need human eyes even if fraud detection itself failed.
    threshold = policy.fraud_thresholds.get("auto_manual_review_above")
    if payable and threshold and result.claimed_amount > threshold:
        route("HIGH_VALUE_CLAIM",
              f"Routed to MANUAL_REVIEW: claimed ₹{result.claimed_amount:,.0f} "
              f"exceeds the ₹{threshold:,.0f} auto-review threshold.",
              "Manual review due to high claim value",
              {"threshold": threshold, "claimed": result.claimed_amount})
        payable = False

    # Unverified member -> eligibility can't be trusted; send to a human.
    if payable and not member_known:
        route("MEMBER_NOT_FOUND",
              "Routed to MANUAL_REVIEW: member could not be verified against the roster.",
              "Manual review due to unverified member",
              {"member_id": result.member_id})
        payable = False

    # Degraded pipeline -> keep the decision but flag for human eyes.
    if result.degraded:
        messages.append(
            "NOTE: one or more components failed during processing. Confidence is "
            "reduced and manual review is recommended due to incomplete processing."
        )
        result.requires_manual_review = True

    result.decision = decision
    result.member_message = " ".join(m for m in messages if m).strip()
