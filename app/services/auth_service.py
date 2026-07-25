"""Auth: org signup + login. Port of backend/src/auth/auth.service.ts."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import unauthorized
from app.core.security import hash_password, sign_token, verify_password
from app.core.slug import to_dotted, unique_email
from app.models import ActivityLog, Role, Tenant, TenantType, User, UserStatus
from app.schemas.auth import LoginBody, SignupBody
from app.services.serializers import user_account


def _admin_role_for(t: TenantType) -> Role:
    return Role.HOSPITAL_ADMIN if t == TenantType.HOSPITAL else Role.INSURER_ADMIN


async def _email_taken(session: AsyncSession, email: str) -> bool:
    res = await session.execute(select(User.id).where(User.email == email))
    return res.first() is not None


def _issue(user: User) -> dict:
    token = sign_token(user.id, user.role.value, user.tenant_id)
    return {"token": token, "user": user_account(user)}


async def signup(session: AsyncSession, body: SignupBody) -> dict:
    org_type = TenantType(body.orgType)
    email = await unique_email(
        to_dotted(body.orgName), lambda e: _email_taken(session, e)
    )
    password_hash = hash_password(body.password)

    tenant = Tenant(name=body.orgName, type=org_type)
    session.add(tenant)
    await session.flush()  # populate tenant.id

    user = User(
        email=email,
        name=body.adminName,
        password_hash=password_hash,
        role=_admin_role_for(org_type),
        tenant_id=tenant.id,
    )
    session.add(user)
    await session.flush()

    session.add(
        ActivityLog(
            tenant_id=tenant.id,
            actor_id=user.id,
            action="ORG_CREATED",
            detail=f'{body.orgType} "{body.orgName}" created',
        )
    )
    await session.commit()
    return _issue(user)


async def login(session: AsyncSession, body: LoginBody) -> dict:
    res = await session.execute(select(User).where(User.email == body.email))
    user = res.scalar_one_or_none()
    if not user:
        raise unauthorized("Invalid credentials")
    if not verify_password(body.password, user.password_hash):
        raise unauthorized("Invalid credentials")
    if user.status == UserStatus.REVOKED:
        raise unauthorized("Account access has been revoked")

    session.add(
        ActivityLog(tenant_id=user.tenant_id, actor_id=user.id, action="LOGIN")
    )
    await session.commit()
    return _issue(user)
