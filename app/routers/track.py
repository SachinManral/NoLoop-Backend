"""Public claim tracking — a patient can follow a claim by its number."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.services import claims_service

router = APIRouter(prefix="/track", tags=["track"])


@router.get("/{claim_number}")
async def track(claim_number: str, session: AsyncSession = Depends(get_session)):
    return await claims_service.track(session, claim_number)
