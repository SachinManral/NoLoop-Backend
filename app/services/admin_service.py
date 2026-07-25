"""Platform-admin (god-mode) operations. Port of admin.service.ts."""

from __future__ import annotations

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.errors import bad_request, not_found
from app.core.passwords import gen_password
from app.core.security import hash_password
from app.core.slug import to_compact, to_dotted, unique_email
from app.models import (
    ActivityLog,
    Admission,
    Bed,
    Claim,
    ClaimEvent,
    Patient,
    Policy,
    Role,
    Tenant,
    TenantType,
    User,
    UserStatus,
    Ward,
)
from app.schemas.admin import (
    AdminCreateUserBody,
    CreateOrgBody,
    ResetPasswordBody,
    UpdateUserBody,
)
from app.services import serializers as S


def _admin_role_for(t: TenantType) -> Role:
    return Role.HOSPITAL_ADMIN if t == TenantType.HOSPITAL else Role.INSURER_ADMIN


def _staff_role_for(t: TenantType) -> Role:
    return Role.HOSPITAL_STAFF if t == TenantType.HOSPITAL else Role.INSURER_ADJUDICATOR


async def _count(session: AsyncSession, model, *where) -> int:
    stmt = select(func.count()).select_from(model)
    for w in where:
        stmt = stmt.where(w)
    return (await session.execute(stmt)).scalar_one()


async def _email_taken(session: AsyncSession, email: str) -> bool:
    return (await session.execute(select(User.id).where(User.email == email))).first() is not None


# ── reads ────────────────────────────────────────────────────
async def stats(session: AsyncSession) -> dict:
    return {
        "orgs": await _count(session, Tenant),
        "hospitals": await _count(session, Tenant, Tenant.type == TenantType.HOSPITAL),
        "insurers": await _count(session, Tenant, Tenant.type == TenantType.INSURER),
        "users": await _count(session, User),
        "claims": await _count(session, Claim),
        "logs": await _count(session, ActivityLog),
    }


async def list_orgs(session: AsyncSession) -> list[dict]:
    tenants = (
        await session.execute(select(Tenant).order_by(Tenant.created_at.desc()))
    ).scalars().all()
    rows = (
        await session.execute(
            select(User.tenant_id, func.count()).group_by(User.tenant_id)
        )
    ).all()
    counts = {tid: n for tid, n in rows}
    return [S.org_summary(t, counts.get(t.id, 0)) for t in tenants]


async def get_org(session: AsyncSession, org_id: str) -> dict:
    tenant = (
        await session.execute(select(Tenant).where(Tenant.id == org_id))
    ).scalar_one_or_none()
    if not tenant:
        raise not_found("Organization not found")
    members = (
        await session.execute(
            select(User).where(User.tenant_id == org_id).order_by(User.created_at.desc())
        )
    ).scalars().all()
    return S.org_detail(tenant, members)


async def list_logs(session: AsyncSession, limit: int = 100) -> list[dict]:
    take = min(max(limit, 1), 500)
    logs = (
        await session.execute(
            select(ActivityLog)
            .options(selectinload(ActivityLog.tenant), selectinload(ActivityLog.actor))
            .order_by(ActivityLog.created_at.desc())
            .limit(take)
        )
    ).scalars().all()
    return [S.log_entry(log) for log in logs]


async def list_users(session: AsyncSession) -> list[dict]:
    users = (
        await session.execute(
            select(User).options(selectinload(User.tenant)).order_by(User.created_at.desc())
        )
    ).scalars().all()
    return [S.user_roster(u) for u in users]


# ── mutations ────────────────────────────────────────────────
async def create_org(session: AsyncSession, actor_id: str, body: CreateOrgBody) -> dict:
    org_type = TenantType(body.type)
    email = await unique_email(to_dotted(body.name), lambda e: _email_taken(session, e))
    temp_password = body.password or gen_password()
    password_hash = hash_password(temp_password)

    tenant = Tenant(name=body.name, type=org_type)
    session.add(tenant)
    await session.flush()
    admin = User(
        email=email,
        name=body.adminName,
        password_hash=password_hash,
        role=_admin_role_for(org_type),
        tenant_id=tenant.id,
    )
    session.add(admin)
    session.add(
        ActivityLog(
            tenant_id=tenant.id,
            actor_id=actor_id,
            action="ORG_CREATED",
            detail=f'{body.type} "{body.name}" created by platform admin',
        )
    )
    await session.commit()
    return {
        "tenant": {"id": tenant.id, "name": tenant.name, "type": tenant.type.value},
        "credentials": {
            "email": admin.email,
            "password": temp_password,
            "role": admin.role.value,
        },
    }


