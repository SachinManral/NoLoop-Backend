import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.services.patient_service import get_aadhaar_last4, hash_aadhaar


import random


def gen_valid_aadhaar() -> str:
    from app.services.patient_service import validate_verhoeff
    while True:
        candidate = f"9{random.randint(10000000000, 99999999999)}"
        if validate_verhoeff(candidate):
            return candidate


def test_hash_aadhaar_and_last4():
    aadhaar = "367598341235"
    a_hash = hash_aadhaar(aadhaar)
    last4 = get_aadhaar_last4(aadhaar)

    assert len(a_hash) == 64  # HMAC-SHA256 hex length
    assert last4 == "XXXX-XXXX-1235"


def test_patient_registration_with_aadhaar():
    with TestClient(app) as client:
        unique_aadhaar = gen_valid_aadhaar()
        payload = {
            "insurerTenantId": "tnt_star_01",
            "name": "Unique Test Patient",
            "age": 35,
            "gender": "Female",
            "phone": "9876543210",
            "aadhaarNumber": unique_aadhaar,
        }
        response = client.post("/patients/register", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert "healthId" in data
        assert data["healthId"].startswith("NL-HID-")
        assert data["aadhaarLast4"] == f"XXXX-XXXX-{unique_aadhaar[-4:]}"
        assert data["name"] == "Unique Test Patient"


def test_patient_lookup_by_aadhaar():
    with TestClient(app) as client:
        unique_aadhaar = gen_valid_aadhaar()
        payload = {
            "insurerTenantId": "tnt_star_01",
            "name": "Lookup Test Patient",
            "age": 40,
            "gender": "Male",
            "phone": "9876543210",
            "aadhaarNumber": unique_aadhaar,
        }
        client.post("/patients/register", json=payload)

        response = client.get(f"/patients/lookup-by-aadhaar?aadhaarNumber={unique_aadhaar}")
        assert response.status_code == 200
        data = response.json()
        assert data["aadhaarLast4"] == f"XXXX-XXXX-{unique_aadhaar[-4:]}"
        assert data["healthId"].startswith("NL-HID-")


def test_patient_lookup_by_health_id():
    with TestClient(app) as client:
        unique_aadhaar = gen_valid_aadhaar()
        payload = {
            "insurerTenantId": "tnt_star_01",
            "name": "Health ID Test Patient",
            "age": 28,
            "gender": "Female",
            "phone": "9876543210",
            "aadhaarNumber": unique_aadhaar,
        }
        reg_res = client.post("/patients/register", json=payload)
        health_id = reg_res.json()["healthId"]

        response = client.get(f"/patients/by-health-id/{health_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["healthId"] == health_id
        assert data["name"] == "Health ID Test Patient"


def test_duplicate_aadhaar_registration_rejected():
    with TestClient(app) as client:
        unique_aadhaar = gen_valid_aadhaar()
        payload = {
            "insurerTenantId": "tnt_star_01",
            "name": "First Patient",
            "age": 30,
            "gender": "Male",
            "phone": "9876543211",
            "aadhaarNumber": unique_aadhaar,
        }
        # First registration -> 200 OK
        res1 = client.post("/patients/register", json=payload)
        assert res1.status_code == 200

        # Duplicate registration with same Aadhaar -> 409 Conflict
        res2 = client.post("/patients/register", json=payload)
        assert res2.status_code == 409
        assert "already registered" in res2.json()["message"]




