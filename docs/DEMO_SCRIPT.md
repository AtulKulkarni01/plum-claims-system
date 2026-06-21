# Demo Video Script (8–12 min)

A shot-by-shot script for the walkthrough. The assignment asks for three things:
a claim stopped early for a document problem, a successful end-to-end approval
with the full trace, and one decision I'm proud of + one I'd change. This script
covers all three plus a short architecture framing.

**Setup before recording:** `uvicorn app.main:app --reload`, open
`http://localhost:8000`, and have `docs/ARCHITECTURE.md` and the codebase open in
an editor.

---

## 0 · Framing (1 min)

> "This is a health-insurance claims adjudication system. A member submits
> documents and a claim; the system verifies the documents, extracts the data,
> applies the policy, checks for fraud, and returns an explainable decision — or
> stops early and tells the member exactly what to fix. Everything you'll see is
> driven by `policy_terms.json`; no policy rule is hardcoded. It's a multi-agent
> pipeline, and the thing I care most about is that every decision is fully
> reconstructable from its trace."

Show the architecture diagram in `docs/ARCHITECTURE.md` §2 for ~15 seconds.

---

## 1 · A claim stopped early for a document problem (2 min)

In the UI, select **TC001 — Wrong Document Uploaded**. Click **Adjudicate claim**.

Point out:
- The orange **STOPPED · DOCUMENT ISSUE** badge — `decision` is null, nothing
  was adjudicated.
- The **Document issues** card: the message names what was uploaded
  (*prescription*) and what's required (*hospital bill*) — not a generic error.
- The **trace**: `document_verification.required_types` is `FAIL`, and the later
  stages never ran.

Then quickly run **TC002** (unreadable bill — "re-upload this specific file, we
have NOT rejected your claim") and **TC003** (patient mismatch — names both
patients). One sentence each: "the gate is the only stage allowed to stop the
pipeline, and its job is message quality, not just detection."

---

## 2 · A successful end-to-end approval with the full trace (3–4 min)

Select **TC010 — Network Hospital — Discount Applied**. Adjudicate.

Walk top to bottom:
- **APPROVED**, ₹3,240 of ₹4,500 claimed, confidence 95%.
- **Payout calculation** card — this is the one I'd linger on:
  Covered ₹4,500 → **network discount 20%** (−₹900) → ₹3,600 → **co-pay 10%**
  (−₹360) → **₹3,240**. "Network discount is applied *before* co-pay — order
  matters, and the breakdown is in the output, not buried in code."
- **Extracted data** card — the fields the pipeline pulled and the per-document
  source (`PROVIDED` here; would be `LLM` for a real scanned doc).
- **Decision trace** — scroll through: member resolved → all three document
  checks PASS → extraction → coverage → exclusion → waiting period → pre-auth →
  per-claim limit → final decision. "An ops reviewer can reconstruct exactly why
  this got ₹3,240 without reading a line of code."

Optional 30s: run **TC006** (dental partial) to show line-item itemization —
root canal approved, teeth whitening rejected with a per-line reason.

---

## 3 · Resilience, briefly (1 min)

Select **TC011 — Component Failure**. Adjudicate.

> "This claim sets a flag that forces the fraud component to crash mid-pipeline.
> Notice: it still returns APPROVED — but confidence drops to ~0.6, the trace
> shows an `ERROR` step for the failed component, and it's flagged for manual
> review. The system degrades; it never 500s. That try/except boundary lives in
> one place — the orchestrator — so resilience is one thing to reason about, not
> scattered everywhere."

---

## 4 · One decision I'm proud of, one I'd change (2 min)

**Proud of — the trace as a first-class output, not logging.**
Open `app/orchestrator.py` and `app/trace.py`.
> "Confidence isn't a vibe — it's literally `0.95 + the sum of confidence deltas`
> recorded across the trace. The number the reviewer sees is derived from the
> same events they read. Observability was the design center, not an afterthought,
> and it's why I chose a deterministic pipeline over an autonomous agent swarm —
> a linear trace is reconstructable; emergent agent chatter isn't."

**Would change — policy interpretation is reverse-engineered, not configured.**
Open `app/agents/adjudication.py` (the check-order comment) and
`docs/ARCHITECTURE.md` §5.
> "The policy file is ambiguous about how limits compose, so I committed to one
> reading — effective per-claim cap = max(per_claim_limit, sub_limit) — and
> documented it. With more time I'd make the rule *engine* data-driven: express
> check order, exclusion keywords, and limit composition as declarative
> configuration so a non-engineer could change policy without touching Python.
> Right now the values come from the file but the *logic* is still in code."

Close on the numbers: **12/12 eval cases pass, 54 tests, 90% coverage** — and
point to `docs/EVAL_REPORT.md`.

---

## Timing cheat-sheet

| Section | Target |
|---------|--------|
| Framing | 1:00 |
| Document stop | 2:00 |
| Full approval + trace | 3:30 |
| Resilience | 1:00 |
| Proud / would-change | 2:00 |
| Buffer | 0:30 |
| **Total** | **~10:00** |