async def delete_org(session: AsyncSession, org_id: str) -> dict:
    tenant = (
        await session.execute(select(Tenant).where(Tenant.id == org_id))
    ).scalar_one_or_none()
    if not tenant:
        raise not_found("Organization not found")

    user_ids = (
        await session.execute(select(User.id).where(User.tenant_id == org_id))
    ).scalars().all()

    await session.execute(
        delete(Claim).where(
            or_(Claim.hospital_tenant_id == org_id, Claim.insurer_tenant_id == org_id)
        )
    )
    await session.execute(
        update(ClaimEvent).where(ClaimEvent.actor_id.in_(user_ids)).values(actor_id=None)
    )
    await session.execute(delete(Admission).where(Admission.hospital_tenant_id == org_id))
    await session.execute(delete(Bed).where(Bed.hospital_tenant_id == org_id))
    await session.execute(delete(Ward).where(Ward.hospital_tenant_id == org_id))
    await session.execute(delete(Patient).where(Patient.insurer_tenant_id == org_id))
    await session.execute(delete(Policy).where(Policy.insurer_tenant_id == org_id))
    await session.execute(
        delete(ActivityLog).where(
            or_(ActivityLog.tenant_id == org_id, ActivityLog.actor_id.in_(user_ids))
        )
    )
    await session.execute(delete(User).where(User.tenant_id == org_id))
    await session.execute(delete(Tenant).where(Tenant.id == org_id))
    await session.commit()
    return {"deleted": True, "id": org_id, "name": tenant.name}


async def create_user(session: AsyncSession, actor_id: str, body: AdminCreateUserBody) -> dict:
    tenant = (
        await session.execute(select(Tenant).where(Tenant.id == body.tenantId))
    ).scalar_one_or_none()
    if not tenant:
        raise bad_request("Organization not found")

    role = Role(body.role) if body.role else _staff_role_for(tenant.type)
    local_base = f"{to_compact(body.name)}.{to_compact(tenant.name)}"
    email = await unique_email(local_base, lambda e: _email_taken(session, e))
    temp_password = body.password or gen_password()
    password_hash = hash_password(temp_password)

    user = User(
        email=email,
        name=body.name,
        password_hash=password_hash,
        role=role,
        tenant_id=tenant.id,
    )
    session.add(user)
    await session.flush()
    session.add(
        ActivityLog(
            tenant_id=tenant.id,
            actor_id=actor_id,
            action="EMPLOYEE_CREATED",
            detail=f"{user.name} <{user.email}> ({role.value}) created by platform admin",
        )
    )
    await session.commit()
    return {
        "user": {"id": user.id, "name": user.name, "role": user.role.value},
        "credentials": {
            "email": user.email,
            "password": temp_password,
            "role": user.role.value,
        },
    }


async def _must_exist(session: AsyncSession, user_id: str) -> User:
    user = (
        await session.execute(select(User).where(User.id == user_id))
    ).scalar_one_or_none()
    if not user:
        raise not_found("User not found")
    return user


async def update_user(session: AsyncSession, user_id: str, body: UpdateUserBody) -> dict:
    user = await _must_exist(session, user_id)
    if body.name:
        user.name = body.name
    if body.role:
        user.role = Role(body.role)
    await session.commit()
    return S.user_admin_fields(user)


async def reset_password(session: AsyncSession, user_id: str, body: ResetPasswordBody) -> dict:
    user = await _must_exist(session, user_id)
    temp_password = body.password or gen_password()
    user.password_hash = hash_password(temp_password)
    await session.commit()
    return {"credentials": {"email": user.email, "password": temp_password}}


async def set_status(session: AsyncSession, user_id: str, status: UserStatus) -> dict:
    user = await _must_exist(session, user_id)
    user.status = status
    await session.commit()
    return S.user_admin_fields(user)


async def delete_user(session: AsyncSession, user_id: str) -> dict:
    user = await _must_exist(session, user_id)
    email = user.email
    await session.execute(
        update(ClaimEvent).where(ClaimEvent.actor_id == user_id).values(actor_id=None)
    )
    await session.execute(
        update(Claim).where(Claim.submitted_by_id == user_id).values(submitted_by_id=None)
    )
    await session.execute(
        update(Claim).where(Claim.overridden_by_id == user_id).values(overridden_by_id=None)
    )
    await session.execute(
        update(ActivityLog).where(ActivityLog.actor_id == user_id).values(actor_id=None)
    )
    await session.execute(delete(User).where(User.id == user_id))
    await session.commit()
    return {"deleted": True, "id": user_id, "email": email}
