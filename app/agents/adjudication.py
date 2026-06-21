"""Adjudication Agent — applies policy rules to extracted data.

Checks run in a deliberate order so the FIRST blocking reason is the reported
one (matching how a human adjudicator reasons — eligibility before money):

    1. category covered
    2. blanket exclusion         (diagnosis/treatment is non-coverable)   -> REJECTED
    3. waiting period            (condition not yet eligible)             -> REJECTED
    4. pre-authorization missing (high-value imaging)                     -> REJECTED
    5. per-claim limit           (covered amount over the ceiling)        -> REJECTED
    6. line-item classification  (some items excluded)                    -> PARTIAL
    7. annual limit + financials (network discount -> co-pay -> caps)

All rule values come from the Policy object; only the keyword *mappings* that
link free-text diagnoses to policy keys live here.
"""

from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Optional

from pydantic import BaseModel, Field

from ..models import (
    CalculationStep,
    ClaimSubmission,
    Decision,
    ExtractedClaim,
    LineItem,
    LineItemResult,
    StepStatus,
)
from ..policy import Policy
from ..trace import Trace

# Free-text -> policy waiting-period key. The DAYS come from the policy file.
_WAITING_KEYWORDS: dict[str, list[str]] = {
    "diabetes": ["diabetes", "diabetic", "t2dm"],
    "hypertension": ["hypertension", "htn"],
    "thyroid_disorders": ["thyroid", "hypothyroid", "hyperthyroid"],
    "joint_replacement": ["joint replacement", "knee replacement", "arthroplasty"],
    "maternity": ["maternity", "pregnan", "obstetric", "delivery"],
    "mental_health": ["mental health", "depression", "anxiety", "psychiatric"],
    "obesity_treatment": ["obesity", "bariatric"],
    "hernia": ["hernia"],
    "cataract": ["cataract"],
}

# Free-text -> policy exclusion phrase (for blanket, diagnosis-level exclusions).
_BLANKET_EXCLUSION_KEYWORDS: dict[str, str] = {
    "self-inflicted": "Self-inflicted injuries",
    "substance abuse": "Substance abuse treatment",
    "experimental": "Experimental treatments",
    "infertility": "Infertility and assisted reproduction",
    "ivf": "Infertility and assisted reproduction",
    "obesity": "Obesity and weight loss programs",
    "weight loss": "Obesity and weight loss programs",
    "bariatric": "Bariatric surgery",
}

# Free-text -> reason, for line-item level exclusions (drives PARTIAL approvals).
_LINE_EXCLUSION_KEYWORDS: dict[str, str] = {
    "whitening": "Teeth whitening is a cosmetic procedure excluded under the policy",
    "bleaching": "Bleaching is a cosmetic procedure excluded under the policy",
    "veneer": "Veneers are a cosmetic procedure excluded under the policy",
    "orthodontic": "Orthodontic treatment is excluded under the policy",
    "braces": "Orthodontic treatment (braces) is excluded under the policy",
    "cosmetic": "Cosmetic/aesthetic procedures are excluded under the policy",
    "aesthetic": "Cosmetic/aesthetic procedures are excluded under the policy",
    "lasik": "LASIK is excluded under the policy",
    "refractive": "Refractive surgery is excluded under the policy",
    "diet": "Weight-loss/diet programs are excluded under the policy",
    "weight loss": "Weight-loss programs are excluded under the policy",
    "bariatric": "Bariatric procedures are excluded under the policy",
    "supplement": "Health supplements are excluded under the policy",
    "tonic": "Tonics are excluded under the policy",
}


class AdjudicationOutcome(BaseModel):
    decision: Decision
    approved_amount: float = 0.0
    reasons: list[str] = Field(default_factory=list)
    messages: list[str] = Field(default_factory=list)
    line_item_results: list[LineItemResult] = Field(default_factory=list)
    calculation: list[CalculationStep] = Field(default_factory=list)


def _text_blob(submission: ClaimSubmission, extracted: ExtractedClaim) -> str:
    parts = [extracted.diagnosis or "", extracted.treatment or ""]
    parts.extend(li.description for li in extracted.line_items)
    return " ".join(parts).lower()


def _match_blanket_exclusion(diagnosis: str, treatment: str) -> Optional[str]:
    blob = f"{diagnosis} {treatment}".lower()
    for keyword, phrase in _BLANKET_EXCLUSION_KEYWORDS.items():
        if keyword in blob:
            return phrase
    return None


def _waiting_condition(diagnosis: str) -> Optional[str]:
    """Match on whole words so e.g. 'disc herniation' does not trip 'hernia'."""
    blob = diagnosis.lower()
    for key, keywords in _WAITING_KEYWORDS.items():
        for k in keywords:
            if re.search(rf"\b{re.escape(k)}\b", blob):
                return key
    return None


