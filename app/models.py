"""Pydantic data models for the claims processing system.

These models are the contracts between every component in the pipeline.
Inputs are validated at the system boundary (the API). Internal agents pass
typed objects, never loose dicts, so a malformed value fails fast and loud.
"""

from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator


class ClaimCategory(str, Enum):
    CONSULTATION = "CONSULTATION"
    DIAGNOSTIC = "DIAGNOSTIC"
    PHARMACY = "PHARMACY"
    DENTAL = "DENTAL"
    VISION = "VISION"
    ALTERNATIVE_MEDICINE = "ALTERNATIVE_MEDICINE"


class DocumentType(str, Enum):
    PRESCRIPTION = "PRESCRIPTION"
    HOSPITAL_BILL = "HOSPITAL_BILL"
    PHARMACY_BILL = "PHARMACY_BILL"
    LAB_REPORT = "LAB_REPORT"
    DIAGNOSTIC_REPORT = "DIAGNOSTIC_REPORT"
    DISCHARGE_SUMMARY = "DISCHARGE_SUMMARY"
    DENTAL_REPORT = "DENTAL_REPORT"


class Quality(str, Enum):
    GOOD = "GOOD"
    FAIR = "FAIR"
    POOR = "POOR"
    UNREADABLE = "UNREADABLE"


class Decision(str, Enum):
    APPROVED = "APPROVED"
    PARTIAL = "PARTIAL"
    REJECTED = "REJECTED"
    MANUAL_REVIEW = "MANUAL_REVIEW"


class ResultStatus(str, Enum):
    """Lifecycle of a claim result: IN_PROGRESS until a terminal state is reached —
    COMPLETED (a decision was produced) or DOCUMENT_ISSUE (stopped at the gate,
    decision is null)."""

    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    DOCUMENT_ISSUE = "DOCUMENT_ISSUE"


class StepStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    WARN = "WARN"
    SKIP = "SKIP"
    INFO = "INFO"
    ERROR = "ERROR"


class ExtractionSource(str, Enum):
    """Where a document's structured fields came from."""

    PROVIDED = "PROVIDED"   # already-structured content (eval harness / JSON)
    LLM = "LLM"             # read by the vision/text LLM (see ExtractedDocument.provider)
    DEGRADED = "DEGRADED"   # could not be extracted; pipeline continues degraded


class LineItemStatus(str, Enum):
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class FraudSeverity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class DocumentIssueCode(str, Enum):
    MISSING_REQUIRED_DOCUMENT = "MISSING_REQUIRED_DOCUMENT"
    UNREADABLE_DOCUMENT = "UNREADABLE_DOCUMENT"
    PATIENT_MISMATCH = "PATIENT_MISMATCH"


class LineItem(BaseModel):
    description: str
    amount: float


class InputDocument(BaseModel):
    """A single uploaded document. `content` carries already-structured fields
    (as the eval harness provides). `text` / `image_base64` carry raw payloads
    that the extraction agent would run an LLM/OCR over when content is absent."""

    file_id: str
    file_name: Optional[str] = None
    actual_type: DocumentType
    quality: Quality = Quality.GOOD
    patient_name_on_doc: Optional[str] = None
    content: Optional[dict[str, Any]] = None
    text: Optional[str] = None
    image_base64: Optional[str] = None
    mime_type: Optional[str] = None  # e.g. image/jpeg, image/png, application/pdf


class ClaimHistoryEntry(BaseModel):
    claim_id: Optional[str] = None
    date: date
    amount: float
    provider: Optional[str] = None


class ClaimSubmission(BaseModel):
    """The full claim as submitted by a member. Validated at the API boundary."""

    member_id: str
    policy_id: str
    claim_category: ClaimCategory
    treatment_date: date
    claimed_amount: float = Field(gt=0)
    hospital_name: Optional[str] = None
    ytd_claims_amount: float = 0.0
    claims_history: list[ClaimHistoryEntry] = Field(default_factory=list)
    simulate_component_failure: bool = False
    documents: list[InputDocument] = Field(default_factory=list)

    @field_validator("documents")
    @classmethod
    def _at_least_one_document(cls, v: list[InputDocument]) -> list[InputDocument]:
        if not v:
            raise ValueError("a claim must include at least one document")
        return v


