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
- **Member message:** For a consultation claim we need: prescription, hospital bill. You uploaded 2 x prescription. Missing: hospital bill. Please upload the following document(s): hospital bill.
- **Document issues:**
    - `DocumentIssueCode.MISSING_REQUIRED_DOCUMENT` For a consultation claim we need: prescription, hospital bill. You uploaded 2 x prescription. Missing: hospital bill. → Please upload the following document(s): hospital bill.
- **Trace:**
    - [PASS] `intake.policy` — Policy PLUM_GHI_2024 resolved
        - data: `{"policy_id": "PLUM_GHI_2024"}`
    - [PASS] `intake.member` — Member resolved: Rajesh Kumar (EMP001)
        - data: `{"member_id": "EMP001"}`
    - [FAIL] `document_verification.required_types` — Missing required document(s): hospital bill
        - data: `{"required": ["PRESCRIPTION", "HOSPITAL_BILL"], "uploaded": ["PRESCRIPTION", "PRESCRIPTION"], "missing": ["HOSPITAL_BILL"]}`
    - [PASS] `document_verification.readability` — All documents are legible
    - [PASS] `document_verification.patient_consistency` — No patient names to cross-check
        - data: `{"names": {}}`

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
    - `DocumentIssueCode.UNREADABLE_DOCUMENT` The pharmacy bill you uploaded (blurry_bill.jpg) is too blurry/low-quality to read. We have NOT rejected your claim. → Please re-upload a clear photo or scan of the pharmacy bill.
- **Trace:**
    - [PASS] `intake.policy` — Policy PLUM_GHI_2024 resolved
        - data: `{"policy_id": "PLUM_GHI_2024"}`
    - [PASS] `intake.member` — Member resolved: Sneha Reddy (EMP004)
        - data: `{"member_id": "EMP004"}`
    - [PASS] `document_verification.required_types` — All required document types are present
        - data: `{"required": ["PRESCRIPTION", "PHARMACY_BILL"], "uploaded": ["PRESCRIPTION", "PHARMACY_BILL"]}`
    - [FAIL] `document_verification.readability` — Document F004 (pharmacy bill) is unreadable
        - data: `{"file_id": "F004", "quality": "UNREADABLE"}`
    - [PASS] `document_verification.patient_consistency` — No patient names to cross-check
        - data: `{"names": {}}`

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
    - `DocumentIssueCode.PATIENT_MISMATCH` The uploaded documents name different patients (F005: 'Rajesh Kumar'; F006: 'Arjun Mehta'). All documents in one claim must belong to the same patient. → Please ensure every document is for the same patient and re-upload the corrected set.
- **Trace:**
    - [PASS] `intake.policy` — Policy PLUM_GHI_2024 resolved
        - data: `{"policy_id": "PLUM_GHI_2024"}`
    - [PASS] `intake.member` — Member resolved: Rajesh Kumar (EMP001)
        - data: `{"member_id": "EMP001"}`
    - [PASS] `document_verification.required_types` — All required document types are present
        - data: `{"required": ["PRESCRIPTION", "HOSPITAL_BILL"], "uploaded": ["PRESCRIPTION", "HOSPITAL_BILL"]}`
    - [PASS] `document_verification.readability` — All documents are legible
    - [FAIL] `document_verification.patient_consistency` — Documents belong to different patients
        - data: `{"names": {"F005": "Rajesh Kumar", "F006": "Arjun Mehta"}}`

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
    - LineItemStatus.APPROVED: Consultation Fee — claimed 1000.0, approved 1000.0
    - LineItemStatus.APPROVED: CBC Test — claimed 300.0, approved 300.0
    - LineItemStatus.APPROVED: Dengue NS1 Test — claimed 200.0, approved 200.0
