# Eval Report

All 12 test cases from `test_cases.json` run through the live pipeline.

**Result: 12/12 matched expected outcomes.**

| Case | Name | Expected | Got | Match |
|------|------|----------|-----|-------|
| TC001 | Wrong Document Uploaded | null (doc stop) | null (DOCUMENT_ISSUE) | ✅ |
| TC002 | Unreadable Document | null (doc stop) | null (DOCUMENT_ISSUE) | ✅ |
| TC003 | Documents Belong to Different Patients | null (doc stop) | null (DOCUMENT_ISSUE) | ✅ |
| TC004 | Clean Consultation — Full Approval | APPROVED | APPROVED | ✅ |
| TC005 | Waiting Period — Diabetes | REJECTED | REJECTED | ✅ |
| TC006 | Dental Partial Approval — Cosmetic Exclusion | PARTIAL | PARTIAL | ✅ |
| TC007 | MRI Without Pre-Authorization | REJECTED | REJECTED | ✅ |
| TC008 | Per-Claim Limit Exceeded | REJECTED | REJECTED | ✅ |
| TC009 | Fraud Signal — Multiple Same-Day Claims | MANUAL_REVIEW | MANUAL_REVIEW | ✅ |
| TC010 | Network Hospital — Discount Applied | APPROVED | APPROVED | ✅ |
| TC011 | Component Failure — Graceful Degradation | APPROVED | APPROVED | ✅ |
| TC012 | Excluded Treatment | REJECTED | REJECTED | ✅ |

## TC001 — Wrong Document Uploaded ✅

_Member submits two prescriptions for a consultation claim that requires a prescription and a hospital bill._

- **Status:** DOCUMENT_ISSUE
- **Decision:** null (stopped at document gate)
- **Approved amount:** —
- **Confidence:** 0.95
- **Reasons:** —
- **Requires manual review:** False
- **Member message:** For a consultation claim we need: prescription, hospital bill. You uploaded 2x prescription. Missing: hospital bill. Please upload the following document(s): hospital bill.
- **Document issues:**
    - `MISSING_REQUIRED_DOCUMENT` For a consultation claim we need: prescription, hospital bill. You uploaded 2x prescription. Missing: hospital bill. → Please upload the following document(s): hospital bill.
- **Trace:**
    - [PASS] `intake.member` — Member resolved: Rajesh Kumar (EMP001)
    - [FAIL] `document_verification.required_types` — Missing required document(s): hospital bill
    - [PASS] `document_verification.readability` — All documents are legible
    - [PASS] `document_verification.patient_consistency` — No patient names to cross-check

**Eval notes:** document issue codes: ['MISSING_REQUIRED_DOCUMENT']

## TC002 — Unreadable Document ✅

_Member uploads a valid prescription but a blurry, unreadable photo of their pharmacy bill._

- **Status:** DOCUMENT_ISSUE
- **Decision:** null (stopped at document gate)
- **Approved amount:** —
- **Confidence:** 0.95
- **Reasons:** —
- **Requires manual review:** False
- **Member message:** The pharmacy bill you uploaded (blurry_bill.jpg) is too blurry/low-quality to read. We have NOT rejected your claim. Please re-upload a clear photo or scan of the pharmacy bill.
- **Document issues:**
    - `UNREADABLE_DOCUMENT` The pharmacy bill you uploaded (blurry_bill.jpg) is too blurry/low-quality to read. We have NOT rejected your claim. → Please re-upload a clear photo or scan of the pharmacy bill.
- **Trace:**
    - [PASS] `intake.member` — Member resolved: Sneha Reddy (EMP004)
    - [PASS] `document_verification.required_types` — All required document types are present
    - [FAIL] `document_verification.readability` — Document F004 (pharmacy bill) is unreadable
    - [PASS] `document_verification.patient_consistency` — No patient names to cross-check

**Eval notes:** document issue codes: ['UNREADABLE_DOCUMENT']

## TC003 — Documents Belong to Different Patients ✅

_The prescription is for Rajesh Kumar but the hospital bill is for a different patient, Arjun Mehta._

