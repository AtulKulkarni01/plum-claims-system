"""API boundary tests via FastAPI TestClient."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_ok():
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
    assert r.json()["policy"]["policy_id"] == "PLUM_GHI_2024"


def test_ui_served():
    r = client.get("/")
    assert r.status_code == 200
    assert "Claims" in r.text


def test_test_cases_endpoint():
    r = client.get("/api/test-cases")
    assert r.status_code == 200
    assert len(r.json()["test_cases"]) == 12


def test_submit_valid_claim(test_cases):
    r = client.post("/api/claims", json=test_cases["TC004"]["input"])
    assert r.status_code == 200
    body = r.json()
    assert body["decision"] == "APPROVED"
    assert body["approved_amount"] == 1350


def test_invalid_payload_returns_422():
    r = client.post("/api/claims", json={"member_id": "EMP001"})  # missing fields
    assert r.status_code == 422


def test_negative_amount_rejected_at_boundary():
    r = client.post("/api/claims", json={
        "member_id": "EMP001", "policy_id": "PLUM_GHI_2024",
        "claim_category": "CONSULTATION", "treatment_date": "2024-11-01",
        "claimed_amount": -5,
        "documents": [{"file_id": "A", "actual_type": "HOSPITAL_BILL"}],
    })
    assert r.status_code == 422
