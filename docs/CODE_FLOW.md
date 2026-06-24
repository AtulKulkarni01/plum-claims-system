# End-to-End Code Flow

A complete trace of how a claim flows through the system — every file, every
function, every branch. **TC010** (the Apollo network-discount approval) is the
spine because it exercises the most; branches other cases take are flagged inline.

---

## The files, and who calls whom

```
HTTP request
   │
app/main.py ............ FastAPI routes; validates input; calls the orchestrator
   │
app/models.py .......... Pydantic types — the contract for everything that moves
   │
app/orchestrator.py .... run_claim(): runs the stages in order, owns trace+result+failure
   ├── app/agents/perception.py ............... read uploaded images → structured content (async)
   │       └── app/llm.py ..................... Gemini → OpenAI extraction failover
   ├── app/agents/document_verification.py ... the GATE (can stop the pipeline)
   ├── app/agents/extraction.py ............... documents → structured fields (async)
   │       └── app/llm.py ..................... same failover adapter
   ├── app/agents/adjudication.py ............. the policy rule engine + payout math
   └── app/agents/fraud.py .................... anomaly signals
app/policy.py .......... read-only accessors over policy_terms.json
app/trace.py ........... the append-only observability log
app/static/index.html .. UI: a "Test case" mode AND an "Upload documents" mode
```

---

## Step 0 — The HTTP request arrives (`app/main.py`)

`POST /api/claims` with the claim JSON runs:

```python
@app.post("/api/claims", response_model=ClaimResult)
async def submit_claim(payload: dict) -> ClaimResult:
    try:
        submission = ClaimSubmission.model_validate(payload)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors())
    return await run_claim(submission)
```

**Branch A — bad input:** malformed JSON (missing `member_id`, `claimed_amount: -5`, unknown `claim_category`, zero documents) → `ValidationError` → **HTTP 422** with field-level detail. The pipeline never runs.

**Branch B — valid input:** `submission` is a typed `ClaimSubmission` and we `await run_claim(submission)`.

Other endpoints: `GET /` serves the UI; `GET /api/policy` returns the policy summary **plus `llm_configured`** (so the UI can warn when no vision key is set); `GET /api/test-cases` feeds the dropdown.

---

## Step 0.5 — What validation enforced (`app/models.py`)

`ClaimSubmission.model_validate` coerced/checked every field: `claim_category` ∈ the 6 enum values, `treatment_date` parses as a date, `claimed_amount > 0`, each document's `actual_type` ∈ `DocumentType`, `quality` defaults to `GOOD`, and a validator rejects an empty `documents` list. A real upload also carries `image_base64`. Downstream code only ever passes typed objects.

---

## Step 1 — Orchestrator setup (`app/orchestrator.py`, `run_claim`)

```python
policy = policy or get_policy()          # @lru_cache singleton; reads policy_terms.json once
trace  = Trace()                          # the observability log for THIS claim
claim_id = f"CLM_{uuid.uuid4().hex[:10]}"
result = ClaimResult(claim_id=…, status=ResultStatus.IN_PROGRESS, …)
```

The result starts as **`IN_PROGRESS`** — a deliberate default. It is set to a terminal status *explicitly* at each exit (`DOCUMENT_ISSUE` at the gate, `COMPLETED` at the end), so a forgotten path surfaces as `IN_PROGRESS` (obviously wrong) rather than a false `COMPLETED`.

---

## Step 2 — Intake: resolve the member

```python
member = policy.get_member(submission.member_id)
```
TC010's `EMP010` exists → **PASS** trace step.
**Branch — unknown member:** WARN step, `-0.2` confidence, `requires_manual_review=True`; later `_finalize` routes an otherwise-payable unknown-member claim to `MANUAL_REVIEW`. (Pydantic guarantees the *id is present*, not that it *exists in the roster* — e.g. dependents `DEP003–006` are referenced but absent.)

---

## Step 3 — Perception: read uploaded images (`agents/perception.py`)

Runs **before** the gate. For each document that is a real upload (`image_base64`/`text`) with **no** `content`, and only if a vision provider is configured:

