"""Run all 12 test cases from test_cases.json through the pipeline.

Produces a structured pass/fail per case and (optionally) writes a Markdown
eval report. Importable by the test suite; runnable as a script:

    python -m scripts.run_evals            # prints summary
    python -m scripts.run_evals --report   # also writes docs/EVAL_REPORT.md
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.models import ClaimResult, ClaimSubmission, Decision, ResultStatus  # noqa: E402
from app.orchestrator import run_claim  # noqa: E402

TEST_CASES_PATH = ROOT / "test_cases.json"


def load_cases() -> list[dict]:
    with open(TEST_CASES_PATH, "r", encoding="utf-8") as fh:
        return json.load(fh)["test_cases"]


def _confidence_ok(expected: str, actual: float) -> bool:
    # expected like "above 0.85"
    try:
        threshold = float(expected.lower().replace("above", "").strip())
        return actual > threshold
    except ValueError:
        return True


def evaluate(case: dict, result: ClaimResult) -> tuple[bool, list[str]]:
    """Return (matched, notes)."""
    exp = case["expected"]
    notes: list[str] = []
    ok = True

    # Cases that must stop at the document gate (decision == null).
    if exp.get("decision", "MISSING") is None:
        if result.status != ResultStatus.DOCUMENT_ISSUE:
            ok = False
            notes.append(f"expected early document stop, got status={result.status.value}")
        else:
            codes = {i.code for i in result.document_issues}
            notes.append(f"document issue codes: {sorted(codes)}")
        return ok, notes

    # Decision cases.
    expected_decision = exp.get("decision")
    if expected_decision and (result.decision is None
                              or result.decision.value != expected_decision):
        ok = False
        got = result.decision.value if result.decision else None
        notes.append(f"decision: expected {expected_decision}, got {got}")

    if "approved_amount" in exp:
        if result.approved_amount != exp["approved_amount"]:
            ok = False
            notes.append(
                f"approved_amount: expected {exp['approved_amount']}, "
                f"got {result.approved_amount}")

    for code in exp.get("rejection_reasons", []):
        if code not in result.reasons:
            ok = False
            notes.append(f"missing rejection reason {code} (got {result.reasons})")

    if "confidence_score" in exp:
        if not _confidence_ok(exp["confidence_score"], result.confidence_score):
            ok = False
        notes.append(
            f"confidence: expected {exp['confidence_score']}, "
            f"got {result.confidence_score}")

    return ok, notes


async def run_all() -> list[dict]:
    cases = load_cases()
    out: list[dict] = []
    for case in cases:
        submission = ClaimSubmission.model_validate(case["input"])
        result = await run_claim(submission)
        matched, notes = evaluate(case, result)
        out.append({"case": case, "result": result, "matched": matched, "notes": notes})
    return out


def _fmt_result(result: ClaimResult) -> str:
    lines = [
        f"- **Status:** {result.status.value}",
        f"- **Decision:** {result.decision.value if result.decision else 'null (stopped at document gate)'}",
        f"- **Approved amount:** {result.approved_amount if result.approved_amount is not None else '—'}",
        f"- **Confidence:** {result.confidence_score}",
        f"- **Reasons:** {result.reasons or '—'}",
        f"- **Requires manual review:** {result.requires_manual_review}",
        f"- **Member message:** {result.member_message}",
    ]
    if result.document_issues:
        lines.append("- **Document issues:**")
        for i in result.document_issues:
            lines.append(f"    - `{i.code}` {i.message} → {i.action_required}")
    if result.line_item_results:
        lines.append("- **Line items:**")
        for li in result.line_item_results:
            lines.append(
                f"    - {li.status}: {li.description} — claimed {li.claimed_amount}, "
                f"approved {li.approved_amount}"
                + (f" ({li.reason})" if li.reason else ""))
    if result.calculation:
        lines.append("- **Calculation:** "
                     + " → ".join(f"{c.label}: {c.amount}" for c in result.calculation))
    if result.fraud_signals:
        lines.append("- **Fraud signals:** "
                     + "; ".join(f"{s.code} ({s.severity})" for s in result.fraud_signals))
    lines.append("- **Trace:**")
    for s in result.trace:
        lines.append(f"    - [{s.status.value}] `{s.step}` — {s.detail}")
    return "\n".join(lines)


def write_report(results: list[dict]) -> Path:
    passed = sum(1 for r in results if r["matched"])
    total = len(results)
    md = [
        "# Eval Report",
        "",
        f"All {total} test cases from `test_cases.json` run through the live pipeline.",
        "",
        f"**Result: {passed}/{total} matched expected outcomes.**",
        "",
        "| Case | Name | Expected | Got | Match |",
        "|------|------|----------|-----|-------|",
    ]
    for r in results:
        case, res = r["case"], r["result"]
        exp = case["expected"]
        exp_dec = exp.get("decision", "—")
        exp_dec = "null (doc stop)" if exp_dec is None else exp_dec
        got = res.decision.value if res.decision else f"null ({res.status.value})"
        md.append(f"| {case['case_id']} | {case['case_name']} | {exp_dec} | {got} "
                  f"| {'✅' if r['matched'] else '❌'} |")
    md.append("")
    for r in results:
        case, res = r["case"], r["result"]
        md.append(f"## {case['case_id']} — {case['case_name']} "
                  f"{'✅' if r['matched'] else '❌'}")
        md.append("")
        md.append(f"_{case['description']}_")
        md.append("")
        md.append(_fmt_result(res))
        md.append("")
        md.append(f"**Eval notes:** {'; '.join(r['notes']) or 'exact match'}")
        md.append("")
    path = ROOT / "docs" / "EVAL_REPORT.md"
    path.write_text("\n".join(md), encoding="utf-8")
    return path


def main() -> None:
    results = asyncio.run(run_all())
    passed = sum(1 for r in results if r["matched"])
    for r in results:
        case, res = r["case"], r["result"]
        mark = "PASS" if r["matched"] else "FAIL"
        got = res.decision.value if res.decision else f"null/{res.status.value}"
        print(f"[{mark}] {case['case_id']} {case['case_name']:<40} -> {got}")
        if not r["matched"]:
            for n in r["notes"]:
                print(f"        {n}")
    print(f"\n{passed}/{len(results)} matched expected outcomes.")
    if "--report" in sys.argv:
        path = write_report(results)
        print(f"Report written to {path}")


if __name__ == "__main__":
    main()
