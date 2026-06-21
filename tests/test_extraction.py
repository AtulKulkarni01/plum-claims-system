"""Extraction agent: provided content, JSON text, and graceful LLM fallback."""

from __future__ import annotations

import asyncio

import pytest

import app.agents.extraction as extraction_mod
import app.llm as llm
from app.agents.extraction import extract_claim
from app.llm import ExtractionError, ExtractionResult, extract_fields, parse_json_fields
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


def test_extract_fields_raises_without_any_provider(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(ExtractionError):
        _run(extract_fields("PRESCRIPTION", raw_text="some text"))


def test_failover_gemini_to_openai(monkeypatch):
    """Primary (Gemini) exhausts its retries, then OpenAI fallback succeeds."""
    monkeypatch.setattr(llm, "_BACKOFF_BASE", 0.0)  # no real sleeps in tests
    monkeypatch.setattr(llm, "_MAX_RETRIES", 2)

    async def gemini_down(doc_type, raw, img):
        raise ExtractionError("rate limited")

    async def openai_ok(doc_type, raw, img):
        return {"diagnosis": "Viral Fever", "total": 500}

    monkeypatch.setattr(llm, "_provider_chain",
                        lambda: [("gemini", gemini_down), ("openai", openai_ok)])

    res = _run(extract_fields("PRESCRIPTION", raw_text="handwritten note"))
    assert res.provider == "openai"
    assert res.fields["diagnosis"] == "Viral Fever"
    # both gemini retries are logged before the failover
    assert sum("gemini attempt" in a for a in res.attempts) == 2


def test_all_providers_failing_raises(monkeypatch):
    monkeypatch.setattr(llm, "_BACKOFF_BASE", 0.0)
    monkeypatch.setattr(llm, "_MAX_RETRIES", 1)

    async def down(doc_type, raw, img):
        raise ExtractionError("provider down")

    monkeypatch.setattr(llm, "_provider_chain",
                        lambda: [("gemini", down), ("openai", down)])
    with pytest.raises(ExtractionError):
        _run(extract_fields("PRESCRIPTION", raw_text="x"))


def test_extraction_records_provider_and_failover_in_trace(monkeypatch):
    """The agent surfaces which provider was used (and any failover) in the trace."""
    async def fake_extract(doc_type, raw_text=None, image_base64=None):
        return ExtractionResult(
            fields={"diagnosis": "Dengue", "total": 700},
            provider="openai",
            attempts=["gemini attempt 1/2 failed: rate limited"])

    monkeypatch.setattr(extraction_mod, "llm_available", lambda: True)
    monkeypatch.setattr(extraction_mod, "extract_fields", fake_extract)

    sub = ClaimSubmission.model_validate({
        "member_id": "EMP001", "policy_id": "PLUM_GHI_2024",
        "claim_category": "CONSULTATION", "treatment_date": "2024-11-01",
        "claimed_amount": 700,
        "documents": [{"file_id": "S", "actual_type": "HOSPITAL_BILL",
                       "text": "handwritten scanned bill, not json"}],
    })
    trace = Trace()
    extracted = _run(extract_claim(sub, trace))
    assert extracted.documents[0].source == "LLM:openai"
    llm_steps = [s for s in trace.steps if s.step == "extraction.llm"]
    assert llm_steps and llm_steps[0].data["failover_log"]