- **Status:** DOCUMENT_ISSUE
- **Decision:** null (stopped at document gate)
- **Approved amount:** —
- **Confidence:** 0.95
- **Reasons:** —
- **Requires manual review:** False
- **Member message:** The uploaded documents name different patients (F005: 'Rajesh Kumar'; F006: 'Arjun Mehta'). All documents in one claim must belong to the same patient. Please ensure every document is for the same patient and re-upload the corrected set.
- **Document issues:**
    - `PATIENT_MISMATCH` The uploaded documents name different patients (F005: 'Rajesh Kumar'; F006: 'Arjun Mehta'). All documents in one claim must belong to the same patient. → Please ensure every document is for the same patient and re-upload the corrected set.
- **Trace:**
    - [PASS] `intake.member` — Member resolved: Rajesh Kumar (EMP001)
    - [PASS] `document_verification.required_types` — All required document types are present
    - [PASS] `document_verification.readability` — All documents are legible
    - [FAIL] `document_verification.patient_consistency` — Documents belong to different patients

**Eval notes:** document issue codes: ['PATIENT_MISMATCH']

## TC004 — Clean Consultation — Full Approval ✅

_Complete, valid consultation claim with correct documents, valid member, covered treatment, within all limits._

- **Status:** COMPLETED
- **Decision:** APPROVED
- **Approved amount:** 1350.0
- **Confidence:** 0.95
- **Reasons:** —
- **Requires manual review:** False
- **Member message:** Approved for ₹1,350.
- **Line items:**
    - APPROVED: Consultation Fee — claimed 1000.0, approved 1000.0
    - APPROVED: CBC Test — claimed 300.0, approved 300.0
    - APPROVED: Dengue NS1 Test — claimed 200.0, approved 200.0
- **Calculation:** Covered amount: 1500.0 → Co-pay (10%): -150.0 → Final approved amount: 1350.0
- **Trace:**
    - [PASS] `intake.member` — Member resolved: Rajesh Kumar (EMP001)
    - [PASS] `document_verification.required_types` — All required document types are present
    - [PASS] `document_verification.readability` — All documents are legible
    - [PASS] `document_verification.patient_consistency` — All documents reference the same patient
    - [PASS] `extraction.summary` — Extracted 2 document(s)
    - [PASS] `adjudication.coverage` — Consultation is a covered category
    - [PASS] `adjudication.exclusion` — No blanket policy exclusion matched
    - [PASS] `adjudication.waiting_period` — No waiting-period restriction applies
    - [PASS] `adjudication.pre_authorization` — No pre-authorization requirement triggered
    - [PASS] `adjudication.per_claim_limit` — Within per-claim limit (₹1,500 ≤ ₹5,000)
    - [PASS] `adjudication.decision` — APPROVED: approved ₹1,350
    - [PASS] `fraud.detection` — No fraud signals detected

**Eval notes:** confidence: expected above 0.85, got 0.95

## TC005 — Waiting Period — Diabetes ✅

_Member joined 2024-09-01. Claims for diabetes treatment on 2024-10-15, which is within the 90-day waiting period for diabetes._

- **Status:** COMPLETED
- **Decision:** REJECTED
- **Approved amount:** 0.0
- **Confidence:** 0.95
- **Reasons:** ['WAITING_PERIOD']
- **Requires manual review:** False
- **Member message:** Claim falls within the 90-day waiting period for diabetes. The member joined on 2024-09-01 and is eligible for diabetes-related claims from 2024-11-30.
- **Trace:**
    - [PASS] `intake.member` — Member resolved: Vikram Joshi (EMP005)
    - [PASS] `document_verification.required_types` — All required document types are present
    - [PASS] `document_verification.readability` — All documents are legible
    - [PASS] `document_verification.patient_consistency` — All documents reference the same patient
    - [PASS] `extraction.summary` — Extracted 2 document(s)
    - [PASS] `adjudication.coverage` — Consultation is a covered category
    - [PASS] `adjudication.exclusion` — No blanket policy exclusion matched
    - [FAIL] `adjudication.waiting_period` — Claim falls within the 90-day waiting period for diabetes. The member joined on 2024-09-01 and is eligible for diabetes-related claims from 2024-11-30.
    - [PASS] `fraud.detection` — No fraud signals detected

