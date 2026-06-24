"""Document Verification Agent — the early-stop gate.

Runs BEFORE any extraction or adjudication. Catches three classes of problem
and produces specific, actionable, member-facing messages:

  1. MISSING_REQUIRED_DOCUMENT — a required document type for the claim
     category was not uploaded (names what was uploaded and what is missing).
  2. UNREADABLE_DOCUMENT       — a document is too poor-quality to read
     (asks to re-upload that specific file; does not reject the claim).
  3. PATIENT_MISMATCH          — documents name different patients
     (surfaces the specific names found on each document).

If any issue is found the pipeline stops here with decision = null.
"""

from __future__ import annotations

from ..models import (
    ClaimSubmission,
    DocumentIssue,
    DocumentIssueCode,
    Quality,
    StepStatus,
)
from ..policy import Policy
from ..trace import Trace


def _humanize(doc_type: str) -> str:
    return doc_type.replace("_", " ").lower()


def verify_documents(
    submission: ClaimSubmission, policy: Policy, trace: Trace
) -> list[DocumentIssue]:
    issues: list[DocumentIssue] = []
    category = submission.claim_category.value

    # required document types present
    reqs = policy.document_requirements(category)
    required = reqs["required"]
    uploaded_types = [d.actual_type.value for d in submission.documents]
    uploaded_set = set(uploaded_types)
    missing = [t for t in required if t not in uploaded_set]

    if missing:
        # Build a message that names what WAS uploaded and what is needed.
        uploaded_desc = ", ".join(
            f"{uploaded_types.count(t)} x {_humanize(t)}" for t in sorted(uploaded_set)
        )
        missing_desc = ", ".join(_humanize(t) for t in missing)
        issues.append(
            DocumentIssue(
                code=DocumentIssueCode.MISSING_REQUIRED_DOCUMENT,
                message=(
                    f"For a {category.lower()} claim we need: "
                    f"{', '.join(_humanize(t) for t in required)}. "
                    f"You uploaded {uploaded_desc}. "
                    f"Missing: {missing_desc}."
                ),
                action_required=(
                    f"Please upload the following document(s): {missing_desc}."
                ),
            )
        )
        trace.add(
            "document_verification.required_types",
            StepStatus.FAIL,
            f"Missing required document(s): {missing_desc}",
            {"required": required, "uploaded": uploaded_types, "missing": missing},
        )
    else:
        trace.add(
            "document_verification.required_types",
            StepStatus.PASS,
            "All required document types are present",
            {"required": required, "uploaded": uploaded_types},
        )

    # readability
    unreadable = [d for d in submission.documents if d.quality == Quality.UNREADABLE]
    for doc in unreadable:
        label = _humanize(doc.actual_type.value)
        issues.append(
            DocumentIssue(
                code=DocumentIssueCode.UNREADABLE_DOCUMENT,
                file_id=doc.file_id,
                message=(
                    f"The {label} you uploaded "
                    f"({doc.file_name or doc.file_id}) is too blurry/low-quality "
                    f"to read. We have NOT rejected your claim."
                ),
                action_required=(
                    f"Please re-upload a clear photo or scan of the {label}."
                ),
            )
        )
        trace.add(
            "document_verification.readability",
            StepStatus.FAIL,
            f"Document {doc.file_id} ({label}) is unreadable",
            {"file_id": doc.file_id, "quality": doc.quality.value},
        )
    if not unreadable:
        trace.add(
            "document_verification.readability",
            StepStatus.PASS,
            "All documents are legible",
        )

    # patient consistency
    names: dict[str, str] = {}  # file_id -> name as written
    for doc in submission.documents:
        name = doc.patient_name_on_doc
        if not name and doc.content:
            name = doc.content.get("patient_name")
        if name:
            names[doc.file_id] = name.strip()

    distinct = {n.lower() for n in names.values()}
    if len(distinct) > 1: # to check if the documents belong to the same patient
        listing = "; ".join(f"{fid}: '{nm}'" for fid, nm in names.items())
        issues.append(
            DocumentIssue(
                code=DocumentIssueCode.PATIENT_MISMATCH,
                message=(
                    f"The uploaded documents name different patients ({listing}). "
                    f"All documents in one claim must belong to the same patient."
                ),
                action_required=(
                    "Please ensure every document is for the same patient and "
                    "re-upload the corrected set."
                ),
            )
        )
        trace.add(
            "document_verification.patient_consistency",
            StepStatus.FAIL,
            "Documents belong to different patients",
            {"names": names},
        )
    else:
        trace.add(
            "document_verification.patient_consistency",
            StepStatus.PASS,
            "All documents reference the same patient" if names else "No patient names to cross-check",
            {"names": names},
        )

    return issues
