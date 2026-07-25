"""Hospital bed capacity + admissions (HOSPITAL_ADMIN / HOSPITAL_STAFF)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import AuthUser, require_roles
from app.db import get_session
from app.models import Role
from app.schemas.beds import AdmitBody
from app.services import beds_service

_guard = require_roles(Role.HOSPITAL_ADMIN.value, Role.HOSPITAL_STAFF.value)

router = APIRouter(prefix="/beds", tags=["beds"])


@router.get("/overview")
async def overview(
    user: AuthUser = Depends(_guard), session: AsyncSession = Depends(get_session)
):
    return await beds_service.overview(session, user.get("tenantId"))


@router.post("/admit")
async def admit(
    body: AdmitBody,
    user: AuthUser = Depends(_guard),
    session: AsyncSession = Depends(get_session),
):
    return await beds_service.admit(session, user.get("tenantId"), body)


@router.post("/discharge/{admission_id}")
async def discharge(
    admission_id: str,
    user: AuthUser = Depends(_guard),
    session: AsyncSession = Depends(get_session),
):
    return await beds_service.discharge(session, user.get("tenantId"), admission_id)
