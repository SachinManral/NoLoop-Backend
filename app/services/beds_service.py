"""Hospital bed capacity + admissions. Port of beds.service.ts."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.errors import bad_request, not_found
from app.models import (
    Admission,
    AdmissionStatus,
    Bed,
    BedStatus,
    Patient,
    Tenant,
    TenantType,
    Ward,
)
from app.models.base import utcnow
from app.schemas.beds import AdmitBody
from app.services import serializers as S


async def _hospital(session: AsyncSession, tenant_id: str | None) -> Tenant:
    if not tenant_id:
        raise bad_request("No hospital on token")
    tenant = (
        await session.execute(select(Tenant).where(Tenant.id == tenant_id))
    ).scalar_one_or_none()
    if not tenant or tenant.type != TenantType.HOSPITAL:
        raise bad_request("Not a hospital account")
    return tenant


async def overview(session: AsyncSession, tenant_id: str | None) -> dict:
    hospital = await _hospital(session, tenant_id)
    wards = (
        await session.execute(
            select(Ward)
            .where(Ward.hospital_tenant_id == hospital.id)
            .options(selectinload(Ward.beds))
            .order_by(Ward.name.asc())
        )
    ).scalars().all()

    active = (
        await session.execute(
            select(Admission)
            .where(
                Admission.hospital_tenant_id == hospital.id,
                Admission.status == AdmissionStatus.ADMITTED,
            )
            .options(selectinload(Admission.bed).selectinload(Bed.ward))
            .order_by(Admission.admitted_at.desc())
        )
    ).scalars().all()

    total_beds = sum(len(w.beds) for w in wards)
    occupied = sum(
        len([b for b in w.beds if b.status == BedStatus.OCCUPIED]) for w in wards
    )
    maintenance = sum(
        len([b for b in w.beds if b.status == BedStatus.MAINTENANCE]) for w in wards
    )
    available = total_beds - occupied - maintenance

    def ward_row(w: Ward) -> dict:
        occ = len([b for b in w.beds if b.status == BedStatus.OCCUPIED])
        maint = len([b for b in w.beds if b.status == BedStatus.MAINTENANCE])
        return {
            "id": w.id,
            "name": w.name,
            "totalBeds": len(w.beds),
            "occupied": occ,
            "available": len(w.beds) - occ - maint,
        }

    return {
        "totalBeds": total_beds,
        "available": available,
        "occupied": occupied,
        "maintenance": maintenance,
        "occupancyRate": round(occupied / total_beds * 100) if total_beds else 0,
        "wards": [ward_row(w) for w in wards],
        "patients": [
            {
                "admissionId": a.id,
                "patientName": a.patient_name,
                "patientAge": a.patient_age,
                "patientGender": a.patient_gender,
                "diagnosis": a.diagnosis,
                "procedure": a.procedure,
                "ward": a.bed.ward.name if a.bed else "—",
                "bed": a.bed.label if a.bed else "—",
                "admittedAt": a.admitted_at,
            }
            for a in active
        ],
    }


async def admit(session: AsyncSession, tenant_id: str | None, body: AdmitBody) -> dict:
    hospital = await _hospital(session, tenant_id)
    stmt = (
        select(Bed)
        .where(
            Bed.hospital_tenant_id == hospital.id,
            Bed.status == BedStatus.AVAILABLE,
        )
        .order_by(Bed.label.asc())
        .limit(1)
    )
    if body.wardId:
        stmt = stmt.where(Bed.ward_id == body.wardId)
    bed = (await session.execute(stmt)).scalar_one_or_none()
    if not bed:
        raise bad_request("No available beds" + (" in that ward" if body.wardId else ""))

    patient = None
    if body.memberId:
        patient = (
            await session.execute(select(Patient).where(Patient.member_id == body.memberId))
        ).scalar_one_or_none()

    admission = Admission(
        hospital_tenant_id=hospital.id,
        bed_id=bed.id,
        patient_id=patient.id if patient else None,
        patient_name=body.patientName,
        patient_age=body.patientAge,
        patient_gender=body.patientGender,
        diagnosis=body.diagnosis,
        procedure=body.procedure,
        status=AdmissionStatus.ADMITTED,
    )
    session.add(admission)
    bed.status = BedStatus.OCCUPIED
    await session.commit()
    return S.admission(admission)


async def discharge(session: AsyncSession, tenant_id: str | None, admission_id: str) -> dict:
    hospital = await _hospital(session, tenant_id)
    admission = (
        await session.execute(
            select(Admission).where(
                Admission.id == admission_id,
                Admission.hospital_tenant_id == hospital.id,
            )
        )
    ).scalar_one_or_none()
    if not admission:
        raise not_found("Admission not found")
    if admission.status == AdmissionStatus.DISCHARGED:
        return S.admission(admission)

    admission.status = AdmissionStatus.DISCHARGED
    admission.discharged_at = utcnow()
    if admission.bed_id:
        bed = (
            await session.execute(select(Bed).where(Bed.id == admission.bed_id))
        ).scalar_one_or_none()
        if bed:
            bed.status = BedStatus.AVAILABLE
    await session.commit()
    return S.admission(admission)