- **Calculation:** Covered amount: 1500.0 → Co-pay (10%): -150.0 → Final approved amount: 1350.0
- **Trace:**
    - [PASS] `intake.policy` — Policy PLUM_GHI_2024 resolved
        - data: `{"policy_id": "PLUM_GHI_2024"}`
    - [PASS] `intake.member` — Member resolved: Rajesh Kumar (EMP001)
        - data: `{"member_id": "EMP001"}`
    - [PASS] `document_verification.required_types` — All required document types are present
        - data: `{"required": ["PRESCRIPTION", "HOSPITAL_BILL"], "uploaded": ["PRESCRIPTION", "HOSPITAL_BILL"]}`
    - [PASS] `document_verification.readability` — All documents are legible
    - [PASS] `document_verification.patient_consistency` — All documents reference the same patient
        - data: `{"names": {"F007": "Rajesh Kumar", "F008": "Rajesh Kumar"}}`
    - [PASS] `extraction.summary` — Extracted 2 document(s)
        - data: `{"sources": {"F007": "PROVIDED", "F008": "PROVIDED"}, "diagnosis": "Viral Fever", "line_item_count": 3}`
    - [PASS] `adjudication.coverage` — Consultation is a covered category
        - data: `{"category": "CONSULTATION"}`
    - [PASS] `adjudication.exclusion` — No blanket policy exclusion matched
        - data: `{"diagnosis": "Viral Fever"}`
    - [PASS] `adjudication.waiting_period` — No waiting-period restriction applies
        - data: `{"join_date": "2024-04-01"}`
    - [PASS] `adjudication.pre_authorization` — No pre-authorization requirement triggered
        - data: `{"high_value_tests": []}`
    - [PASS] `adjudication.per_claim_limit` — Within per-claim limit (₹1,500 ≤ ₹5,000)
        - data: `{"covered_total": 1500.0, "limit": 5000.0}`
    - [PASS] `adjudication.decision` — APPROVED: approved ₹1,350
        - data: `{"calculation": [{"label": "Covered amount", "amount": 1500.0}, {"label": "Co-pay (10%)", "amount": -150.0}, {"label": "Final approved amount", "amount": 1350.0}]}`
    - [PASS] `fraud.detection` — No fraud signals detected
        - data: `{"signals": [], "same_day_count": 1}`

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
    - [PASS] `intake.policy` — Policy PLUM_GHI_2024 resolved
        - data: `{"policy_id": "PLUM_GHI_2024"}`
    - [PASS] `intake.member` — Member resolved: Vikram Joshi (EMP005)
        - data: `{"member_id": "EMP005"}`
    - [PASS] `document_verification.required_types` — All required document types are present
        - data: `{"required": ["PRESCRIPTION", "HOSPITAL_BILL"], "uploaded": ["PRESCRIPTION", "HOSPITAL_BILL"]}`
    - [PASS] `document_verification.readability` — All documents are legible
    - [PASS] `document_verification.patient_consistency` — All documents reference the same patient
        - data: `{"names": {"F009": "Vikram Joshi", "F010": "Vikram Joshi"}}`
    - [PASS] `extraction.summary` — Extracted 2 document(s)
        - data: `{"sources": {"F009": "PROVIDED", "F010": "PROVIDED"}, "diagnosis": "Type 2 Diabetes Mellitus", "line_item_count": 0}`
    - [PASS] `adjudication.coverage` — Consultation is a covered category
        - data: `{"category": "CONSULTATION"}`
    - [PASS] `adjudication.exclusion` — No blanket policy exclusion matched
        - data: `{"diagnosis": "Type 2 Diabetes Mellitus"}`
    - [FAIL] `adjudication.waiting_period` — Claim falls within the 90-day waiting period for diabetes. The member joined on 2024-09-01 and is eligible for diabetes-related claims from 2024-11-30.
        - data: `{"type": "diabetes", "waiting_days": 90, "join_date": "2024-09-01", "eligible_from": "2024-11-30"}`
    - [PASS] `fraud.detection` — No fraud signals detected
        - data: `{"signals": [], "same_day_count": 1}`

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
    - LineItemStatus.APPROVED: Root Canal Treatment — claimed 8000.0, approved 8000.0
    - LineItemStatus.REJECTED: Teeth Whitening — claimed 4000.0, approved 0.0 (Teeth Whitening is excluded under the dental policy)
