"""Analytics dashboard (all org + platform roles)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import AuthUser, require_roles
from app.db import get_session
from app.models import Role
from app.services import metrics_service

_guard = require_roles(
    Role.HOSPITAL_ADMIN.value,
    Role.HOSPITAL_STAFF.value,
    Role.INSURER_ADMIN.value,
    Role.INSURER_ADJUDICATOR.value,
    Role.PLATFORM_ADMIN.value,
)

router = APIRouter(prefix="/metrics", tags=["metrics"])


@router.get("")
async def summary(
    user: AuthUser = Depends(_guard), session: AsyncSession = Depends(get_session)
):
    return await metrics_service.summary(session, user)
