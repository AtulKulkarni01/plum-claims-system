"""Extraction Agent — turns documents into structured, typed fields.

Per-document strategy (in priority order):
  1. `content` present  -> use it directly (source = PROVIDED).
  2. raw `text`/`image` -> run the LLM adapter, validate (source = LLM).
  3. nothing usable / LLM failure -> emit an empty record flagged DEGRADED
     and record a warning. The pipeline continues with reduced confidence.

Documents are extracted concurrently with asyncio.gather — this is the one
place real latency lives (LLM/OCR I/O), so it is where async matters.
"""

from __future__ import annotations

import asyncio
from typing import Any

from ..llm import ExtractionError, extract_fields, llm_available, parse_json_fields
from ..models import (
    ClaimSubmission,
    DocumentType,
    ExtractedClaim,
    ExtractedDocument,
    InputDocument,
    LineItem,
    StepStatus,
)
from ..trace import Trace


def _line_items(raw: Any) -> list[LineItem]:
    items: list[LineItem] = []
    for li in raw or []:
        try:
            items.append(LineItem(description=li["description"], amount=float(li["amount"])))
        except (KeyError, TypeError, ValueError):
            continue
    return items


def _from_content(doc: InputDocument, content: dict[str, Any], source: str) -> ExtractedDocument:
    return ExtractedDocument(
        file_id=doc.file_id,
        doc_type=doc.actual_type,
        source=source,
        patient_name=content.get("patient_name") or doc.patient_name_on_doc,
        doctor_name=content.get("doctor_name"),
        doctor_registration=content.get("doctor_registration"),
        diagnosis=content.get("diagnosis"),
        treatment=content.get("treatment"),
        hospital_name=content.get("hospital_name"),
        line_items=_line_items(content.get("line_items")),
        total=content.get("total"),
        tests_ordered=list(content.get("tests_ordered", []) or []),
        medicines=list(content.get("medicines", []) or []),
        date=content.get("date"),
        warnings=list(content.get("unreadable_fields", []) or []),
    )


async def _extract_one(doc: InputDocument) -> ExtractedDocument:
    if doc.content:
        return _from_content(doc, doc.content, "PROVIDED")

    raw = doc.text
    if raw:
        as_json = parse_json_fields(raw)
        if as_json is not None:
            return _from_content(doc, as_json, "PROVIDED")

    # Raw text and/or an image plus an available model -> LLM extraction
    # (Gemini primary, OpenAI fallback, with retry/backoff inside extract_fields).
    if (raw or doc.image_base64) and llm_available():
        res = await extract_fields(  # may raise ExtractionError (all providers down)
            doc.actual_type.value, raw_text=raw, image_base64=doc.image_base64
        )
        ed = _from_content(doc, res.fields, f"LLM:{res.provider}")
        ed.warnings.extend(res.attempts)  # record any retries / failovers
        return ed

    # Nothing structured and no LLM available -> degraded, but do not crash.
    return ExtractedDocument(
        file_id=doc.file_id,
        doc_type=doc.actual_type,
        source="DEGRADED",
        patient_name=doc.patient_name_on_doc,
        warnings=["no structured content and no extractor available"],
    )


async def extract_claim(
    submission: ClaimSubmission, trace: Trace
) -> ExtractedClaim:
    async def _safe(doc: InputDocument) -> ExtractedDocument:
        # Catch broadly: a malformed `content` payload (e.g. a non-numeric amount)
        # raises ValidationError, not ExtractionError. The pipeline must degrade,
        # never crash — so any failure here becomes a DEGRADED document.
        try:
            ed = await _extract_one(doc)
        except Exception as exc:  # noqa: BLE001 - resilience by design
            trace.add(
                "extraction.document",
                StepStatus.WARN,
                f"Extraction failed for {doc.file_id}; continuing degraded",
                {"file_id": doc.file_id, "error": str(exc),
                 "error_type": type(exc).__name__},
                confidence_delta=-0.15,
            )
            return ExtractedDocument(
                file_id=doc.file_id, doc_type=doc.actual_type, source="DEGRADED",
                warnings=[f"extraction error: {exc}"],
            )
        # Surface which LLM provider was used and any failover/retry in the trace.
        if ed.source.startswith("LLM"):
            trace.add(
                "extraction.llm",
                StepStatus.WARN if ed.warnings else StepStatus.PASS,
                f"{doc.file_id}: extracted via {ed.source}"
                + (" after retry/failover" if ed.warnings else ""),
                {"file_id": doc.file_id, "provider": ed.source,
                 "failover_log": ed.warnings},
            )
        return ed

    docs = await asyncio.gather(*[_safe(d) for d in submission.documents])

    # Merge into a single claim-level view. Bills contribute line items/totals;
    # prescriptions contribute clinical context.
    bill_types = {DocumentType.HOSPITAL_BILL, DocumentType.PHARMACY_BILL}
    merged = ExtractedClaim(documents=list(docs))
    for d in docs:
        merged.patient_name = merged.patient_name or d.patient_name
        merged.diagnosis = merged.diagnosis or d.diagnosis
        merged.treatment = merged.treatment or d.treatment
        merged.doctor_registration = merged.doctor_registration or d.doctor_registration
        merged.hospital_name = merged.hospital_name or d.hospital_name
        merged.tests_ordered.extend(d.tests_ordered)
        merged.medicines.extend(d.medicines)
        if d.line_items:
            merged.line_items.extend(d.line_items)
        # Only bills carry a payable total; a stray total on a prescription/lab
        # report must not be added (it would double-count the claim amount).
        if d.total is not None and d.doc_type in bill_types:
            merged.total = (merged.total or 0) + d.total

    degraded = [d.file_id for d in docs if d.source == "DEGRADED"]
    status = StepStatus.WARN if degraded else StepStatus.PASS
    trace.add(
        "extraction.summary",
        status,
        f"Extracted {len(docs)} document(s)"
        + (f"; degraded: {degraded}" if degraded else ""),
        {
            "sources": {d.file_id: d.source for d in docs},
            "diagnosis": merged.diagnosis,
            "line_item_count": len(merged.line_items),
        },
        # Degraded documents reduce confidence so a failed extraction cannot
        # quietly back a high-confidence decision.
        confidence_delta=-0.1 * len(degraded),
    )
    return merged
