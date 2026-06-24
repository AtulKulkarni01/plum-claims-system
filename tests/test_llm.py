"""Unit tests for the LLM extraction adapter: validation, decoding, JSON
fast-path, per-attempt timeout, and provider failover."""

from __future__ import annotations

import asyncio
import sys
import types

import pytest

import app.llm as llm
from app.llm import (
    ExtractionError,
    _decode_image,
    _validate,
    extract_fields,
    parse_json_fields,
)


def _run(coro):
    return asyncio.run(coro)


def _install_fake_gemini(monkeypatch, resp_text):
    """Inject a minimal fake `google.genai` so _gemini_extract runs offline."""
    class FakeResp:
        text = resp_text

    class FakeModels:
        async def generate_content(self, **kw):
            return FakeResp()

    class FakeClient:
        def __init__(self, api_key=None):
            self.aio = types.SimpleNamespace(models=FakeModels())

    gtypes = types.ModuleType("google.genai.types")
    gtypes.Part = types.SimpleNamespace(from_bytes=lambda data=None, mime_type=None: ("part", mime_type))
    gtypes.GenerateContentConfig = lambda **kw: kw
    genai = types.ModuleType("google.genai")
    genai.Client = FakeClient
    genai.types = gtypes
    google = types.ModuleType("google")
    google.genai = genai
    monkeypatch.setitem(sys.modules, "google", google)
    monkeypatch.setitem(sys.modules, "google.genai", genai)
    monkeypatch.setitem(sys.modules, "google.genai.types", gtypes)
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")


def _install_fake_openai(monkeypatch, resp_text):
    """Inject a minimal fake `openai` so _openai_extract runs offline."""
    class FakeCompletions:
        async def create(self, **kw):
            msg = types.SimpleNamespace(content=resp_text)
            return types.SimpleNamespace(choices=[types.SimpleNamespace(message=msg)])

    class FakeAsyncOpenAI:
        def __init__(self, api_key=None):
            self.chat = types.SimpleNamespace(completions=FakeCompletions())

    openai_mod = types.ModuleType("openai")
    openai_mod.AsyncOpenAI = FakeAsyncOpenAI
    monkeypatch.setitem(sys.modules, "openai", openai_mod)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")


# --- _validate ------------------------------------------------------------- #
def test_validate_accepts_valid_json():
    fields = _validate('{"diagnosis": "Dengue", "total": 700}')
    assert fields["diagnosis"] == "Dengue"
    assert fields["total"] == 700


def test_validate_rejects_malformed_json():
    with pytest.raises(ExtractionError):
        _validate("not json at all")


def test_validate_rejects_wrong_types():
    # total must be a number; a non-numeric string fails schema validation
    with pytest.raises(ExtractionError):
        _validate('{"total": "not-a-number"}')


# --- _decode_image --------------------------------------------------------- #
def test_decode_image_roundtrip():
    import base64
    assert _decode_image(base64.b64encode(b"hello").decode()) == b"hello"


def test_decode_image_rejects_bad_payload():
    with pytest.raises(ExtractionError):
        _decode_image("a")  # invalid base64 padding


# --- parse_json_fields ----------------------------------------------------- #
def test_parse_json_fields_dict():
    assert parse_json_fields('{"a": 1}') == {"a": 1}


def test_parse_json_fields_non_dict_returns_none():
    assert parse_json_fields("[1, 2, 3]") is None


def test_parse_json_fields_invalid_returns_none():
    assert parse_json_fields("definitely not json") is None


# --- extract_fields: timeout ----------------------------------------------- #
def test_extract_fields_times_out_a_hung_provider(monkeypatch):
    async def hung(doc_type, raw_text, image_base64, mime_type):
        await asyncio.sleep(5)  # never returns within the timeout

    monkeypatch.setattr(llm, "_TIMEOUT", 0.01)
    monkeypatch.setattr(llm, "_MAX_RETRIES", 1)
    monkeypatch.setattr(llm, "_BACKOFF_BASE", 0.0)
    monkeypatch.setattr(llm, "_provider_chain", lambda: [("gemini", hung)])

    with pytest.raises(ExtractionError) as exc:
        _run(extract_fields("PRESCRIPTION", raw_text="x"))
    assert "timed out" in str(exc.value)


# --- extract_fields: failover ---------------------------------------------- #
def test_extract_fields_fails_over_to_next_provider(monkeypatch):
    async def broken(doc_type, raw_text, image_base64, mime_type):
        raise ExtractionError("gemini down")

    async def ok(doc_type, raw_text, image_base64, mime_type):
        return {"diagnosis": "Dengue"}

    monkeypatch.setattr(llm, "_MAX_RETRIES", 1)
    monkeypatch.setattr(llm, "_BACKOFF_BASE", 0.0)
    monkeypatch.setattr(llm, "_provider_chain",
                        lambda: [("gemini", broken), ("openai", ok)])

    res = _run(extract_fields("PRESCRIPTION", raw_text="x"))
    assert res.provider == "openai"
    assert res.fields["diagnosis"] == "Dengue"
    assert any("gemini" in a for a in res.attempts)


# --- provider bodies (fake SDKs) ------------------------------------------- #
def test_gemini_extract_parses_response(monkeypatch):
    _install_fake_gemini(monkeypatch, '{"diagnosis": "Dengue", "total": 700}')
    import base64
    fields = _run(llm._gemini_extract(
        "HOSPITAL_BILL", "bill text", base64.b64encode(b"img").decode(), "image/png"))
    assert fields["diagnosis"] == "Dengue"
    assert fields["total"] == 700


def test_gemini_extract_raises_on_empty_response(monkeypatch):
    _install_fake_gemini(monkeypatch, "")
    with pytest.raises(ExtractionError):
        _run(llm._gemini_extract("PRESCRIPTION", "text", None, None))


def test_openai_extract_parses_response(monkeypatch):
    _install_fake_openai(monkeypatch, '{"diagnosis": "Migraine"}')
    fields = _run(llm._openai_extract("PRESCRIPTION", "rx text", None, None))
    assert fields["diagnosis"] == "Migraine"


def test_openai_extract_raises_on_empty_response(monkeypatch):
    _install_fake_openai(monkeypatch, None)
    with pytest.raises(ExtractionError):
        _run(llm._openai_extract("PRESCRIPTION", "text", None, None))