**Eval notes:** exact match

## TC006 — Dental Partial Approval — Cosmetic Exclusion ✅

_Bill includes root canal treatment (covered) and teeth whitening (cosmetic, excluded). System must approve only the covered procedure._

- **Status:** COMPLETED
- **Decision:** PARTIAL
- **Approved amount:** 8000.0
- **Confidence:** 0.95
- **Reasons:** ['PARTIAL_EXCLUSION']
- **Requires manual review:** False
- **Member message:** Partially approved. Approved ₹8,000. Excluded line item(s): Teeth Whitening. See itemized breakdown.
- **Line items:**
    - APPROVED: Root Canal Treatment — claimed 8000.0, approved 8000.0
    - REJECTED: Teeth Whitening — claimed 4000.0, approved 0.0 (Teeth Whitening is excluded under the dental policy)
- **Calculation:** Covered amount: 8000.0 → Final approved amount: 8000.0
- **Trace:**
    - [PASS] `intake.member` — Member resolved: Priya Singh (EMP002)
    - [PASS] `document_verification.required_types` — All required document types are present
    - [PASS] `document_verification.readability` — All documents are legible
    - [PASS] `document_verification.patient_consistency` — All documents reference the same patient
    - [PASS] `extraction.summary` — Extracted 1 document(s)
    - [PASS] `adjudication.coverage` — Dental is a covered category
    - [PASS] `adjudication.exclusion` — No blanket policy exclusion matched
    - [PASS] `adjudication.waiting_period` — No waiting-period restriction applies
    - [PASS] `adjudication.pre_authorization` — No pre-authorization requirement triggered
    - [PASS] `adjudication.per_claim_limit` — Within per-claim limit (₹8,000 ≤ ₹10,000)
    - [PASS] `adjudication.decision` — PARTIAL: approved ₹8,000
    - [PASS] `fraud.detection` — No fraud signals detected

**Eval notes:** exact match

## TC007 — MRI Without Pre-Authorization ✅

_MRI scan costing ₹15,000 submitted without pre-authorization. Policy requires pre-auth for MRI above ₹10,000._

- **Status:** COMPLETED
- **Decision:** REJECTED
- **Approved amount:** 0.0
- **Confidence:** 0.95
- **Reasons:** ['PRE_AUTH_MISSING']
- **Requires manual review:** False
- **Member message:** Pre-authorization was required for MRI (amount ₹15,000 exceeds the ₹10,000 threshold) but was not obtained. To resubmit: obtain pre-authorization from the insurer before the procedure and attach the approval reference.
- **Trace:**
    - [PASS] `intake.member` — Member resolved: Suresh Patil (EMP007)
    - [PASS] `document_verification.required_types` — All required document types are present
    - [PASS] `document_verification.readability` — All documents are legible
    - [PASS] `document_verification.patient_consistency` — No patient names to cross-check
    - [PASS] `extraction.summary` — Extracted 3 document(s)
    - [PASS] `adjudication.coverage` — Diagnostic is a covered category
    - [PASS] `adjudication.exclusion` — No blanket policy exclusion matched
    - [PASS] `adjudication.waiting_period` — No waiting-period restriction applies
    - [FAIL] `adjudication.pre_authorization` — Pre-authorization was required for MRI (amount ₹15,000 exceeds the ₹10,000 threshold) but was not obtained. To resubmit: obtain pre-authorization from the insurer before the procedure and attach the approval reference.
    - [PASS] `fraud.detection` — No fraud signals detected

**Eval notes:** exact match

## TC008 — Per-Claim Limit Exceeded ✅

_Claimed amount of ₹7,500 exceeds the per-claim limit of ₹5,000._

- **Status:** COMPLETED
- **Decision:** REJECTED
- **Approved amount:** 0.0
- **Confidence:** 0.95
- **Reasons:** ['PER_CLAIM_EXCEEDED']
- **Requires manual review:** False
- **Member message:** The claimed amount of ₹7,500 exceeds the per-claim limit of ₹5,000 for consultation claims. The claim cannot be approved.
- **Line items:**
    - APPROVED: Consultation Fee — claimed 2000.0, approved 2000.0
    - APPROVED: Medicines — claimed 5500.0, approved 5500.0
