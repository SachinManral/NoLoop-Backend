"""Workflow routes: transitions, timeline, and claim advancement.

Sprint 2: exposes the orchestrator state machine via REST endpoints.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import AuthUser, require_roles
from app.db import get_session
from app.models import Role
from app.services import claims_service

router = APIRouter(prefix="/workflow", tags=["workflow"])

_all_roles = require_roles(
    Role.HOSPITAL_ADMIN.value,
    Role.HOSPITAL_STAFF.value,
    Role.INSURER_ADMIN.value,
    Role.INSURER_ADJUDICATOR.value,
    Role.TPA_ADMIN.value,
    Role.TPA_REVIEWER.value,
    Role.PLATFORM_ADMIN.value,
)


@router.get("/{claim_id}/transitions")
async def get_transitions(
    claim_id: str,
    user: AuthUser = Depends(_all_roles),
    session: AsyncSession = Depends(get_session),
):
    """Return valid next states for the given claim's current status."""
    return await claims_service.get_valid_transitions(session, user, claim_id)


@router.get("/{claim_id}/timeline")
async def get_timeline(
    claim_id: str,
    user: AuthUser = Depends(_all_roles),
    session: AsyncSession = Depends(get_session),
):
    """Return the full event timeline with stage durations."""
    return await claims_service.get_timeline(session, user, claim_id)