```python
res = await extract_fields(doc.actual_type.value, raw_text=doc.text, image_base64=doc.image_base64)
doc.content = res.fields                 # the gate + extraction now work off real data
doc.patient_name_on_doc = res.fields.get("patient_name") or doc.patient_name_on_doc
if res.fields.get("legible") is False: doc.quality = Quality.UNREADABLE
```

- **TC010 and all eval cases supply `content`** → perception **skips them entirely** → the deterministic path is untouched and needs no API key.
- **Branch — real image:** the LLM reads it into `content`; legibility/patient name are *derived from the document*, not given.
- **Branch — couldn't read it** (`ExtractionError`, e.g. all providers down): the doc is marked `UNREADABLE` so the gate asks the member to re-upload — never a wrong decision.

---

## Step 4 — The verification GATE (`document_verification.py`)

The **only** stage allowed to stop the pipeline. Three checks, each adding a PASS/FAIL trace step, returning a list of `DocumentIssue`s:

1. **Required types present** — TC010 has PRESCRIPTION+HOSPITAL_BILL → PASS. *(TC001: two prescriptions → `MISSING_REQUIRED_DOCUMENT` naming uploaded vs missing.)*
2. **Readability** — none `UNREADABLE` → PASS. *(TC002, or a perception-flagged image → `UNREADABLE_DOCUMENT` for that file, "re-upload"; not a rejection.)*
3. **Patient consistency** — both "Deepak Shah" → PASS. *(TC003: two names → `PATIENT_MISMATCH`.)*

```python
issues = verify_documents(submission, policy, trace)
if issues:
    result.status = ResultStatus.DOCUMENT_ISSUE   # decision stays None
    result.member_message = "<each issue + action_required>"
    ... ; return result                            # TC001/2/3 end here
```

---

## Step 5 — Extraction (`agents/extraction.py`) — async

Turns documents into one merged `ExtractedClaim`, concurrently (`asyncio.gather`). Per-document strategy:

1. **`content is not None`** → use it (`source="PROVIDED"`) — the eval path, and the output of perception.
2. **`text` that's JSON** → parse → `PROVIDED`.
3. **raw text/image + a key** → `extract_fields()` → `source="LLM:<provider>"` (failover provider recorded).
4. **nothing usable** → `source="DEGRADED"`.

**Resilience:** the per-doc wrapper catches *any* exception (not just `ExtractionError`) → a `DEGRADED` doc + WARN trace, never a crash. The merge only adds a `total` from **bill-type** docs (no double-count). Degraded docs subtract `0.1` confidence each, and:

```python
if any(d.source == "DEGRADED" for d in extracted.documents):
    result.degraded = True; result.requires_manual_review = True   # don't trust unverified data
```

For TC010 both docs are `PROVIDED` → `merged` = diagnosis "Acute Bronchitis", line_items `[1500, 3000]`, hospital "Apollo Hospitals".

---

## Step 6 — Adjudication (`agents/adjudication.py`) — the rule engine

Run through `_safe` (a throw → degrade to `MANUAL_REVIEW`, not a crash). Rules in a fixed order; the **first** hard reject wins (one reason per case):

1. **Category covered?** consultation `covered: true` → PASS. *(else `CATEGORY_NOT_COVERED`)*
2. **Blanket exclusion?** "Acute Bronchitis" matches nothing → PASS. *(TC012 obesity → `EXCLUDED_CONDITION`)*
3. **Waiting period?** join 2024-04-01; no condition match → PASS. *(TC005 diabetes → `WAITING_PERIOD` with eligibility date)*
4. **Pre-auth?** only for DIAGNOSTIC → skipped for TC010. *(TC007 MRI > ₹10k → `PRE_AUTH_MISSING`)*
5. **Line items** → both covered → `covered_total=4500`. *(TC006 whitening excluded → PARTIAL)*
6. **Per-claim limit** `max(5000, 2000)=5000`; 4500 ≤ 5000 → PASS. *(TC008 7500 → `PER_CLAIM_EXCEEDED`)*
7. **Payout:** network discount (Apollo, 20% → −900 → 3600) **then** co-pay (10% → −360 → **3240**), then annual cap. *(annual exhausted → `ANNUAL_LIMIT_EXCEEDED`)*

