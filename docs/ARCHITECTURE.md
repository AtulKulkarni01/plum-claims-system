# Architecture

## 1. What this system does

It takes a health-insurance claim (member details, treatment type, claimed
amount, uploaded documents) and produces an **explainable** decision —
`APPROVED`, `PARTIAL`, `REJECTED`, or `MANUAL_REVIEW` — or stops early and tells
the member exactly which document to fix. Every output carries a full,
step-by-step trace so an operations reviewer can reconstruct *why* any claim got
any decision.

## 2. The shape: a linear multi-agent pipeline with one gate

```
                    ┌─────────────────────────── Orchestrator ───────────────────────────┐
                    │  owns the Trace, the ClaimResult, and the failure boundary           │
  ClaimSubmission ─▶│                                                                      │
                    │  Intake ─▶ Document Verification ──(issues?)──▶ STOP (decision=null) │
                    │              │ no issues                                              │
                    │              ▼                                                        │
                    │  Extraction (async, per-doc)                                         │
                    │              ▼                                                        │
                    │  Adjudication (policy rules + financials)                            │
                    │              ▼                                                        │
                    │  Fraud / Anomaly detection                                           │
                    │              ▼                                                        │
                    │  Decision assembly (decision + confidence + member message)          │
                    └──────────────────────────────────────────────────┬─────────────────┘
                                                                         ▼
                                                                   ClaimResult (+ trace)
```

Each box is a small, single-responsibility **agent** with a typed contract
(`docs/COMPONENT_CONTRACTS.md`). They never share mutable state; they
communicate through Pydantic objects and append to a shared `Trace`.

### Why a pipeline and not a free-for-all of agents

The claims problem is a **sequential decision process with a hard gate**: you
cannot adjudicate before you know the documents are valid, and you cannot decide
the payout before you have extracted the numbers. A deterministic pipeline makes
the data flow obvious, the trace linear and readable, and every stage unit-testable
in isolation. A "swarm" of autonomous agents negotiating would add
non-determinism and latency for no benefit here. The agents are still cleanly
separated (the bonus "multi-agentic" property) — they are just *orchestrated*
rather than *emergent*.

## 3. Components and responsibilities

| Component | Responsibility | Can stop pipeline? |
|-----------|----------------|--------------------|
| **Orchestrator** (`orchestrator.py`) | Run stages in order, own trace + result, catch failures, compute confidence | — |
| **Intake** | Resolve member against the roster, structural validation | no |
| **Document Verification** (`agents/document_verification.py`) | Catch wrong/missing docs, unreadable docs, patient mismatch — with specific member messages | **yes (the only gate)** |
| **Extraction** (`agents/extraction.py`) | Turn documents into structured, typed fields; async per-document; degrade on failure | no |
| **Adjudication** (`agents/adjudication.py`) | Apply policy rules (coverage, exclusions, waiting periods, pre-auth, limits) and compute the payout | no |
| **Fraud / Anomaly** (`agents/fraud.py`) | Score anomaly signals vs policy thresholds, route to manual review | no |
| **Policy** (`policy.py`) | Read-only typed accessors over `policy_terms.json` (no hardcoded rules) | — |
| **Trace** (`trace.py`) | Append-only observability log; the explanation of every decision | — |
| **LLM adapter** (`llm.py`) | Optional Gemini 2.0 Flash extraction for raw/unstructured docs (text + vision), schema-validated | — |

## 4. Three decisions I want to defend

### 4.1 The verification gate runs first and is the *only* stage that can stop

Document problems are cheap to detect and must short-circuit everything else —
there is no point extracting or adjudicating a claim whose hospital bill is for
a different patient. Crucially, the gate's job is **message quality**, not just
detection: it names the document type uploaded and the one required, names the
specific unreadable file, and lists the conflicting patient names. Generic
errors fail the assignment; specific, actionable ones pass it.

### 4.2 Failure handling lives in the orchestrator, not scattered in agents

Every non-gate stage runs inside `_safe(...)`. If it raises, the orchestrator
records an `ERROR` trace step, applies a confidence penalty, flags the claim for
manual review, and **continues with whatever it has**. This is one place to
reason about resilience instead of try/except noise in every agent. The
`simulate_component_failure` flag (TC011) just forces the fraud agent to throw,
exercising exactly this path — the system degrades to a lower-confidence
APPROVED with a "manual review recommended" note rather than 500-ing.

### 4.3 The trace is a first-class output, not logging

