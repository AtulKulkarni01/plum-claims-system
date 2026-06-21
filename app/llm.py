"""Document extraction adapter — Google Gemini 2.0 Flash.

The LLM is used in exactly ONE place in this system: turning messy, unstructured
medical documents (handwriting, stamps, phone photos) into structured fields.
Adjudication never touches an LLM — money decisions stay deterministic and
auditable.

Why Gemini 2.0 Flash: lowest latency and cost per call with strong vision and
native *structured output* (a response JSON schema), which is what matters for
claim volume. Output is schema-constrained by the API and then re-validated with
Pydantic; any failure raises ExtractionError so the caller degrades instead of
trusting bad data.

The eval harness supplies structured `content`, so the system is fully functional
and deterministic with NO API key. Set GEMINI_API_KEY (or GOOGLE_API_KEY) to
enable extraction of real raw text / images.
"""

from __future__ import annotations

import base64
import json
import os
from typing import Any, Optional

from pydantic import BaseModel

MODEL = os.environ.get("CLAIMS_LLM_MODEL", "gemini-2.0-flash")


class _Fields(BaseModel):
    """Response schema handed to Gemini (drives its structured output)."""

    patient_name: Optional[str] = None
    doctor_name: Optional[str] = None
    doctor_registration: Optional[str] = None
    diagnosis: Optional[str] = None
    treatment: Optional[str] = None
    hospital_name: Optional[str] = None
    total: Optional[float] = None
    date: Optional[str] = None
    line_items: list[dict[str, Any]] = []
    tests_ordered: list[str] = []
    medicines: list[str] = []
    unreadable_fields: list[str] = []


_PROMPT = (
    "You are extracting fields from an Indian medical document (type: {doc_type}). "
    "Read carefully like OCR. Indian doctor registration numbers look like "
    "KA/45678/2015. Expand shorthand diagnoses (HTN=Hypertension, T2DM=Type 2 "
    "Diabetes). For a bill, capture every line item as {{description, amount}} and "
    "the total. List any field you genuinely cannot read in `unreadable_fields` "
    "rather than guessing."
)


class ExtractionError(RuntimeError):
    """Raised when the LLM is unavailable or returns invalid/unparseable output."""


def _api_key() -> Optional[str]:
    return os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")


def llm_available() -> bool:
    return bool(_api_key())


def parse_json_fields(raw_text: str) -> Optional[dict[str, Any]]:
    """Some 'raw' docs are actually JSON blobs — use them directly, no LLM."""
    try:
        value = json.loads(raw_text)
        return value if isinstance(value, dict) else None
    except (json.JSONDecodeError, TypeError):
        return None


async def extract_fields(
    doc_type: str,
    raw_text: Optional[str] = None,
    image_base64: Optional[str] = None,
) -> dict[str, Any]:
    """Extract structured fields from raw text and/or an image. Raises ExtractionError."""
    if not llm_available():
        raise ExtractionError("GEMINI_API_KEY/GOOGLE_API_KEY not set")
    if not raw_text and not image_base64:
        raise ExtractionError("no document payload to extract from")

    try:
        from google import genai  # lazy import: dependency is optional at runtime
        from google.genai import types
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise ExtractionError("google-genai package not installed") from exc

    client = genai.Client(api_key=_api_key())
    parts: list[Any] = [_PROMPT.format(doc_type=doc_type)]
    if raw_text:
        parts.append(f"\n\nDOCUMENT TEXT:\n{raw_text}")
    if image_base64:
        try:
            image_bytes = base64.b64decode(image_base64)
        except Exception as exc:  # malformed base64
            raise ExtractionError(f"bad image payload: {exc}") from exc
        parts.append(types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"))

    try:
        resp = await client.aio.models.generate_content(
            model=MODEL,
            contents=parts,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=_Fields,
                temperature=0,
            ),
        )
    except Exception as exc:  # network / API / quota failure
        raise ExtractionError(f"Gemini call failed: {exc}") from exc

    if not resp.text:
        raise ExtractionError("Gemini returned no content")
    try:
        return _Fields.model_validate_json(resp.text).model_dump()
    except Exception as exc:
        raise ExtractionError(f"Gemini output failed validation: {exc}") from exc