→ `AdjudicationOutcome{decision=APPROVED, approved_amount=3240, …}`.

---

## Step 7 — Fraud / anomaly (`agents/fraud.py`)

Also via `_safe`.
```python
if submission.simulate_component_failure: raise ComponentFailure(...)   # TC011
```
Else checks `policy.fraud_thresholds`: same-day volume, monthly volume, high-value. TC010 → none → `[]`.
*(TC009: 4 same-day > limit 2 → `SAME_DAY_CLAIM_VOLUME` HIGH. TC011: the raise is caught → ERROR trace, −0.35 confidence, degraded, pipeline continues.)*

---

## Step 8 — Decision assembly (`_finalize`)

Sets line items, calculation, amount, reasons. Then a shared `route()` helper can flip a *payable* claim to `MANUAL_REVIEW`:
1. **HIGH fraud signals** → none for TC010. *(TC009 routes here)*
2. **`auto_manual_review_above` (25000)** → 4500 ≤ 25000 → skip. *(holds even if fraud crashed)*
3. **member not known** → known → skip.

**Degraded branch:** if `result.degraded` (TC011, or any unread document), append the "components failed / manual review recommended" note and force `requires_manual_review`. TC010 stays `APPROVED`.

---

## Step 9 — Terminal status + confidence

```python
result.status = ResultStatus.COMPLETED                       # set explicitly here
result.confidence_score = round(clamp(0.95 + Σ trace.confidence_delta, 0, 1), 2)
result.trace = trace.steps
return result
```
Confidence is **literally `0.95 + the sum of penalties recorded in the trace`** — the same events the reviewer reads produce the number. TC010 → 0.95; TC011 → 0.60.

Penalties that can fire: unknown member (−0.2), unknown join date (−0.2), degraded extraction (−0.1×docs), per-doc extraction error (−0.15), component failure via `_safe` (−0.35).

---

## Step 10 — Response → UI (`static/index.html`)

`run_claim` returns the `ClaimResult`; FastAPI serializes it. The UI has two modes:
- **Test case** — pick TC001–TC012 or paste JSON, POST as-is.
- **Upload documents** — fill the claim form, attach image files (each with a document-type dropdown); files are base64-encoded and sent as `image_base64`, which drives the **perception** path. A banner warns if no vision provider is configured.

`render(r)` builds: decision badge + amount, confidence bar, reason chips, member message, then cards for line items, payout calculation (the −900 / −360 steps), fraud signals, extracted data, and the **decision trace** as a timeline. A `DOCUMENT_ISSUE` result shows the orange "STOPPED" badge + the document-issues card instead.

---

## The cross-cutting pieces

- **`app/llm.py`** — extraction failover: `extract_fields` tries a provider chain **Gemini → OpenAI**, retrying each with exponential backoff, returns `ExtractionResult{fields, provider, attempts}`, raises only when all providers are exhausted. Output is schema-constrained per provider and re-validated with Pydantic. Used by both perception and extraction.
- **`app/trace.py`** — `Trace.add(...)` appends a typed `TraceStep`; `steps` returns a *copy*; `total_confidence_delta()` is summed for confidence.
- **`app/policy.py`** — read-only accessors over `policy_terms.json`; `effective_claim_cap` = `max(per_claim_limit, sub_limit)`; uppercase claim category → lowercase policy key.
- **`_safe` (orchestrator)** — the single failure boundary: `try fn() → (value, False)` else `(default, True)` + an ERROR trace step + `-0.35`. Resilience lives in one place.

---

Full path with no skips: **HTTP → validate → intake → perception (read uploads) → gate (maybe stop) → async extract (failover) → adjudicate (ordered rules + payout) → fraud → finalize (routing) → status COMPLETED → confidence → JSON → UI.**