def _detect_preauth_tests(
    tests: list[str], items: list[LineItem], policy: Policy
) -> list[str]:
    high_value = policy.category_config("diagnostic").get(
        "high_value_tests_requiring_pre_auth", []
    )
    tokens = {name.split()[0].lower() for name in high_value}  # mri, ct, pet
    haystack = [t.lower() for t in tests] + [li.description.lower() for li in items]
    found = []
    for name in high_value:
        token = name.split()[0].lower()
        if any(token in h for h in haystack):
            found.append(name)
    return found


def _line_item_exclusion(category: str, description: str, policy: Policy) -> Optional[str]:
    desc = description.lower()
    if category == "DENTAL":
        for proc in policy.category_config("dental").get("excluded_procedures", []):
            if proc.lower() in desc:
                return f"{proc} is excluded under the dental policy"
    if category == "VISION":
        for item in policy.category_config("vision").get("excluded_items", []):
            if item.lower() in desc:
                return f"{item} is excluded under the vision policy"
    for keyword, reason in _LINE_EXCLUSION_KEYWORDS.items():
        if keyword in desc:
            return reason
    return None


def _reject(
    outcome_reason: str, message: str, trace: Trace, step: str, data: dict
) -> AdjudicationOutcome:
    trace.add(step, StepStatus.FAIL, message, data)
    return AdjudicationOutcome(
        decision=Decision.REJECTED, approved_amount=0.0,
        reasons=[outcome_reason], messages=[message],
    )


