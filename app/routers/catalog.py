"""Catalog reads — insurers (for the claim form) and an insurer's own data."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import AuthUser, require_roles
from app.db import get_session
from app.models import Role
from app.services import catalog_service

router = APIRouter(tags=["catalog"])

_insurer_guard = require_roles(Role.INSURER_ADMIN.value, Role.INSURER_ADJUDICATOR.value)


@router.get("/catalog/insurers")
async def insurers(
    _: AuthUser = Depends(
        require_roles(
            Role.HOSPITAL_ADMIN.value,
            Role.HOSPITAL_STAFF.value,
            Role.PLATFORM_ADMIN.value,
            Role.INSURER_ADMIN.value,
            Role.INSURER_ADJUDICATOR.value,
        )
    ),
    session: AsyncSession = Depends(get_session),
):
    return await catalog_service.insurers(session)


@router.get("/insurer/policies")
async def policies(
    user: AuthUser = Depends(_insurer_guard),
    session: AsyncSession = Depends(get_session),
):
    return await catalog_service.policies(session, user.get("tenantId"))


@router.get("/insurer/patients")
async def patients(
    user: AuthUser = Depends(_insurer_guard),
    session: AsyncSession = Depends(get_session),
):
    return await catalog_service.patients(session, user.get("tenantId"))
