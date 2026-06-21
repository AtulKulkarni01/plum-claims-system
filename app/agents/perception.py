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
from ..models import ClaimSubmission, Quality, StepStatus
from ..trace import Trace


async def perceive(submission: ClaimSubmission, trace: Trace) -> None:
    # Only real uploads (image/text) that aren't already structured, and only
    # when a vision provider is configured.
    targets = [
        d for d in submission.documents
        if d.content is None and (d.image_base64 or d.text) and llm_available()
    ]
    if not targets:
        return

    async def _read(doc) -> None:
        try:
            res = await extract_fields(
                doc.actual_type.value, raw_text=doc.text, image_base64=doc.image_base64
            )
        except ExtractionError as exc:
            # Could not read it at all -> treat as unreadable so the gate asks the
            # member to re-upload that specific document (never a wrong decision).
            doc.quality = Quality.UNREADABLE
            trace.add(
                "perception.read", StepStatus.WARN,
                f"{doc.file_id}: could not be read ({exc}); flagged for re-upload",
                {"file_id": doc.file_id, "error": str(exc)},
                confidence_delta=-0.15,
            )
            return

        fields = res.fields
        if fields.get("legible") is False:
            doc.quality = Quality.UNREADABLE
        doc.content = fields
        if fields.get("patient_name") and not doc.patient_name_on_doc:
            doc.patient_name_on_doc = fields["patient_name"]
        trace.add(
            "perception.read",
            StepStatus.WARN if doc.quality == Quality.UNREADABLE else StepStatus.PASS,
            f"{doc.file_id}: read via {res.provider}"
            + (" [UNREADABLE]" if doc.quality == Quality.UNREADABLE else ""),
            {"file_id": doc.file_id, "provider": res.provider,
             "legible": fields.get("legible", True)},
        )

    await asyncio.gather(*[_read(d) for d in targets])
