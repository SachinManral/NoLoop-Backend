"""Org-admin self-service. Port of org.service.ts."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import bad_request, not_found
from app.core.security import hash_password
from app.core.slug import to_compact, unique_email
from app.models import ActivityLog, Role, Tenant, TenantType, User
from app.schemas.org import CreateEmployeeBody
from app.services import serializers as S


def _staff_role_for(t: TenantType) -> Role:
    return Role.HOSPITAL_STAFF if t == TenantType.HOSPITAL else Role.INSURER_ADJUDICATOR


async def _tenant_of(session: AsyncSession, tenant_id: str | None) -> Tenant:
    if not tenant_id:
        raise bad_request("No organization on token")
    tenant = (
        await session.execute(select(Tenant).where(Tenant.id == tenant_id))
    ).scalar_one_or_none()
    if not tenant:
        raise not_found("Organization not found")
    return tenant


async def _email_taken(session: AsyncSession, email: str) -> bool:
    return (await session.execute(select(User.id).where(User.email == email))).first() is not None


async def overview(session: AsyncSession, tenant_id: str | None) -> dict:
    tenant = await _tenant_of(session, tenant_id)
    employee_count = (
        await session.execute(
            select(func.count()).select_from(User).where(User.tenant_id == tenant.id)
        )
    ).scalar_one()
    admin_email = (
        await session.execute(
            select(User.email)
            .where(
                User.tenant_id == tenant.id,
                User.role.in_([Role.HOSPITAL_ADMIN, Role.INSURER_ADMIN]),
            )
            .order_by(User.created_at.asc())
            .limit(1)
        )
    ).scalar_one_or_none()
    return {
        "id": tenant.id,
        "name": tenant.name,
        "type": tenant.type.value,
        "createdAt": tenant.created_at,
        "orgEmail": admin_email,
        "employeeCount": employee_count,
    }


async def list_employees(session: AsyncSession, tenant_id: str | None) -> list[dict]:
    tenant = await _tenant_of(session, tenant_id)
    users = (
        await session.execute(
            select(User).where(User.tenant_id == tenant.id).order_by(User.created_at.asc())
        )
    ).scalars().all()
    return [S.employee(u) for u in users]


async def create_employee(
    session: AsyncSession, tenant_id: str | None, body: CreateEmployeeBody
) -> dict:
    tenant = await _tenant_of(session, tenant_id)
    local_base = f"{to_compact(body.name)}.{to_compact(tenant.name)}"
    email = await unique_email(local_base, lambda e: _email_taken(session, e))
    user = User(
        email=email,
        name=body.name,
        password_hash=hash_password(body.password),
        role=_staff_role_for(tenant.type),
        tenant_id=tenant.id,
    )
    session.add(user)
    await session.flush()
    session.add(
        ActivityLog(
            tenant_id=tenant.id,
            action="EMPLOYEE_CREATED",
            detail=f"{user.name} <{user.email}>",
        )
    )
    await session.commit()
    return S.employee(user)
