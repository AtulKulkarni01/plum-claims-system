"""Optional LLM adapter for document extraction.

The eval harness supplies already-structured `content` for every document, so the
system is fully functional and deterministic with NO API key. When a real,
unstructured document arrives (raw `text` or an image) and ANTHROPIC_API_KEY is
set, this adapter asks Claude to extract fields into a strict JSON schema, which
is then validated by Pydantic. Any failure raises ExtractionError so the caller
can degrade gracefully rather than trust unvalidated output.

This keeps AI use thoughtful: structured, validated, and failure-aware — without
making the reviewer depend on network access or secrets to run the system.
"""

from __future__ import annotations

import json
import os
from typing import Any, Optional

MODEL = os.environ.get("CLAIMS_LLM_MODEL", "claude-sonnet-4-6")

_EXTRACTION_TOOL = {
    "name": "emit_document_fields",
    "description": "Return the structured fields extracted from a medical document.",
    "input_schema": {
        "type": "object",
        "properties": {
            "patient_name": {"type": ["string", "null"]},
            "doctor_name": {"type": ["string", "null"]},
            "doctor_registration": {"type": ["string", "null"]},
            "diagnosis": {"type": ["string", "null"]},
            "treatment": {"type": ["string", "null"]},
            "hospital_name": {"type": ["string", "null"]},
            "total": {"type": ["number", "null"]},
            "date": {"type": ["string", "null"]},
            "line_items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "description": {"type": "string"},
                        "amount": {"type": "number"},
                    },
                    "required": ["description", "amount"],
                },
            },
            "tests_ordered": {"type": "array", "items": {"type": "string"}},
            "medicines": {"type": "array", "items": {"type": "string"}},
            "unreadable_fields": {"type": "array", "items": {"type": "string"}},
        },
        "required": [],
    },
}


class ExtractionError(RuntimeError):
    """Raised when the LLM is unavailable or returns invalid/unparseable output."""


def llm_available() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


async def extract_fields(doc_type: str, raw_text: str) -> dict[str, Any]:
    """Extract structured fields from raw document text. Raises ExtractionError."""
    if not llm_available():
        raise ExtractionError("ANTHROPIC_API_KEY not set")

    try:
        import anthropic  # imported lazily so the dep is optional at runtime
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise ExtractionError("anthropic package not installed") from exc

    client = anthropic.AsyncAnthropic()
    prompt = (
        f"Extract the fields from this Indian medical document (type: {doc_type}). "
        "Use OCR-style careful reading. Indian doctor registration numbers look "
        "like KA/45678/2015. Expand shorthand diagnoses (HTN=Hypertension, "
        "T2DM=Type 2 Diabetes). List any field you cannot read in `unreadable_fields`. "
        "Call emit_document_fields with what you find.\n\n"
        f"DOCUMENT:\n{raw_text}"
    )
    try:
        resp = await client.messages.create(
            model=MODEL,
            max_tokens=1024,
            tools=[_EXTRACTION_TOOL],
            tool_choice={"type": "tool", "name": "emit_document_fields"},
            messages=[{"role": "user", "content": prompt}],
        )
    except Exception as exc:  # network / API failure
        raise ExtractionError(f"LLM call failed: {exc}") from exc

    for block in resp.content:
        if getattr(block, "type", None) == "tool_use":
            return dict(block.input)
    raise ExtractionError("LLM returned no structured tool output")


def parse_json_fields(raw_text: str) -> Optional[dict[str, Any]]:
    """Best-effort: some 'raw' docs are actually JSON blobs. Returns None if not."""
    try:
        value = json.loads(raw_text)
        return value if isinstance(value, dict) else None
    except (json.JSONDecodeError, TypeError):
        return None
