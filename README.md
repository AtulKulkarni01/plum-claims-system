# Plum — Health Insurance Claims Processing System

A multi-agent pipeline that adjudicates health-insurance claims: it verifies
documents, extracts structured data, applies policy rules, scores fraud signals,
and returns an **explainable** decision (`APPROVED` / `PARTIAL` / `REJECTED` /
`MANUAL_REVIEW`) with a full step-by-step trace — or stops early and tells the
member exactly which document to fix.

> Built for the Plum AI Engineer assignment. The original brief is in
> [`assignment.md`](assignment.md).

**Result: 12 / 12 eval cases match expected outcomes** (see [`docs/EVAL_REPORT.md`](docs/EVAL_REPORT.md)).

---

## Quick start

```bash
# 1. install
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 2. run the app  (UI + API on http://localhost:8000)
uvicorn app.main:app --reload

# 3. open the console
open http://localhost:8000
```

In the UI: pick a test case (TC001–TC012) from the dropdown, optionally edit the
JSON, and click **Adjudicate claim** to see the decision, the payout
calculation, fraud signals, and the full decision trace.

No API key is required — the system is fully functional and deterministic out of
the box. (Setting `GEMINI_API_KEY` (or `OPENAI_API_KEY`) enables LLM extraction
for *raw, unstructured* documents; see below.)

---

## Run the evals and tests

```bash
python -m scripts.run_evals            # prints PASS/FAIL for all 12 cases
python -m scripts.run_evals --report   # regenerates docs/EVAL_REPORT.md

pytest -q                              # 54 tests
pytest --cov=app -q                    # ~90% coverage
```

---

## How it works (one screen)

```
ClaimSubmission
   │
   ▼  Orchestrator (owns trace + result + failure boundary)
   ├─ Intake .................. resolve member
   ├─ Document Verification ... GATE: wrong/missing/unreadable/mismatched docs → STOP (decision=null)
   ├─ Extraction (async) ...... documents → structured typed fields
   ├─ Adjudication ............ coverage → exclusion → waiting → pre-auth → limits → payout
   ├─ Fraud / Anomaly ......... same-day volume, high value → MANUAL_REVIEW
   └─ Decision assembly ....... decision + confidence + member message
   ▼
ClaimResult (+ full trace)
```

- **Documentation:** [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) ·
  [`docs/COMPONENT_CONTRACTS.md`](docs/COMPONENT_CONTRACTS.md) ·
  [`docs/EVAL_REPORT.md`](docs/EVAL_REPORT.md) ·
  [`docs/DEPLOY.md`](docs/DEPLOY.md) · [`docs/DEMO_SCRIPT.md`](docs/DEMO_SCRIPT.md)
- **Policy rules** are read from [`policy_terms.json`](policy_terms.json) — nothing is hardcoded.
- **Observability:** every decision carries an ordered `trace`; confidence is
  literally `0.95 + Σ(confidence deltas)` from those same trace steps.
- **Resilience:** every non-gate stage runs in a try/except boundary — a failing
  component is recorded, drops confidence, flags manual review, and the pipeline
  continues (TC011).

---

## Project layout

```
app/
  main.py              FastAPI app + UI endpoints
  orchestrator.py      pipeline + failure boundary + confidence
  models.py            Pydantic contracts (validated I/O)
  policy.py            typed read-only accessors over policy_terms.json
  trace.py             observability accumulator
  llm.py               optional Gemini→OpenAI extraction adapter (schema-validated)
  agents/perception.py reads uploaded document images into structured fields
  agents/
    document_verification.py   the early-stop gate
    extraction.py              async document → fields
    adjudication.py            policy rule engine + financials
    fraud.py                   anomaly signals
  static/index.html    decision-review console (zero external deps)
docs/                  architecture, contracts, eval report
scripts/run_evals.py   runs all 12 cases, writes the eval report
tests/                 54 tests (unit + integration + full eval)
```

---

## Optional: LLM extraction for raw documents (Google Gemini 2.0 Flash)

The eval harness supplies structured `content` for each document, so the LLM is
not exercised by the test cases. For a *real* unstructured document (raw text or
an image), set `GEMINI_API_KEY` (or `GOOGLE_API_KEY`) and the extraction agent
calls **Gemini 2.0 Flash** with a constrained JSON `response_schema`, re-validates
the result with Pydantic, and falls back to a degraded-but-non-crashing path on
any failure. Gemini 2.0 Flash is chosen for lowest latency/cost at claim volume
with strong vision + native structured output. The adapter is provider-agnostic
(`extract_fields`), so swapping models is a one-file change. See
[`app/llm.py`](app/llm.py) and `docs/ARCHITECTURE.md` §6.

```bash
export GEMINI_API_KEY=...   # then raw text/image documents get LLM extraction
```
