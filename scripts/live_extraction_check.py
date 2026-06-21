"""Live end-to-end check of the real LLM extraction path.

Unlike the pytest suite (which is deterministic and never hits the network), this
script makes a REAL Gemini call. It loads keys from .env, feeds two unstructured
document texts (no `content`) into the full pipeline, and prints what the model
extracted and the decision the system reached.

    python -m scripts.live_extraction_check
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Load .env (the app reads os.environ directly; it does not auto-load .env).
env_path = ROOT / ".env"
if env_path.exists():
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        if val.strip():
            os.environ.setdefault(key.strip(), val.strip())

from app.llm import llm_available  # noqa: E402
from app.models import ClaimSubmission  # noqa: E402
from app.orchestrator import run_claim  # noqa: E402

PRESCRIPTION = """Dr. Arun Sharma, MBBS, MD (Internal Medicine)
Reg. No: KA/45678/2015
City Medical Centre, 12 MG Road, Bengaluru
Patient: Rajesh Kumar     Date: 01-Nov-2024
Age: 39   Gender: M
Diagnosis: Viral Fever
Rx: Tab Paracetamol 650mg, Tab Vitamin C 500mg
"""

BILL = """CITY MEDICAL CENTRE, Bengaluru
Bill No: CMC/2024/08321    Date: 01-Nov-2024
Patient Name: Rajesh Kumar
Consultation Fee (OPD) ........ 1000
CBC (Complete Blood Count) .... 300
Dengue NS1 Antigen Test ....... 200
Total Amount: 1500
"""


async def main() -> None:
    print(f"llm_available: {llm_available()}")
    if not llm_available():
        print("No GEMINI_API_KEY / OPENAI_API_KEY found in .env — cannot run the live check.")
        return

    submission = ClaimSubmission.model_validate({
        "member_id": "EMP001",
        "policy_id": "PLUM_GHI_2024",
        "claim_category": "CONSULTATION",
        "treatment_date": "2024-11-01",
        "claimed_amount": 1500,
        "documents": [
            {"file_id": "RX", "actual_type": "PRESCRIPTION", "text": PRESCRIPTION},
            {"file_id": "BILL", "actual_type": "HOSPITAL_BILL", "text": BILL},
        ],
    })

    result = await run_claim(submission)
    ex = result.extracted

    print("\n--- what the LLM extracted ---")
    print(f"sources    : {[d.source for d in ex.documents] if ex else None}")
    print(f"diagnosis  : {ex.diagnosis if ex else None}")
    print(f"patient    : {ex.patient_name if ex else None}")
    print(f"line_items : {[(li.description, li.amount) for li in ex.line_items] if ex else None}")
    print(f"total      : {ex.total if ex else None}")

    print("\n--- decision ---")
    print(f"status     : {result.status.value}")
    print(f"decision   : {result.decision.value if result.decision else None}")
    print(f"approved   : {result.approved_amount}")
    print(f"confidence : {result.confidence_score}")
    print(f"message    : {result.member_message}")

    print("\n--- LLM trace steps ---")
    for s in result.trace:
        if s.step in ("perception.read", "extraction.llm", "extraction.summary"):
            print(f"  [{s.status.value}] {s.step} — {s.detail}")

    # Inputs had no `content` — only raw text. So if the perception stage ran and
    # diagnosis/line items are now populated, Gemini must have read them.
    perceived = [s for s in result.trace if s.step == "perception.read"]
    providers = sorted({s.data.get("provider", "?") for s in perceived})
    used_llm = bool(perceived) and bool(ex) and bool(ex.diagnosis)
    if used_llm:
        print(f"\nRESULT: PASS — documents read end to end via {', '.join(providers)}")
    else:
        print("\nRESULT: FAIL — LLM path was not exercised")


if __name__ == "__main__":
    asyncio.run(main())
