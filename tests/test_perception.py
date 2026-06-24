"""Perception stage: real uploaded images are read into structured content."""

from __future__ import annotations

import asyncio

import app.agents.perception as perception_mod
from app.agents.perception import perceive
from app.llm import ExtractionResult
from app.models import ClaimSubmission, Decision, Quality, ResultStatus
from app.trace import Trace
from tests.conftest import run


def _run(coro):
    return asyncio.run(coro)


def _image_claim():
    return ClaimSubmission.model_validate({
        "member_id": "EMP001", "policy_id": "PLUM_GHI_2024",
        "claim_category": "CONSULTATION", "treatment_date": "2024-11-01",
        "claimed_amount": 1500,
        "documents": [
            {"file_id": "IMG1", "actual_type": "PRESCRIPTION", "image_base64": "ZmFrZQ=="},
            {"file_id": "IMG2", "actual_type": "HOSPITAL_BILL", "image_base64": "ZmFrZQ=="},
        ],
    })


def _fake_reader(prescription_fields, bill_fields):
    async def fake(doc_type, raw_text=None, image_base64=None, mime_type=None):
        fields = prescription_fields if doc_type == "PRESCRIPTION" else bill_fields
        return ExtractionResult(fields=fields, provider="gemini")
    return fake


def test_perceive_reads_images_into_content(monkeypatch):
    monkeypatch.setattr(perception_mod, "llm_available", lambda: True)
    monkeypatch.setattr(perception_mod, "extract_fields", _fake_reader(
        {"patient_name": "Rajesh Kumar", "diagnosis": "Viral Fever", "legible": True},
        {"patient_name": "Rajesh Kumar",
         "line_items": [{"description": "Consultation", "amount": 1500}],
         "total": 1500, "legible": True}))
    sub, trace = _image_claim(), Trace()
    enriched = _run(perceive(sub, trace))
    docs = {d.file_id: d for d in enriched.documents}
    assert docs["IMG1"].content["diagnosis"] == "Viral Fever"
    assert docs["IMG1"].patient_name_on_doc == "Rajesh Kumar"
    assert any(s.step == "perception.read" for s in trace.steps)
    # input submission is not mutated in place
    assert all(d.content is None for d in sub.documents)


def test_unreadable_image_is_flagged(monkeypatch):
    monkeypatch.setattr(perception_mod, "llm_available", lambda: True)
    monkeypatch.setattr(perception_mod, "extract_fields",
                        _fake_reader({"legible": False}, {"legible": False}))
    sub, trace = _image_claim(), Trace()
    enriched = _run(perceive(sub, trace))
    assert all(d.quality == Quality.UNREADABLE for d in enriched.documents)


def test_perceive_skips_when_no_provider(monkeypatch):
    monkeypatch.setattr(perception_mod, "llm_available", lambda: False)
    sub, trace = _image_claim(), Trace()
    _run(perceive(sub, trace))
    assert all(d.content is None for d in sub.documents)  # untouched
    assert trace.steps == []


def test_end_to_end_uploaded_images_reach_a_decision(monkeypatch):
    monkeypatch.setattr(perception_mod, "llm_available", lambda: True)
    monkeypatch.setattr(perception_mod, "extract_fields", _fake_reader(
        {"patient_name": "Rajesh Kumar", "diagnosis": "Viral Fever", "legible": True},
        {"patient_name": "Rajesh Kumar",
         "line_items": [{"description": "Consultation Fee", "amount": 1500}],
         "total": 1500, "legible": True}))
    result = run(_image_claim())
    assert result.status == ResultStatus.COMPLETED
    assert result.decision == Decision.APPROVED
    assert result.approved_amount == 1350  # 1500 - 10% consultation co-pay
