"""Catalog reads (insurers, policies, patients). Port of catalog.service.ts."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.errors import bad_request
from app.models import Claim, Patient, Policy, Tenant, TenantType
from app.services import serializers as S


async def insurers(session: AsyncSession) -> list[dict]:
    rows = (
        await session.execute(
            select(Tenant)
            .where(Tenant.type == TenantType.INSURER)
            .options(selectinload(Tenant.policies))
            .order_by(Tenant.name.asc())
        )
    ).scalars().all()

    result = []
    for ins in rows:
        # Primary policy = earliest by createdAt (Prisma take:1, asc).
        policies = sorted(ins.policies, key=lambda p: p.created_at)
        p = policies[0] if policies else None
        result.append(
            {
                "id": ins.id,
                "name": ins.name,
                "policy": (
                    {
                        "name": p.name,
                        "planCode": p.plan_code,
                        "sumInsuredPaise": p.sum_insured_paise,
                        "roomRentCapPerDayPaise": p.room_rent_cap_per_day_paise,
                        "copayPct": p.copay_pct,
                        "coveredProcedures": list(p.covered_procedures or []),
                        "exclusions": list(p.exclusions or []),
                    }
                    if p
                    else None
                ),
            }
        )
    return result


async def policies(session: AsyncSession, tenant_id: str | None) -> list[dict]:
    if not tenant_id:
        raise bad_request("No insurer on token")
    rows = (
        await session.execute(
            select(Policy)
            .where(Policy.insurer_tenant_id == tenant_id)
            .order_by(Policy.created_at.asc())
        )
    ).scalars().all()

    out = []
    for p in rows:
        patients = (
            await session.execute(
                select(func.count()).select_from(Patient).where(Patient.policy_id == p.id)
            )
        ).scalar_one()
        claims = (
            await session.execute(
                select(func.count()).select_from(Claim).where(Claim.policy_id == p.id)
            )
        ).scalar_one()
        out.append(S.policy_with_counts(p, patients, claims))
    return out


async def patients(session: AsyncSession, tenant_id: str | None) -> list[dict]:
    if not tenant_id:
        raise bad_request("No insurer on token")
    rows = (
        await session.execute(
            select(Patient)
            .where(Patient.insurer_tenant_id == tenant_id)
            .options(selectinload(Patient.policy))
            .order_by(Patient.created_at.desc())
        )
    ).scalars().all()

    out = []
    for p in rows:
        claims = (
            await session.execute(
                select(func.count()).select_from(Claim).where(Claim.patient_id == p.id)
            )
        ).scalar_one()
        out.append(S.patient_with_counts(p, claims))
    return out
