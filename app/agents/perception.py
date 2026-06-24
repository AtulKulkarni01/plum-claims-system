"""Perception stage — read real uploaded documents into structured fields.

Runs BEFORE the verification gate. For any document that arrives as a raw upload
(an image / raw text) with no structured `content`, it calls the vision LLM
(Gemini primary, OpenAI fallback) to read the document into `content`, pull out
the patient name, and judge whether it is legible — so the gate and the rest of
the pipeline work off data DERIVED from the actual document, not metadata.

Documents that already carry `content` (the eval harness) are passed through
untouched, so the deterministic eval path is unaffected and needs no API key.
"""

from __future__ import annotations

import asyncio

from ..llm import ExtractionError, extract_fields, llm_available
from ..models import ClaimSubmission, InputDocument, Quality, StepStatus
from ..trace import Trace


async def perceive(submission: ClaimSubmission, trace: Trace) -> ClaimSubmission:
    """Read raw uploads into structured fields. Returns a NEW submission with the
    enriched documents; the input is never mutated in place."""
    # Only real uploads (image/text) that aren't already structured, and only
    # when a vision provider is configured.
    targets = [
        d for d in submission.documents
        if d.content is None and (d.image_base64 or d.text) and llm_available()
    ]
    if not targets:
        return submission

    async def _read(doc: InputDocument) -> InputDocument:
        try:
            res = await extract_fields(
                doc.actual_type.value, raw_text=doc.text,
                image_base64=doc.image_base64, mime_type=doc.mime_type,
            )
        except ExtractionError as exc:
            # Could not read it at all -> treat as unreadable so the gate asks the
            # member to re-upload that specific document (never a wrong decision).
            trace.add(
                "perception.read", StepStatus.WARN,
                f"{doc.file_id}: could not be read ({exc}); flagged for re-upload",
                {"file_id": doc.file_id, "error": str(exc)},
                confidence_delta=-0.15,
            )
            return doc.model_copy(update={"quality": Quality.UNREADABLE})

        fields = res.fields
        unreadable = fields.get("legible") is False
        updates: dict = {"content": fields}
        if unreadable:
            updates["quality"] = Quality.UNREADABLE
        if fields.get("patient_name") and not doc.patient_name_on_doc:
            updates["patient_name_on_doc"] = fields["patient_name"]
        trace.add(
            "perception.read",
            StepStatus.WARN if unreadable else StepStatus.PASS,
            f"{doc.file_id}: read via {res.provider}"
            + (" [UNREADABLE]" if unreadable else ""),
            {"file_id": doc.file_id, "provider": res.provider,
             "legible": fields.get("legible", True)},
        )
        return doc.model_copy(update=updates)

    enriched = await asyncio.gather(*[_read(d) for d in targets])
    by_id = {d.file_id: d for d in enriched}
    new_docs = [by_id.get(d.file_id, d) for d in submission.documents]
    return submission.model_copy(update={"documents": new_docs})
