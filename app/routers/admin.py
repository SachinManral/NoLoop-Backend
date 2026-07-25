"""Platform-admin routes — all require a logged-in PLATFORM_ADMIN."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import AuthUser, get_current_user, require_roles
from app.db import get_session
from app.models import Role, UserStatus
from app.schemas.admin import (
    AdminCreateUserBody,
    CreateOrgBody,
    ResetPasswordBody,
    UpdateUserBody,
)
from app.services import admin_service

router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    dependencies=[Depends(require_roles(Role.PLATFORM_ADMIN.value))],
)


# ── reads ──
@router.get("/stats")
async def stats(session: AsyncSession = Depends(get_session)):
    return await admin_service.stats(session)


@router.get("/orgs")
async def orgs(session: AsyncSession = Depends(get_session)):
    return await admin_service.list_orgs(session)


@router.get("/orgs/{org_id}")
async def org(org_id: str, session: AsyncSession = Depends(get_session)):
    return await admin_service.get_org(session, org_id)


@router.get("/users")
async def users(session: AsyncSession = Depends(get_session)):
    return await admin_service.list_users(session)


@router.get("/logs")
async def logs(limit: int = 100, session: AsyncSession = Depends(get_session)):
    return await admin_service.list_logs(session, limit)


# ── org mutations ──
@router.post("/orgs")
async def create_org(
    body: CreateOrgBody,
    user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    return await admin_service.create_org(session, user["sub"], body)


@router.delete("/orgs/{org_id}")
async def delete_org(org_id: str, session: AsyncSession = Depends(get_session)):
    return await admin_service.delete_org(session, org_id)


# ── user mutations ──
@router.post("/users")
async def create_user(
    body: AdminCreateUserBody,
    user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    return await admin_service.create_user(session, user["sub"], body)


@router.patch("/users/{user_id}")
async def update_user(
    user_id: str, body: UpdateUserBody, session: AsyncSession = Depends(get_session)
):
    return await admin_service.update_user(session, user_id, body)


@router.post("/users/{user_id}/reset-password")
async def reset_password(
    user_id: str, body: ResetPasswordBody, session: AsyncSession = Depends(get_session)
):
    return await admin_service.reset_password(session, user_id, body)


@router.post("/users/{user_id}/revoke")
async def revoke(user_id: str, session: AsyncSession = Depends(get_session)):
    return await admin_service.set_status(session, user_id, UserStatus.REVOKED)


@router.post("/users/{user_id}/restore")
async def restore(user_id: str, session: AsyncSession = Depends(get_session)):
    return await admin_service.set_status(session, user_id, UserStatus.ACTIVE)


@router.delete("/users/{user_id}")
async def delete_user(user_id: str, session: AsyncSession = Depends(get_session)):
    return await admin_service.delete_user(session, user_id)