- **Calculation:** Covered amount: 8000.0 → Final approved amount: 8000.0
- **Trace:**
    - [PASS] `intake.policy` — Policy PLUM_GHI_2024 resolved
        - data: `{"policy_id": "PLUM_GHI_2024"}`
    - [PASS] `intake.member` — Member resolved: Priya Singh (EMP002)
        - data: `{"member_id": "EMP002"}`
    - [PASS] `document_verification.required_types` — All required document types are present
        - data: `{"required": ["HOSPITAL_BILL"], "uploaded": ["HOSPITAL_BILL"]}`
    - [PASS] `document_verification.readability` — All documents are legible
    - [PASS] `document_verification.patient_consistency` — All documents reference the same patient
        - data: `{"names": {"F011": "Priya Singh"}}`
    - [PASS] `extraction.summary` — Extracted 1 document(s)
        - data: `{"sources": {"F011": "PROVIDED"}, "diagnosis": null, "line_item_count": 2}`
    - [PASS] `adjudication.coverage` — Dental is a covered category
        - data: `{"category": "DENTAL"}`
    - [PASS] `adjudication.exclusion` — No blanket policy exclusion matched
        - data: `{"diagnosis": ""}`
    - [PASS] `adjudication.waiting_period` — No waiting-period restriction applies
        - data: `{"join_date": "2024-04-01"}`
    - [PASS] `adjudication.pre_authorization` — No pre-authorization requirement triggered
        - data: `{"high_value_tests": []}`
    - [PASS] `adjudication.per_claim_limit` — Within per-claim limit (₹8,000 ≤ ₹10,000)
        - data: `{"covered_total": 8000.0, "limit": 10000.0}`
    - [PASS] `adjudication.decision` — PARTIAL: approved ₹8,000
        - data: `{"calculation": [{"label": "Covered amount", "amount": 8000.0}, {"label": "Final approved amount", "amount": 8000.0}]}`
    - [PASS] `fraud.detection` — No fraud signals detected
        - data: `{"signals": [], "same_day_count": 1}`

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
    - [PASS] `intake.policy` — Policy PLUM_GHI_2024 resolved
        - data: `{"policy_id": "PLUM_GHI_2024"}`
    - [PASS] `intake.member` — Member resolved: Suresh Patil (EMP007)
        - data: `{"member_id": "EMP007"}`
    - [PASS] `document_verification.required_types` — All required document types are present
        - data: `{"required": ["PRESCRIPTION", "LAB_REPORT", "HOSPITAL_BILL"], "uploaded": ["PRESCRIPTION", "LAB_REPORT", "HOSPITAL_BILL"]}`
    - [PASS] `document_verification.readability` — All documents are legible
    - [PASS] `document_verification.patient_consistency` — No patient names to cross-check
        - data: `{"names": {}}`
    - [PASS] `extraction.summary` — Extracted 3 document(s)
        - data: `{"sources": {"F012": "PROVIDED", "F013": "PROVIDED", "F014": "PROVIDED"}, "diagnosis": "Suspected Lumbar Disc Herniation", "line_item_count": 1}`
    - [PASS] `adjudication.coverage` — Diagnostic is a covered category
        - data: `{"category": "DIAGNOSTIC"}`
    - [PASS] `adjudication.exclusion` — No blanket policy exclusion matched
        - data: `{"diagnosis": "Suspected Lumbar Disc Herniation"}`
    - [PASS] `adjudication.waiting_period` — No waiting-period restriction applies
        - data: `{"join_date": "2024-04-01"}`
    - [FAIL] `adjudication.pre_authorization` — Pre-authorization was required for MRI (amount ₹15,000 exceeds the ₹10,000 threshold) but was not obtained. To resubmit: obtain pre-authorization from the insurer before the procedure and attach the approval reference.
        - data: `{"tests": ["MRI"], "threshold": 10000, "amount": 15000.0}`
    - [PASS] `fraud.detection` — No fraud signals detected
        - data: `{"signals": [], "same_day_count": 1}`

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
    - LineItemStatus.APPROVED: Consultation Fee — claimed 2000.0, approved 2000.0
    - LineItemStatus.APPROVED: Medicines — claimed 5500.0, approved 5500.0
