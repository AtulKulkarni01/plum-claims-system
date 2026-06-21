"""Extraction agent: provided content, JSON text, and graceful LLM fallback."""

from __future__ import annotations

import asyncio

import pytest

from app.agents.extraction import extract_claim
from app.llm import ExtractionError, extract_fields, parse_json_fields
from app.models import ClaimSubmission
from app.trace import Trace


def _run(coro):
    return asyncio.run(coro)


def test_uses_provided_content_without_llm():
    sub = ClaimSubmission.model_validate({
        "member_id": "EMP001", "policy_id": "PLUM_GHI_2024",
        "claim_category": "CONSULTATION", "treatment_date": "2024-11-01",
        "claimed_amount": 1500,
        "documents": [
            {"file_id": "A", "actual_type": "PRESCRIPTION",
             "content": {"diagnosis": "Viral Fever", "patient_name": "Rajesh Kumar"}},
            {"file_id": "B", "actual_type": "HOSPITAL_BILL",
             "content": {"line_items": [{"description": "Consultation", "amount": 1500}],
                         "total": 1500}},
        ],
    })
    extracted = _run(extract_claim(sub, Trace()))
    assert extracted.diagnosis == "Viral Fever"
    assert extracted.total == 1500
    assert {d.source for d in extracted.documents} == {"PROVIDED"}


def test_json_text_is_parsed_without_llm():
    assert parse_json_fields('{"total": 200}') == {"total": 200}
    assert parse_json_fields("not json") is None


def test_missing_payload_degrades_not_crashes():
    sub = ClaimSubmission.model_validate({
        "member_id": "EMP001", "policy_id": "PLUM_GHI_2024",
        "claim_category": "CONSULTATION", "treatment_date": "2024-11-01",
        "claimed_amount": 100,
        # no content, no text, no image, and no API key -> degraded record
        "documents": [{"file_id": "A", "actual_type": "HOSPITAL_BILL"}],
    })
    extracted = _run(extract_claim(sub, Trace()))
    assert extracted.documents[0].source == "DEGRADED"


def test_extract_fields_raises_without_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    with pytest.raises(ExtractionError):
        _run(extract_fields("PRESCRIPTION", raw_text="some text"))
