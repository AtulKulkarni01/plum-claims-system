# Component Contracts

Every significant component's interface — input, output, errors. Precise enough
to reimplement any one component without reading its code. Types refer to the
Pydantic models in `app/models.py`.

---

## Orchestrator — `run_claim`

```python
async def run_claim(submission: ClaimSubmission, policy: Policy | None = None) -> ClaimResult
```

- **Input:** a validated `ClaimSubmission`; optional `Policy` (defaults to the singleton).
- **Output:** a `ClaimResult` that is ALWAYS returned (never raises for claim-logic reasons).
  - `status = DOCUMENT_ISSUE` and `decision = None` when the verification gate stops the pipeline.
  - `status = COMPLETED` with a `decision` otherwise.
- **Guarantees:**
  - Populates `trace` with every step taken.
  - `confidence_score = clamp(0.95 + Σ trace.confidence_delta, 0, 1)`.
  - Any non-gate stage that raises is caught: trace gets an `ERROR` step, `degraded=True`, `requires_manual_review=True`, pipeline continues.
- **Raises:** nothing for claim logic. Programmer errors (e.g. a bug) would propagate; the API layer turns input problems into 422 before this is called.

---

## Intake (inline in orchestrator)

- **Input:** `ClaimSubmission`, `Policy`.
- **Output:** trace step `intake.member` (PASS / WARN). Sets `requires_manual_review` if the member is not in the roster.
- **Errors:** none (a missing member degrades, never crashes).

---

## Document Verification — `verify_documents`

```python
def verify_documents(submission: ClaimSubmission, policy: Policy, trace: Trace) -> list[DocumentIssue]
```

- **Input:** the submission, policy (for `document_requirements`), the trace.
- **Output:** a list of `DocumentIssue`. Empty list ⇒ gate passed.
- **Issue codes & meaning:**
  - `MISSING_REQUIRED_DOCUMENT` — a required type for the category is absent; message names what was uploaded and what is missing.
  - `UNREADABLE_DOCUMENT` — a document has `quality == UNREADABLE`; `file_id` set; asks to re-upload that file; does **not** reject the claim.
  - `PATIENT_MISMATCH` — documents reference >1 distinct patient name; message lists each file's name.
- **Side effects:** appends PASS/FAIL trace steps for each of the three checks.
- **Raises:** none.

---

## Extraction — `extract_claim`

```python
async def extract_claim(submission: ClaimSubmission, trace: Trace) -> ExtractedClaim
```

- **Input:** the submission, the trace.
- **Output:** an `ExtractedClaim` merging every document's `ExtractedDocument`.
  - Per-document `source ∈ {PROVIDED, LLM, DEGRADED}`.
  - Merges clinical fields (diagnosis/treatment/registration) and financial fields (line_items/total).
- **Behavior:** documents extracted concurrently (`asyncio.gather`). Priority: structured `content` → JSON `text` → LLM (if `ANTHROPIC_API_KEY`) → degraded empty record.
- **Errors:** an `ExtractionError` from the LLM adapter is caught per-document → that document becomes `DEGRADED` with a `-0.15` confidence trace step. `extract_claim` itself does not raise.

---

## LLM adapter — `extract_fields` (Google Gemini 2.0 Flash)

```python
async def extract_fields(doc_type: str, raw_text: str | None = None,
                         image_base64: str | None = None) -> dict
```

- **Input:** document type, and raw text and/or a base64 image.
- **Output:** a dict matching the `_Fields` response schema (constrained by the Gemini API and re-validated with Pydantic).
- **Model:** `gemini-2.0-flash` (override via `CLAIMS_LLM_MODEL`); key from `GEMINI_API_KEY` / `GOOGLE_API_KEY`.
- **Raises:** `ExtractionError` if the key is missing, the SDK is absent, there is no payload, the network call fails, or the output fails validation. Callers must handle this and degrade.

---

## Adjudication — `adjudicate`

```python
def adjudicate(submission: ClaimSubmission, extracted: ExtractedClaim, policy: Policy, trace: Trace) -> AdjudicationOutcome
```

- **Input:** submission, extracted data, policy, trace.
- **Output:** `AdjudicationOutcome { decision, approved_amount, reasons[], messages[], line_item_results[], calculation[] }` where `decision ∈ {APPROVED, PARTIAL, REJECTED}` (manual review is decided later, by the orchestrator).
- **Rule order (first hard reject wins):** coverage → blanket exclusion → waiting period → pre-auth → per-claim limit → line-item partial → financials.
- **Reason codes:** `CATEGORY_NOT_COVERED`, `EXCLUDED_CONDITION`, `WAITING_PERIOD`, `PRE_AUTH_MISSING`, `PER_CLAIM_EXCEEDED`, `PARTIAL_EXCLUSION`.
- **Financials:** covered base → network discount (if network hospital) → co-pay → annual-limit cap. Each step emitted as a `CalculationStep`.
- **Raises:** may raise on malformed data; the orchestrator wraps it in `_safe` and degrades to `MANUAL_REVIEW`.

---

## Fraud / Anomaly — `detect_fraud`

```python
def detect_fraud(submission: ClaimSubmission, policy: Policy, trace: Trace) -> list[FraudSignal]
```

- **Input:** submission (incl. `claims_history`), policy thresholds, trace.
- **Output:** list of `FraudSignal { code, detail, severity }`. Codes: `SAME_DAY_CLAIM_VOLUME` (HIGH), `MONTHLY_CLAIM_VOLUME` (MEDIUM), `HIGH_VALUE_CLAIM` (HIGH).
- **Routing:** the orchestrator turns any HIGH signal on an otherwise-payable claim into `MANUAL_REVIEW` (never an auto-reject).
- **Raises:** `ComponentFailure` when `simulate_component_failure` is set (and would raise on real internal failure). Caught by the orchestrator → degraded path.

---

## Policy — `Policy`

```python
Policy.from_file(path) -> Policy
get_policy() -> Policy            # cached singleton
```

Key accessors (all read-only, all sourced from `policy_terms.json`):

| Method | Returns |
|--------|---------|
| `get_member(id)` | member dict or `None` |
| `member_join_date(id)` | `date` (dependents inherit primary's) |
| `category_config(category)` | the `opd_categories` entry |
| `document_requirements(category)` | `{required[], optional[]}` |
| `per_claim_limit()` / `annual_opd_limit()` | floats |
| `effective_claim_cap(category)` | `max(per_claim_limit, sub_limit)` |
| `is_network_hospital(name)` | bool |
| `waiting_periods` / `exclusions` / `pre_authorization` / `fraud_thresholds` | raw sub-dicts |

- **Raises:** `FileNotFoundError` / `JSONDecodeError` at load time only.

---

## API — `app.main`

| Method & path | Input | Output | Errors |
|---------------|-------|--------|--------|
| `GET /` | — | UI (HTML) | — |
| `GET /api/health` | — | `{status, policy}` | — |
| `GET /api/policy` | — | policy summary | — |
| `GET /api/test-cases` | — | the 12 eval cases | — |
| `POST /api/claims` | claim JSON | `ClaimResult` JSON | `422` with field-level detail on invalid input |

The boundary validates input with Pydantic and returns a precise `422` before
any business logic runs — untrusted input never reaches the pipeline unvalidated.