- **Trace:**
    - [PASS] `intake.policy` — Policy PLUM_GHI_2024 resolved
        - data: `{"policy_id": "PLUM_GHI_2024"}`
    - [PASS] `intake.member` — Member resolved: Amit Verma (EMP003)
        - data: `{"member_id": "EMP003"}`
    - [PASS] `document_verification.required_types` — All required document types are present
        - data: `{"required": ["PRESCRIPTION", "HOSPITAL_BILL"], "uploaded": ["PRESCRIPTION", "HOSPITAL_BILL"]}`
    - [PASS] `document_verification.readability` — All documents are legible
    - [PASS] `document_verification.patient_consistency` — No patient names to cross-check
        - data: `{"names": {}}`
    - [PASS] `extraction.summary` — Extracted 2 document(s)
        - data: `{"sources": {"F015": "PROVIDED", "F016": "PROVIDED"}, "diagnosis": "Gastroenteritis", "line_item_count": 2}`
    - [PASS] `adjudication.coverage` — Consultation is a covered category
        - data: `{"category": "CONSULTATION"}`
    - [PASS] `adjudication.exclusion` — No blanket policy exclusion matched
        - data: `{"diagnosis": "Gastroenteritis"}`
    - [PASS] `adjudication.waiting_period` — No waiting-period restriction applies
        - data: `{"join_date": "2024-04-01"}`
    - [PASS] `adjudication.pre_authorization` — No pre-authorization requirement triggered
        - data: `{"high_value_tests": []}`
    - [FAIL] `adjudication.per_claim_limit` — The claimed amount of ₹7,500 exceeds the per-claim limit of ₹5,000 for consultation claims. The claim cannot be approved.
        - data: `{"claimed": 7500.0, "covered_total": 7500.0, "limit": 5000.0}`
    - [PASS] `fraud.detection` — No fraud signals detected
        - data: `{"signals": [], "same_day_count": 1}`

**Eval notes:** exact match

## TC009 — Fraud Signal — Multiple Same-Day Claims ✅

_Member EMP008 has already submitted 3 claims today before this one arrives. This is the 4th claim from the same member on the same day._

- **Status:** COMPLETED
- **Decision:** MANUAL_REVIEW
- **Approved amount:** —
- **Confidence:** 0.85
- **Reasons:** ['SAME_DAY_CLAIM_VOLUME']
- **Requires manual review:** True
- **Member message:** Approved for ₹4,320. Routed to MANUAL_REVIEW due to fraud/anomaly signals: 4 claims on 2024-10-30 (limit 2). Providers: City Clinic A, City Clinic B, Wellness Center + current.
- **Calculation:** Covered amount: 4800.0 → Co-pay (10%): -480.0 → Final approved amount: 4320.0
- **Fraud signals:** SAME_DAY_CLAIM_VOLUME (FraudSeverity.HIGH)
- **Trace:**
    - [PASS] `intake.policy` — Policy PLUM_GHI_2024 resolved
        - data: `{"policy_id": "PLUM_GHI_2024"}`
    - [PASS] `intake.member` — Member resolved: Ravi Menon (EMP008)
        - data: `{"member_id": "EMP008"}`
    - [PASS] `document_verification.required_types` — All required document types are present
        - data: `{"required": ["PRESCRIPTION", "HOSPITAL_BILL"], "uploaded": ["PRESCRIPTION", "HOSPITAL_BILL"]}`
    - [PASS] `document_verification.readability` — All documents are legible
    - [PASS] `document_verification.patient_consistency` — No patient names to cross-check
        - data: `{"names": {}}`
    - [PASS] `extraction.summary` — Extracted 2 document(s)
        - data: `{"sources": {"F017": "PROVIDED", "F018": "PROVIDED"}, "diagnosis": "Migraine", "line_item_count": 0}`
    - [PASS] `adjudication.coverage` — Consultation is a covered category
        - data: `{"category": "CONSULTATION"}`
    - [PASS] `adjudication.exclusion` — No blanket policy exclusion matched
        - data: `{"diagnosis": "Migraine"}`
    - [PASS] `adjudication.waiting_period` — No waiting-period restriction applies
        - data: `{"join_date": "2024-04-01"}`
    - [PASS] `adjudication.pre_authorization` — No pre-authorization requirement triggered
        - data: `{"high_value_tests": []}`
    - [PASS] `adjudication.per_claim_limit` — Within per-claim limit (₹4,800 ≤ ₹5,000)
        - data: `{"covered_total": 4800.0, "limit": 5000.0}`
    - [PASS] `adjudication.decision` — APPROVED: approved ₹4,320
        - data: `{"calculation": [{"label": "Covered amount", "amount": 4800.0}, {"label": "Co-pay (10%)", "amount": -480.0}, {"label": "Final approved amount", "amount": 4320.0}]}`
    - [WARN] `fraud.detection` — 1 fraud signal(s) detected
        - data: `{"signals": [{"code": "SAME_DAY_CLAIM_VOLUME", "detail": "4 claims on 2024-10-30 (limit 2). Providers: City Clinic A, City Clinic B, Wellness Center + current.", "severity": "HIGH"}], "same_day_count": 4}`
    - [WARN] `decision.route` — Manual review due to fraud signals _(confidence -0.10)_
        - data: `{"signals": [{"code": "SAME_DAY_CLAIM_VOLUME", "detail": "4 claims on 2024-10-30 (limit 2). Providers: City Clinic A, City Clinic B, Wellness Center + current.", "severity": "HIGH"}]}`

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
    - LineItemStatus.APPROVED: Consultation Fee — claimed 1500.0, approved 1500.0
    - LineItemStatus.APPROVED: Medicines — claimed 3000.0, approved 3000.0