# --------------------------------------------------------------------------- #
# Observability
# --------------------------------------------------------------------------- #
class TraceStep(BaseModel):
    """One auditable event. The ordered list of these IS the explanation of a
    decision — operations can reconstruct exactly what happened from them."""

    step: str
    status: StepStatus
    detail: str
    data: dict[str, Any] = Field(default_factory=dict)
    confidence_delta: float = 0.0


# --------------------------------------------------------------------------- #
# Document-issue (early-stop) models
# --------------------------------------------------------------------------- #
class DocumentIssue(BaseModel):
    code: DocumentIssueCode
    file_id: Optional[str] = None
    message: str  # specific, member-facing
    action_required: str  # exactly what the member should do next


# --------------------------------------------------------------------------- #
# Extraction output
# --------------------------------------------------------------------------- #
class ExtractedDocument(BaseModel):
    file_id: str
    doc_type: DocumentType
    source: ExtractionSource
    provider: Optional[str] = None  # which LLM provider, when source == LLM
    patient_name: Optional[str] = None
    doctor_name: Optional[str] = None
    doctor_registration: Optional[str] = None
    diagnosis: Optional[str] = None
    treatment: Optional[str] = None
    hospital_name: Optional[str] = None
    line_items: list[LineItem] = Field(default_factory=list)
    total: Optional[float] = None
    tests_ordered: list[str] = Field(default_factory=list)
    medicines: list[str] = Field(default_factory=list)
    date: Optional[str] = None
    warnings: list[str] = Field(default_factory=list)
    low_confidence_fields: list[str] = Field(default_factory=list)
    alterations: list[str] = Field(default_factory=list)
    duplicate_stamps: list[str] = Field(default_factory=list)
    registration_valid: Optional[bool] = None


class ExtractedClaim(BaseModel):
    """Merged view across all documents — what the adjudicator reasons over."""

    patient_name: Optional[str] = None
    diagnosis: Optional[str] = None
    treatment: Optional[str] = None
    doctor_registration: Optional[str] = None
    hospital_name: Optional[str] = None
    line_items: list[LineItem] = Field(default_factory=list)
    total: Optional[float] = None
    tests_ordered: list[str] = Field(default_factory=list)
    medicines: list[str] = Field(default_factory=list)
    documents: list[ExtractedDocument] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# Decision output
# --------------------------------------------------------------------------- #
class LineItemResult(BaseModel):
    description: str
    claimed_amount: float
    approved_amount: float
    status: LineItemStatus
    reason: Optional[str] = None


class CalculationStep(BaseModel):
    label: str
    amount: float


class FraudSignal(BaseModel):
    code: str
    detail: str
    severity: FraudSeverity


class ClaimResult(BaseModel):
    """The single object returned to the UI / ops team for any submission."""

    claim_id: str
    status: ResultStatus = ResultStatus.IN_PROGRESS
    decision: Optional[Decision] = None
    member_id: str
    claim_category: ClaimCategory
    currency: str = "INR"

    claimed_amount: float = 0.0
    approved_amount: Optional[float] = None

    reasons: list[str] = Field(default_factory=list)  # machine codes
    member_message: str = ""  # human-facing summary

    document_issues: list[DocumentIssue] = Field(default_factory=list)
    line_item_results: list[LineItemResult] = Field(default_factory=list)
    calculation: list[CalculationStep] = Field(default_factory=list)
    fraud_signals: list[FraudSignal] = Field(default_factory=list)

    confidence_score: float = 0.0
    degraded: bool = False
    requires_manual_review: bool = False

    extracted: Optional[ExtractedClaim] = None
    trace: list[TraceStep] = Field(default_factory=list)