def adjudicate(
    submission: ClaimSubmission,
    extracted: ExtractedClaim,
    policy: Policy,
    trace: Trace,
) -> AdjudicationOutcome:
    category = submission.claim_category.value
    cfg = policy.category_config(category)
    diagnosis = extracted.diagnosis or ""
    treatment = extracted.treatment or ""
    claimed = submission.claimed_amount

    # 1. category covered ---------------------------------------------------- #
    if not cfg.get("covered", False):
        return _reject(
            "CATEGORY_NOT_COVERED",
            f"The {category.lower()} category is not covered under this policy.",
            trace, "adjudication.coverage", {"category": category},
        )
    trace.add("adjudication.coverage", StepStatus.PASS,
              f"{category.title()} is a covered category", {"category": category})

    # 2. blanket exclusion --------------------------------------------------- #
    excl = _match_blanket_exclusion(diagnosis, treatment)
    if excl:
        msg = (
            f"This claim is for an excluded condition. Diagnosis/treatment "
            f"('{diagnosis or treatment}') falls under the policy exclusion: "
            f"'{excl}'. Excluded conditions are not payable."
        )
        return _reject("EXCLUDED_CONDITION", msg, trace, "adjudication.exclusion",
                       {"matched_exclusion": excl, "diagnosis": diagnosis,
                        "treatment": treatment})
    trace.add("adjudication.exclusion", StepStatus.PASS,
              "No blanket policy exclusion matched", {"diagnosis": diagnosis})

    # 3. waiting period ------------------------------------------------------ #
    join = policy.member_join_date(submission.member_id)
    wp = policy.waiting_periods
    if join:
        initial = wp.get("initial_waiting_period_days", 0)
        if submission.treatment_date < join + timedelta(days=initial):
            eligible = join + timedelta(days=initial)
            msg = (
                f"Claim falls within the initial {initial}-day waiting period. "
                f"You are eligible for claims from {eligible.isoformat()}."
            )
            return _reject("WAITING_PERIOD", msg, trace, "adjudication.waiting_period",
                           {"type": "initial", "eligible_from": eligible.isoformat()})

        condition = _waiting_condition(diagnosis)
        if condition:
            days = wp.get("specific_conditions", {}).get(condition)
            if days:
                eligible = join + timedelta(days=days)
                if submission.treatment_date < eligible:
                    pretty = condition.replace("_", " ")
                    msg = (
                        f"Claim falls within the {days}-day waiting period for "
                        f"{pretty}. The member joined on {join.isoformat()} and is "
                        f"eligible for {pretty}-related claims from "
                        f"{eligible.isoformat()}."
                    )
                    return _reject("WAITING_PERIOD", msg, trace,
                                   "adjudication.waiting_period",
                                   {"type": condition, "waiting_days": days,
                                    "join_date": join.isoformat(),
                                    "eligible_from": eligible.isoformat()})
    trace.add("adjudication.waiting_period", StepStatus.PASS,
              "No waiting-period restriction applies",
              {"join_date": join.isoformat() if join else None})

    # 4. pre-authorization --------------------------------------------------- #
    preauth_tests = _detect_preauth_tests(extracted.tests_ordered,
                                           extracted.line_items, policy)
    if preauth_tests:
        threshold = cfg.get("pre_auth_threshold", 0)
        needs = any("pet" in t.lower() for t in preauth_tests) or claimed > threshold
        if needs:  # no pre-auth reference was supplied with the claim
            tests_str = ", ".join(preauth_tests)
            msg = (
                f"Pre-authorization was required for {tests_str} "
                f"(amount ₹{claimed:,.0f} exceeds the ₹{threshold:,.0f} threshold) "
                f"but was not obtained. To resubmit: obtain pre-authorization from "
                f"the insurer before the procedure and attach the approval reference."
            )
            return _reject("PRE_AUTH_MISSING", msg, trace,
                           "adjudication.pre_authorization",
                           {"tests": preauth_tests, "threshold": threshold,
                            "amount": claimed})
    trace.add("adjudication.pre_authorization", StepStatus.PASS,
              "No pre-authorization requirement triggered",
              {"high_value_tests": preauth_tests})

    # --- line-item classification (needed for per-claim + partial) --------- #
    items = extracted.line_items
    line_results: list[LineItemResult] = []
    covered_total = 0.0
    excluded_count = 0
    for li in items:
        reason = _line_item_exclusion(category, li.description, policy)
        if reason:
            excluded_count += 1
            line_results.append(LineItemResult(
                description=li.description, claimed_amount=li.amount,
                approved_amount=0.0, status="REJECTED", reason=reason))
        else:
            covered_total += li.amount
            line_results.append(LineItemResult(
                description=li.description, claimed_amount=li.amount,
                approved_amount=li.amount, status="APPROVED"))

    if not items:
        covered_total = extracted.total if extracted.total is not None else claimed

    # If every line item is excluded, the whole claim is non-coverable.
    if items and excluded_count == len(items):
        msg = "All claimed line items are excluded under the policy."
        trace.add("adjudication.line_items", StepStatus.FAIL, msg,
                  {"line_items": [r.model_dump() for r in line_results]})
        return AdjudicationOutcome(
            decision=Decision.REJECTED, approved_amount=0.0,
            reasons=["EXCLUDED_CONDITION"], messages=[msg],
            line_item_results=line_results)

    # 5. per-claim limit ----------------------------------------------------- #
    cap = policy.effective_claim_cap(category)
    if covered_total > cap:
        msg = (
            f"The claimed amount of ₹{claimed:,.0f} exceeds the per-claim limit of "
            f"₹{cap:,.0f} for {category.lower()} claims. The claim cannot be approved."
        )
        trace.add("adjudication.per_claim_limit", StepStatus.FAIL, msg,
                  {"claimed": claimed, "covered_total": covered_total, "limit": cap})
        return AdjudicationOutcome(
            decision=Decision.REJECTED, approved_amount=0.0,
            reasons=["PER_CLAIM_EXCEEDED"], messages=[msg],
            line_item_results=line_results)
    trace.add("adjudication.per_claim_limit", StepStatus.PASS,
              f"Within per-claim limit (₹{covered_total:,.0f} ≤ ₹{cap:,.0f})",
              {"covered_total": covered_total, "limit": cap})

    # 6 & 7. financials: network discount -> co-pay -> caps ----------------- #
    calc: list[CalculationStep] = [CalculationStep(label="Covered amount", amount=covered_total)]
    running = covered_total

    if policy.is_network_hospital(submission.hospital_name):
        pct = cfg.get("network_discount_percent", 0)
        if pct:
            discount = round(running * pct / 100, 2)
            running = round(running - discount, 2)
            calc.append(CalculationStep(label=f"Network discount ({pct}%)", amount=-discount))
            calc.append(CalculationStep(label="After network discount", amount=running))

    copay_pct = cfg.get("copay_percent", 0)
    if copay_pct:
        copay = round(running * copay_pct / 100, 2)
        running = round(running - copay, 2)
        calc.append(CalculationStep(label=f"Co-pay ({copay_pct}%)", amount=-copay))

    # annual OPD limit
    remaining_annual = policy.annual_opd_limit() - submission.ytd_claims_amount
    if remaining_annual >= 0 and running > remaining_annual:
        calc.append(CalculationStep(label="Capped at remaining annual OPD limit",
                                    amount=remaining_annual))
        running = remaining_annual

    approved = round(max(running, 0.0), 2)
    calc.append(CalculationStep(label="Final approved amount", amount=approved))

    decision = Decision.PARTIAL if excluded_count else Decision.APPROVED
    if decision == Decision.PARTIAL:
        rejected = [r.description for r in line_results if r.status == "REJECTED"]
        message = (
            f"Partially approved. Approved ₹{approved:,.0f}. "
            f"Excluded line item(s): {', '.join(rejected)}. See itemized breakdown."
        )
        reasons = ["PARTIAL_EXCLUSION"]
    else:
        message = f"Approved for ₹{approved:,.0f}."
        reasons = []

    trace.add("adjudication.decision", StepStatus.PASS,
              f"{decision.value}: approved ₹{approved:,.0f}",
              {"calculation": [c.model_dump() for c in calc]})

    return AdjudicationOutcome(
        decision=decision, approved_amount=approved, reasons=reasons,
        messages=[message], line_item_results=line_results, calculation=calc)