- **Calculation:** Covered amount: 4500.0 → Network discount (20%): -900.0 → After network discount: 3600.0 → Co-pay (10%): -360.0 → Final approved amount: 3240.0
- **Trace:**
    - [PASS] `intake.policy` — Policy PLUM_GHI_2024 resolved
        - data: `{"policy_id": "PLUM_GHI_2024"}`
    - [PASS] `intake.member` — Member resolved: Deepak Shah (EMP010)
        - data: `{"member_id": "EMP010"}`
    - [PASS] `document_verification.required_types` — All required document types are present
        - data: `{"required": ["PRESCRIPTION", "HOSPITAL_BILL"], "uploaded": ["PRESCRIPTION", "HOSPITAL_BILL"]}`
    - [PASS] `document_verification.readability` — All documents are legible
    - [PASS] `document_verification.patient_consistency` — All documents reference the same patient
        - data: `{"names": {"F019": "Deepak Shah", "F020": "Deepak Shah"}}`
    - [PASS] `extraction.summary` — Extracted 2 document(s)
        - data: `{"sources": {"F019": "PROVIDED", "F020": "PROVIDED"}, "diagnosis": "Acute Bronchitis", "line_item_count": 2}`
    - [PASS] `adjudication.coverage` — Consultation is a covered category
        - data: `{"category": "CONSULTATION"}`
    - [PASS] `adjudication.exclusion` — No blanket policy exclusion matched
        - data: `{"diagnosis": "Acute Bronchitis"}`
    - [PASS] `adjudication.waiting_period` — No waiting-period restriction applies
        - data: `{"join_date": "2024-04-01"}`
    - [PASS] `adjudication.pre_authorization` — No pre-authorization requirement triggered
        - data: `{"high_value_tests": []}`
    - [PASS] `adjudication.per_claim_limit` — Within per-claim limit (₹4,500 ≤ ₹5,000)
        - data: `{"covered_total": 4500.0, "limit": 5000.0}`
    - [PASS] `adjudication.decision` — APPROVED: approved ₹3,240
        - data: `{"calculation": [{"label": "Covered amount", "amount": 4500.0}, {"label": "Network discount (20%)", "amount": -900.0}, {"label": "After network discount", "amount": 3600.0}, {"label": "Co-pay (10%)", "amount": -360.0}, {"label": "Final approved amount", "amount": 3240.0}]}`
    - [PASS] `fraud.detection` — No fraud signals detected
        - data: `{"signals": [], "same_day_count": 1}`

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
    - LineItemStatus.APPROVED: Panchakarma Therapy (5 sessions) — claimed 3000.0, approved 3000.0
    - LineItemStatus.APPROVED: Consultation — claimed 1000.0, approved 1000.0
