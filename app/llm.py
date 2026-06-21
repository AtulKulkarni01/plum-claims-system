"""Document extraction adapter with multi-provider failover.

The LLM is used in exactly ONE place in this system: turning messy, unstructured
medical documents (handwriting, stamps, phone photos) into structured fields.
Adjudication never touches an LLM — money decisions stay deterministic.

Extraction runs a resilience chain:

    Gemini 2.0 Flash (primary)
        ├─ retry with exponential backoff on transient failure
        └─ on exhaustion, FAIL OVER to →
    OpenAI (fallback)
        ├─ retry with exponential backoff
        └─ on exhaustion → ExtractionError → caller degrades the document

This mirrors the production pattern of sequential model switching + backoff: a
single provider's rate-limit or outage never takes the pipeline down. Output is
schema-constrained per provider and re-validated with Pydantic; the provider used
and every failover attempt are returned so the caller can record them in the trace.

The eval harness supplies structured `content`, so the system is fully functional
and deterministic with NO API key. Set GEMINI_API_KEY and/or OPENAI_API_KEY to
enable extraction of real raw text / images.
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Optional

from pydantic import BaseModel

GEMINI_MODEL = os.environ.get("CLAIMS_LLM_MODEL", "gemini-2.0-flash")
OPENAI_MODEL = os.environ.get("CLAIMS_OPENAI_MODEL", "gpt-4o-mini")

# Failover tuning (overridable via env; tests set backoff to 0).
_MAX_RETRIES = int(os.environ.get("CLAIMS_LLM_RETRIES", "2"))
_BACKOFF_BASE = float(os.environ.get("CLAIMS_LLM_BACKOFF", "0.5"))


class _Fields(BaseModel):
    """The structured fields we ask each provider to return."""

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
    legible: bool = True


_PROMPT = (
    "Extract the fields from this Indian medical document (type: {doc_type}). "
    "Read carefully like OCR. Indian doctor registration numbers look like "
    "KA/45678/2015. Expand shorthand diagnoses (HTN=Hypertension, T2DM=Type 2 "
    "Diabetes). For a bill, capture every line item as {{description, amount}} and "
    "the total. List any field you genuinely cannot read in `unreadable_fields` "
    "rather than guessing. Set legible=false if the document is too blurry or "
    "low-quality to read reliably."
)

_JSON_HINT = (
    " Respond ONLY with a JSON object with keys: patient_name, doctor_name, "
    "doctor_registration, diagnosis, treatment, hospital_name, total, date, "
    "line_items (array of {description, amount}), tests_ordered (array), "
    "medicines (array), unreadable_fields (array), legible (boolean)."
)


class ExtractionError(RuntimeError):
    """Raised when no provider could return valid output."""


@dataclass
class ExtractionResult:
    fields: dict[str, Any]
    provider: str                       # which provider succeeded
    attempts: list[str] = field(default_factory=list)  # failover/retry log


def _gemini_key() -> Optional[str]:
    return os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")


def _openai_key() -> Optional[str]:
    return os.environ.get("OPENAI_API_KEY")


def llm_available() -> bool:
    """True if at least one extraction provider is configured."""
    return bool(_gemini_key() or _openai_key())


def parse_json_fields(raw_text: str) -> Optional[dict[str, Any]]:
    """Some 'raw' docs are actually JSON blobs — use them directly, no LLM."""
    try:
        value = json.loads(raw_text)
        return value if isinstance(value, dict) else None
    except (json.JSONDecodeError, TypeError):
        return None


# --------------------------------------------------------------------------- #
# Providers — each takes (doc_type, raw_text, image_base64) and returns a dict
# of fields, or raises ExtractionError. Imports are lazy so the SDKs are optional.
# --------------------------------------------------------------------------- #
async def _gemini_extract(
    doc_type: str, raw_text: Optional[str], image_base64: Optional[str]
) -> dict[str, Any]:
    if not _gemini_key():
        raise ExtractionError("GEMINI_API_KEY not set")
    try:
        from google import genai
        from google.genai import types
    except ImportError as exc:  # pragma: no cover - env dependent
        raise ExtractionError("google-genai not installed") from exc

    client = genai.Client(api_key=_gemini_key())
    parts: list[Any] = [_PROMPT.format(doc_type=doc_type)]
    if raw_text:
        parts.append(f"\n\nDOCUMENT TEXT:\n{raw_text}")
    if image_base64:
        parts.append(types.Part.from_bytes(
            data=_decode_image(image_base64), mime_type="image/jpeg"))
    try:
        resp = await client.aio.models.generate_content(
            model=GEMINI_MODEL,
            contents=parts,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=_Fields,
                temperature=0,
            ),
        )
    except Exception as exc:
        raise ExtractionError(f"Gemini call failed: {exc}") from exc
    if not resp.text:
        raise ExtractionError("Gemini returned no content")
    return _validate(resp.text)


async def _openai_extract(
    doc_type: str, raw_text: Optional[str], image_base64: Optional[str]
) -> dict[str, Any]:
    if not _openai_key():
        raise ExtractionError("OPENAI_API_KEY not set")
    try:
        from openai import AsyncOpenAI
    except ImportError as exc:  # pragma: no cover - env dependent
        raise ExtractionError("openai not installed") from exc

    client = AsyncOpenAI(api_key=_openai_key())
    content: list[dict[str, Any]] = [
        {"type": "text", "text": _PROMPT.format(doc_type=doc_type) + _JSON_HINT}
    ]
    if raw_text:
        content.append({"type": "text", "text": f"DOCUMENT TEXT:\n{raw_text}"})
    if image_base64:
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"},
        })
    try:
        resp = await client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[{"role": "user", "content": content}],
            response_format={"type": "json_object"},
            temperature=0,
        )
    except Exception as exc:
        raise ExtractionError(f"OpenAI call failed: {exc}") from exc
    text = resp.choices[0].message.content
    if not text:
        raise ExtractionError("OpenAI returned no content")
    return _validate(text)


def _decode_image(image_base64: str) -> bytes:
    try:
        return base64.b64decode(image_base64)
    except Exception as exc:
        raise ExtractionError(f"bad image payload: {exc}") from exc


def _validate(text: str) -> dict[str, Any]:
    try:
        return _Fields.model_validate_json(text).model_dump()
    except Exception as exc:
        raise ExtractionError(f"LLM output failed validation: {exc}") from exc


ProviderFn = Callable[[str, Optional[str], Optional[str]], Awaitable[dict[str, Any]]]


def _provider_chain() -> list[tuple[str, ProviderFn]]:
    """Ordered list of configured providers: Gemini first, OpenAI as fallback."""
    chain: list[tuple[str, ProviderFn]] = []
    if _gemini_key():
        chain.append(("gemini", _gemini_extract))
    if _openai_key():
        chain.append(("openai", _openai_extract))
    return chain


async def extract_fields(
    doc_type: str,
    raw_text: Optional[str] = None,
    image_base64: Optional[str] = None,
) -> ExtractionResult:
    """Extract fields, failing over across providers with backoff.

    Raises ExtractionError only when every configured provider is exhausted (or
    none is configured), so the caller can degrade the document gracefully.
    """
    if not raw_text and not image_base64:
        raise ExtractionError("no document payload to extract from")
    chain = _provider_chain()
    if not chain:
        raise ExtractionError("no LLM provider configured")

    attempts: list[str] = []
    for name, fn in chain:
        for attempt in range(_MAX_RETRIES):
            try:
                fields = await fn(doc_type, raw_text, image_base64)
                return ExtractionResult(fields=fields, provider=name, attempts=attempts)
            except ExtractionError as exc:
                attempts.append(f"{name} attempt {attempt + 1}/{_MAX_RETRIES} failed: {exc}")
                if attempt + 1 < _MAX_RETRIES:
                    await asyncio.sleep(_BACKOFF_BASE * (2 ** attempt))
        # provider exhausted -> fall over to the next one in the chain
    raise ExtractionError("all providers failed: " + "; ".join(attempts))