`ClaimResult.trace` is an ordered list of typed `TraceStep`s
(`step, status, detail, data, confidence_delta`). Confidence is literally
`0.95 + sum(confidence_delta)` across the trace — so the number is *derived from*
the same events the reviewer reads, never an opaque guess. The UI renders this
as a timeline; the eval report prints it verbatim.

## 5. Policy interpretation (conscious assumptions)

The policy file is intentionally ambiguous in places. Where the eval cases
forced a single interpretation, I committed to it and documented it:

- **Effective per-claim cap = `max(per_claim_limit, category.sub_limit)`,
  measured against the *covered* amount.** This is the only reading consistent
  with TC006 (dental ₹8,000 partial-approved although > ₹5,000 global limit),
  TC008 (consultation ₹7,500 rejected), and TC010 (₹4,500 → ₹3,240 approved).
  The category `sub_limit` is therefore treated as a per-category *annual*
  aggregate ceiling that raises the per-claim ceiling, not a hard per-claim cap.
- **Check order = coverage → exclusion → waiting → pre-auth → per-claim → partial.**
  Short-circuiting on the first hard reject yields exactly the single reason each
  eval case expects (e.g. TC012 obesity is *excluded*, not *waiting-period* or
  *per-claim*, even though all three technically apply).
- **Financial order = network discount, then co-pay** (TC010 is explicit).
- **No pre-auth reference is ever supplied**, so high-value imaging over the
  threshold is always treated as "pre-auth not obtained". A real system would
  accept and verify a pre-auth token.
- **Submission deadline is not enforced** because the eval treatment dates fall
  outside any real "today"; enforcing it would falsely reject every case. It is
  implemented as an INFO-only check, ready to enable with a reference date.
- **Waiting-period matching is whole-word** so "Lumbar Disc *Herni*ation" does
  not trip the "hernia" rule (regression-tested). Pre-auth imaging detection is
  likewise whole-word and scoped to the DIAGNOSTIC category.

Deliberately **left as known limitations** (documented rather than over-built, to
keep the core simple):

- **Network-hospital matching is lenient** (case-insensitive substring) so
  "Apollo Hospitals, Bengaluru" matches "Apollo Hospitals". A crafted name like
  "Not Apollo Hospitals" would also match; a production system would match
  against a hospital ID, not a free-text name.
- **`minimum_claim_amount` and the submission deadline are not enforced.** The
  Pydantic boundary rejects non-positive amounts; the ₹500 floor and the 30-day
  deadline are intake rules that need a trusted submission date (the eval dates
  fall outside any real "today"), so they are left as INFO-level rules.

## 6. What I considered and rejected

- **A database / queue / worker tier.** Rejected for the assignment: it adds ops
  surface without exercising any required behavior. The pipeline is pure and
  stateless, so this is a deployment choice, not a rewrite (see §7).
- **LLM-in-the-loop for adjudication.** Rejected: policy math must be
  deterministic, auditable, and testable. LLMs belong in *extraction* (messy,
  unstructured input), not in deciding money. Adjudication is plain Python over
  validated data.
- **A real OCR/vision dependency as a hard requirement.** Rejected as the
  default: the eval supplies structured `content`, and forcing a vision model
  would make the system non-deterministic and un-runnable without secrets. It is
  an *optional* adapter (`llm.py`) instead.

## 7. Limitations and the path to 10x load

Current design is a single stateless FastAPI process. At 10x (≈750k claims/yr,
bursty), the bottleneck is document extraction (LLM/OCR latency), not the rule
engine.

| Concern | Now | At 10x |
|---------|-----|--------|
| Throughput | one process, async I/O | horizontal scale behind a load balancer; the pipeline is stateless so this is trivial |
| Extraction latency | inline, async per-doc | move to a queue (SQS/Celery): submit → ack → extract+adjudicate async → notify; cache extractions by document content-hash |
| Policy data | file read at boot, cached | versioned policy store; pin each claim to the policy version it was decided under (auditability) |
| Trace storage | in the response object | append to durable store (e.g. OLAP table / object storage) keyed by claim_id for replay + analytics |
| LLM cost/limits | single model | route by document difficulty (cheap model for clean printed bills, vision model only for handwriting); batch where possible |
| Idempotency / dedup | none | content-hash + idempotency keys so retries and same-day-resubmits don't double-process |
| Human-in-the-loop | `MANUAL_REVIEW` flag | a review queue UI; feed reviewer overrides back as labeled data to tune thresholds |

None of these change the component boundaries — they are infrastructure wrapped
around the same agents. That is the point of keeping the core pure.