- **Calculation:** Covered amount: 4000.0 → Final approved amount: 4000.0
- **Trace:**
    - [PASS] `intake.policy` — Policy PLUM_GHI_2024 resolved
        - data: `{"policy_id": "PLUM_GHI_2024"}`
    - [PASS] `intake.member` — Member resolved: Kavita Nair (EMP006)
        - data: `{"member_id": "EMP006"}`
    - [PASS] `document_verification.required_types` — All required document types are present
        - data: `{"required": ["PRESCRIPTION", "HOSPITAL_BILL"], "uploaded": ["PRESCRIPTION", "HOSPITAL_BILL"]}`
    - [PASS] `document_verification.readability` — All documents are legible
    - [PASS] `document_verification.patient_consistency` — No patient names to cross-check
        - data: `{"names": {}}`
    - [PASS] `extraction.summary` — Extracted 2 document(s)
        - data: `{"sources": {"F021": "PROVIDED", "F022": "PROVIDED"}, "diagnosis": "Chronic Joint Pain", "line_item_count": 2}`
    - [PASS] `adjudication.coverage` — Alternative_Medicine is a covered category
        - data: `{"category": "ALTERNATIVE_MEDICINE"}`
    - [PASS] `adjudication.exclusion` — No blanket policy exclusion matched
        - data: `{"diagnosis": "Chronic Joint Pain"}`
    - [PASS] `adjudication.waiting_period` — No waiting-period restriction applies
        - data: `{"join_date": "2024-04-01"}`
    - [PASS] `adjudication.pre_authorization` — No pre-authorization requirement triggered
        - data: `{"high_value_tests": []}`
    - [PASS] `adjudication.per_claim_limit` — Within per-claim limit (₹4,000 ≤ ₹8,000)
        - data: `{"covered_total": 4000.0, "limit": 8000.0}`
    - [PASS] `adjudication.decision` — APPROVED: approved ₹4,000
        - data: `{"calculation": [{"label": "Covered amount", "amount": 4000.0}, {"label": "Final approved amount", "amount": 4000.0}]}`
    - [ERROR] `fraud.detection` — Component failed and was skipped: fraud detection component failed (simulated) _(confidence -0.35)_
        - data: `{"error": "fraud detection component failed (simulated)", "error_type": "ComponentFailure"}`

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
    - [PASS] `intake.policy` — Policy PLUM_GHI_2024 resolved
        - data: `{"policy_id": "PLUM_GHI_2024"}`
    - [PASS] `intake.member` — Member resolved: Anita Desai (EMP009)
        - data: `{"member_id": "EMP009"}`
    - [PASS] `document_verification.required_types` — All required document types are present
        - data: `{"required": ["PRESCRIPTION", "HOSPITAL_BILL"], "uploaded": ["PRESCRIPTION", "HOSPITAL_BILL"]}`
    - [PASS] `document_verification.readability` — All documents are legible
    - [PASS] `document_verification.patient_consistency` — No patient names to cross-check
        - data: `{"names": {}}`
    - [PASS] `extraction.summary` — Extracted 2 document(s)
        - data: `{"sources": {"F023": "PROVIDED", "F024": "PROVIDED"}, "diagnosis": "Morbid Obesity \u2014 BMI 37", "line_item_count": 2}`
    - [PASS] `adjudication.coverage` — Consultation is a covered category
        - data: `{"category": "CONSULTATION"}`
    - [FAIL] `adjudication.exclusion` — This claim is for an excluded condition. Diagnosis/treatment ('Morbid Obesity — BMI 37') falls under the policy exclusion: 'Obesity and weight loss programs'. Excluded conditions are not payable.
        - data: `{"matched_exclusion": "Obesity and weight loss programs", "diagnosis": "Morbid Obesity \u2014 BMI 37", "treatment": "Bariatric Consultation and Customised Diet Plan"}`
    - [PASS] `fraud.detection` — No fraud signals detected
        - data: `{"signals": [], "same_day_count": 1}`

**Eval notes:** confidence: expected above 0.90, got 0.95
