"""Patient Lifetime Registration & Aadhaar Lookup Service.

Every patient registered on NoLoop is issued a lifetime immutable Health ID
(ABHA-compatible format: NL-HID-XXXX-XXXX-XXXX). Patients can be instantly
located and linked across hospitals & insurers via their Aadhaar Card number.
"""

from __future__ import annotations

import hmac
import hashlib
import logging
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.core.errors import bad_request, conflict, not_found


from app.models import Patient, Policy
from app.models.base import gen_health_id

log = logging.getLogger("patient_service")

# Pepper key for HMAC-SHA256 hashing to prevent rainbow-table reverse lookups (DPDP / UIDAI section 29)
AADHAAR_PEPPER = getattr(settings, "jwt_secret", "noloop-sec-aadhaar-pepper-key-2026").encode("utf-8")

VERHOEFF_D = [
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
    [1, 2, 3, 4, 0, 6, 7, 8, 9, 5],
    [2, 3, 4, 0, 1, 7, 8, 9, 5, 6],
    [3, 4, 0, 1, 2, 8, 9, 5, 6, 7],
    [4, 0, 1, 2, 3, 9, 5, 6, 7, 8],
    [5, 9, 8, 7, 6, 0, 4, 3, 2, 1],
    [6, 5, 9, 8, 7, 1, 0, 4, 3, 2],
    [7, 6, 5, 9, 8, 2, 1, 0, 4, 3],
    [8, 7, 6, 5, 9, 3, 2, 1, 0, 4],
    [9, 8, 7, 6, 5, 4, 3, 2, 1, 0],
]

VERHOEFF_P = [
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
    [1, 5, 7, 6, 2, 8, 3, 0, 9, 4],
    [5, 8, 0, 3, 7, 9, 6, 1, 4, 2],
    [8, 9, 1, 6, 0, 4, 3, 5, 2, 7],
    [9, 4, 5, 3, 1, 2, 6, 8, 7, 0],
    [4, 2, 8, 6, 5, 7, 3, 9, 0, 1],
    [2, 7, 9, 3, 8, 0, 6, 4, 1, 5],
    [7, 0, 4, 6, 9, 1, 3, 2, 5, 8],
]


def validate_verhoeff(number: str) -> bool:
    """Validate 12-digit Aadhaar number using UIDAI Verhoeff checksum algorithm."""
    c = 0
    for i, digit in enumerate(reversed(number)):
        c = VERHOEFF_D[c][VERHOEFF_P[i % 8][int(digit)]]
    return c == 0


def hash_aadhaar(aadhaar_number: str) -> str:
    """Compute peppered HMAC-SHA256 digest for DPDP Act & UIDAI Section 29 compliance.

    Raw Aadhaar numbers are never stored in cleartext. HMAC with system pepper prevents
    rainbow table or dictionary attacks against the 12-digit space.
    """
    clean = "".join(c for c in aadhaar_number if c.isdigit())
    if len(clean) != 12:
        raise bad_request("Aadhaar Card number must be exactly 12 digits")

    if not validate_verhoeff(clean):
        raise bad_request("Invalid Aadhaar Card number (failed Verhoeff checksum check)")

    return hmac.new(AADHAAR_PEPPER, clean.encode("utf-8"), hashlib.sha256).hexdigest()


def get_aadhaar_last4(aadhaar_number: str) -> str:
    """Extract masked display string (UIDAI mandate: XXXX-XXXX-1234)."""
    clean = "".join(c for c in aadhaar_number if c.isdigit())
    if len(clean) != 12:
        raise bad_request("Aadhaar Card number must be exactly 12 digits")
    return f"XXXX-XXXX-{clean[-4:]}"



async def register_patient(
    session: AsyncSession,
    insurer_tenant_id: str,
    name: str,
    age: int,
    gender: str,
    aadhaar_number: str,
    phone: str | None = None,
    policy_id: str | None = None,
    member_id: str | None = None,
) -> Patient:
    if not aadhaar_number or len(aadhaar_number.strip()) == 0:
        raise bad_request("Aadhaar Card number is required to issue a Lifetime Health ID")

    from app.models import Tenant, TenantType
    insurer = await session.get(Tenant, insurer_tenant_id)
    if not insurer:
        insurer = Tenant(
            id=insurer_tenant_id,
            name="Star Health Insurance",
            type=TenantType.INSURER,
        )
        session.add(insurer)
        await session.commit()

    aadhaar_hash = hash_aadhaar(aadhaar_number)
    aadhaar_last4 = get_aadhaar_last4(aadhaar_number)

    # Enforce strict uniqueness: Only one patient record per Aadhaar Card
    existing = (
        await session.execute(
            select(Patient)
            .where(Patient.aadhaar_hash == aadhaar_hash)
            .options(selectinload(Patient.policy), selectinload(Patient.insurer))
        )
    ).scalar_one_or_none()

    if existing:
        log.warning(f"Registration conflict: Aadhaar Card already registered (Health ID: {existing.health_id})")
        raise conflict("An account with this Aadhaar Card number is already registered")


    # Generate lifetime Health ID derived from Aadhaar
    health_id = gen_health_id(aadhaar_number)


    # Generate fallback memberId if not provided
    if not member_id:
        clean_hid = health_id.replace("NL-HID-", "").replace("-", "")
        member_id = f"MEM-{clean_hid}"

    patient = Patient(
        insurer_tenant_id=insurer_tenant_id,
        policy_id=policy_id,
        member_id=member_id,
        health_id=health_id,
        aadhaar_hash=aadhaar_hash,
        aadhaar_last4=aadhaar_last4,
        name=name,
        age=age,
        gender=gender,
        phone=phone,
    )
    session.add(patient)
    await session.commit()
    await session.refresh(patient)
    return patient


async def lookup_by_aadhaar(session: AsyncSession, aadhaar_number: str) -> Patient:
    """Instantly locate a patient using their 12-digit Aadhaar Card number."""
    a_hash = hash_aadhaar(aadhaar_number)
    patient = (
        await session.execute(
            select(Patient)
            .where(Patient.aadhaar_hash == a_hash)
            .options(selectinload(Patient.policy), selectinload(Patient.insurer), selectinload(Patient.claims))
        )
    ).scalar_one_or_none()

    if not patient:
        raise not_found("No registered patient record found for this Aadhaar Card")
    return patient


async def lookup_by_health_id(session: AsyncSession, health_id: str) -> Patient:
    """Instantly locate a patient using their lifetime Health ID (NL-HID-XXXX-XXXX-XXXX)."""
    patient = (
        await session.execute(
            select(Patient)
            .where(Patient.health_id == health_id)
            .options(selectinload(Patient.policy), selectinload(Patient.insurer), selectinload(Patient.claims))
        )
    ).scalar_one_or_none()

    if not patient:
        raise not_found("No patient found for this lifetime Health ID")
    return patient
