"""Org-admin self-service routes (HOSPITAL_ADMIN / INSURER_ADMIN)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import AuthUser, require_roles
from app.db import get_session
from app.models import Role
from app.schemas.org import CreateEmployeeBody
from app.services import org_service

_guard = require_roles(Role.HOSPITAL_ADMIN.value, Role.INSURER_ADMIN.value)

router = APIRouter(prefix="/org", tags=["org"])


@router.get("/overview")
async def overview(
    user: AuthUser = Depends(_guard), session: AsyncSession = Depends(get_session)
):
    return await org_service.overview(session, user.get("tenantId"))


@router.get("/employees")
async def employees(
    user: AuthUser = Depends(_guard), session: AsyncSession = Depends(get_session)
):
    return await org_service.list_employees(session, user.get("tenantId"))


@router.post("/employees")
async def create_employee(
    body: CreateEmployeeBody,
    user: AuthUser = Depends(_guard),
    session: AsyncSession = Depends(get_session),
):
    return await org_service.create_employee(session, user.get("tenantId"), body)