- **Trace:**
    - [PASS] `intake.member` — Member resolved: Amit Verma (EMP003)
    - [PASS] `document_verification.required_types` — All required document types are present
    - [PASS] `document_verification.readability` — All documents are legible
    - [PASS] `document_verification.patient_consistency` — No patient names to cross-check
    - [PASS] `extraction.summary` — Extracted 2 document(s)
    - [PASS] `adjudication.coverage` — Consultation is a covered category
    - [PASS] `adjudication.exclusion` — No blanket policy exclusion matched
    - [PASS] `adjudication.waiting_period` — No waiting-period restriction applies
    - [PASS] `adjudication.pre_authorization` — No pre-authorization requirement triggered
    - [FAIL] `adjudication.per_claim_limit` — The claimed amount of ₹7,500 exceeds the per-claim limit of ₹5,000 for consultation claims. The claim cannot be approved.
    - [PASS] `fraud.detection` — No fraud signals detected

**Eval notes:** exact match

## TC009 — Fraud Signal — Multiple Same-Day Claims ✅

_Member EMP008 has already submitted 3 claims today before this one arrives. This is the 4th claim from the same member on the same day._

- **Status:** COMPLETED
- **Decision:** MANUAL_REVIEW
- **Approved amount:** —
- **Confidence:** 0.95
- **Reasons:** ['SAME_DAY_CLAIM_VOLUME']
- **Requires manual review:** True
- **Member message:** Approved for ₹4,320. Routed to MANUAL_REVIEW due to fraud/anomaly signals: 4 claims on 2024-10-30 (limit 2). Providers: City Clinic A, City Clinic B, Wellness Center + current.
- **Calculation:** Covered amount: 4800.0 → Co-pay (10%): -480.0 → Final approved amount: 4320.0
- **Fraud signals:** SAME_DAY_CLAIM_VOLUME (HIGH)
- **Trace:**
    - [PASS] `intake.member` — Member resolved: Ravi Menon (EMP008)
    - [PASS] `document_verification.required_types` — All required document types are present
    - [PASS] `document_verification.readability` — All documents are legible
    - [PASS] `document_verification.patient_consistency` — No patient names to cross-check
    - [PASS] `extraction.summary` — Extracted 2 document(s)
    - [PASS] `adjudication.coverage` — Consultation is a covered category
    - [PASS] `adjudication.exclusion` — No blanket policy exclusion matched
    - [PASS] `adjudication.waiting_period` — No waiting-period restriction applies
    - [PASS] `adjudication.pre_authorization` — No pre-authorization requirement triggered
    - [PASS] `adjudication.per_claim_limit` — Within per-claim limit (₹4,800 ≤ ₹5,000)
    - [PASS] `adjudication.decision` — APPROVED: approved ₹4,320
    - [WARN] `fraud.detection` — 1 fraud signal(s) detected
    - [WARN] `decision.route` — Manual review due to fraud signals

**Eval notes:** exact match

## TC010 — Network Hospital — Discount Applied ✅

_Valid claim at Apollo Hospitals, a network hospital. Network discount must be applied before co-pay._

- **Status:** COMPLETED
- **Decision:** APPROVED
- **Approved amount:** 3240.0
- **Confidence:** 0.95
- **Reasons:** —
- **Requires manual review:** False
- **Member message:** Approved for ₹3,240.
- **Line items:**
    - APPROVED: Consultation Fee — claimed 1500.0, approved 1500.0
    - APPROVED: Medicines — claimed 3000.0, approved 3000.0
