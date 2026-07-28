"""FastAPI Router for Patient Registration & Lifetime Health ID / Aadhaar Lookup."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.schemas.patients import RegisterPatientBody
from app.services import patient_service
from app.services import serializers as S

router = APIRouter(prefix="/patients", tags=["Patients"])


@router.post("/register")
async def register_patient(
    body: RegisterPatientBody,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Register a new patient across any portal.

    Generates a fixed, lifetime-immutable Health ID (NL-HID-XXXX-XXXX-XXXX)
    and binds the patient's Aadhaar Card hash for instant retrieval.
    """
    patient = await patient_service.register_patient(
        session=session,
        insurer_tenant_id=body.insurerTenantId,
        name=body.name,
        age=body.age,
        gender=body.gender,
        phone=body.phone,
        aadhaar_number=body.aadhaarNumber,
        policy_id=body.policyId,
        member_id=body.memberId,
    )
    return S.patient_with_counts(patient, 0)


@router.get("/lookup-by-aadhaar")
async def lookup_by_aadhaar(
    aadhaarNumber: str = Query(..., min_length=12, max_length=12, description="12-digit Aadhaar Card number"),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Instantly locate a patient's lifetime record using their 12-digit Aadhaar Card number."""
    patient = await patient_service.lookup_by_aadhaar(session, aadhaarNumber)
    claims_count = len(patient.claims) if "claims" in patient.__dict__ and patient.claims else 0
    return S.patient_with_counts(patient, claims_count)


@router.get("/by-health-id/{health_id}")
async def lookup_by_health_id(
    health_id: str,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Retrieve a patient's unified record using their lifetime Health ID (NL-HID-XXXX-XXXX-XXXX)."""
    patient = await patient_service.lookup_by_health_id(session, health_id)
    claims_count = len(patient.claims) if "claims" in patient.__dict__ and patient.claims else 0
    return S.patient_with_counts(patient, claims_count)