- **Calculation:** Covered amount: 4500.0 → Network discount (20%): -900.0 → After network discount: 3600.0 → Co-pay (10%): -360.0 → Final approved amount: 3240.0
- **Trace:**
    - [PASS] `intake.member` — Member resolved: Deepak Shah (EMP010)
    - [PASS] `document_verification.required_types` — All required document types are present
    - [PASS] `document_verification.readability` — All documents are legible
    - [PASS] `document_verification.patient_consistency` — All documents reference the same patient
    - [PASS] `extraction.summary` — Extracted 2 document(s)
    - [PASS] `adjudication.coverage` — Consultation is a covered category
    - [PASS] `adjudication.exclusion` — No blanket policy exclusion matched
    - [PASS] `adjudication.waiting_period` — No waiting-period restriction applies
    - [PASS] `adjudication.pre_authorization` — No pre-authorization requirement triggered
    - [PASS] `adjudication.per_claim_limit` — Within per-claim limit (₹4,500 ≤ ₹5,000)
    - [PASS] `adjudication.decision` — APPROVED: approved ₹3,240
    - [PASS] `fraud.detection` — No fraud signals detected

**Eval notes:** exact match

## TC011 — Component Failure — Graceful Degradation ✅

_One component of your system fails mid-processing (simulate with the flag below). The overall pipeline must continue, produce a decision, and make the failure visible in the output with an appropriately reduced confidence score._

- **Status:** COMPLETED
- **Decision:** APPROVED
- **Approved amount:** 4000.0
- **Confidence:** 0.6
- **Reasons:** —
- **Requires manual review:** True
- **Member message:** Approved for ₹4,000. NOTE: one or more components failed during processing. Confidence is reduced and manual review is recommended due to incomplete processing.
- **Line items:**
    - APPROVED: Panchakarma Therapy (5 sessions) — claimed 3000.0, approved 3000.0
    - APPROVED: Consultation — claimed 1000.0, approved 1000.0
- **Calculation:** Covered amount: 4000.0 → Final approved amount: 4000.0
- **Trace:**
    - [PASS] `intake.member` — Member resolved: Kavita Nair (EMP006)
    - [PASS] `document_verification.required_types` — All required document types are present
    - [PASS] `document_verification.readability` — All documents are legible
    - [PASS] `document_verification.patient_consistency` — No patient names to cross-check
    - [PASS] `extraction.summary` — Extracted 2 document(s)
    - [PASS] `adjudication.coverage` — Alternative_Medicine is a covered category
    - [PASS] `adjudication.exclusion` — No blanket policy exclusion matched
    - [PASS] `adjudication.waiting_period` — No waiting-period restriction applies
    - [PASS] `adjudication.pre_authorization` — No pre-authorization requirement triggered
    - [PASS] `adjudication.per_claim_limit` — Within per-claim limit (₹4,000 ≤ ₹8,000)
    - [PASS] `adjudication.decision` — APPROVED: approved ₹4,000
    - [ERROR] `fraud.detection` — Component failed and was skipped: fraud detection component failed (simulated)

**Eval notes:** exact match

## TC012 — Excluded Treatment ✅

_Member claims for bariatric consultation and a diet program. Obesity treatment is explicitly excluded under the policy._

- **Status:** COMPLETED
- **Decision:** REJECTED
- **Approved amount:** 0.0
- **Confidence:** 0.95
- **Reasons:** ['EXCLUDED_CONDITION']
- **Requires manual review:** False
- **Member message:** This claim is for an excluded condition. Diagnosis/treatment ('Morbid Obesity — BMI 37') falls under the policy exclusion: 'Obesity and weight loss programs'. Excluded conditions are not payable.
- **Trace:**
    - [PASS] `intake.member` — Member resolved: Anita Desai (EMP009)
    - [PASS] `document_verification.required_types` — All required document types are present
    - [PASS] `document_verification.readability` — All documents are legible
    - [PASS] `document_verification.patient_consistency` — No patient names to cross-check
    - [PASS] `extraction.summary` — Extracted 2 document(s)
    - [PASS] `adjudication.coverage` — Consultation is a covered category
    - [FAIL] `adjudication.exclusion` — This claim is for an excluded condition. Diagnosis/treatment ('Morbid Obesity — BMI 37') falls under the policy exclusion: 'Obesity and weight loss programs'. Excluded conditions are not payable.
    - [PASS] `fraud.detection` — No fraud signals detected

**Eval notes:** confidence: expected above 0.90, got 0.95
