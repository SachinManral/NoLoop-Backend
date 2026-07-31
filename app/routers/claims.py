"""Claim routes: submit, extract, list, detail, override, settle, respond."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import AuthUser, require_roles
from app.db import get_session
from app.models import Role
from app.schemas.claims import OverrideClaimBody, RespondBody, SubmitClaimBody
from app.services import claims_service

router = APIRouter(prefix="/claims", tags=["claims"])

_hospital = require_roles(Role.HOSPITAL_ADMIN.value, Role.HOSPITAL_STAFF.value)
_all_roles = require_roles(
    Role.HOSPITAL_ADMIN.value,
    Role.HOSPITAL_STAFF.value,
    Role.INSURER_ADMIN.value,
    Role.INSURER_ADJUDICATOR.value,
    Role.TPA_ADMIN.value,
    Role.TPA_REVIEWER.value,
    Role.PATIENT.value,
    Role.PLATFORM_ADMIN.value,
)

_insurer = require_roles(
    Role.INSURER_ADMIN.value,
    Role.INSURER_ADJUDICATOR.value,
    Role.TPA_ADMIN.value,
    Role.TPA_REVIEWER.value,
    Role.PLATFORM_ADMIN.value,
)


@router.post("")
async def submit(
    body: SubmitClaimBody,
    user: AuthUser = Depends(_hospital),
    session: AsyncSession = Depends(get_session),
):
    return await claims_service.submit(session, user, body)


@router.post("/extract")
async def extract(
    file: UploadFile = File(...),
    _: AuthUser = Depends(_all_roles),
):
    if not file:
        raise bad_request("No file uploaded")
    content_type = file.content_type or "image/jpeg"
    allowed_types = {"image/jpeg", "image/png", "image/webp", "image/heic", "image/jpg", "application/pdf"}
    if content_type not in allowed_types and not content_type.startswith("image/"):
        raise bad_request("Invalid file type. Allowed formats: JPEG, PNG, WEBP, HEIC, PDF.")
    
    data = await file.read()
    if not data or len(data) == 0:
        raise bad_request("Uploaded file is empty.")
    if len(data) > 10 * 1024 * 1024:
        raise bad_request("File size exceeds maximum allowed limit of 10MB.")
        
    return await claims_service.extract_document(data, content_type)


@router.get("")
async def list_claims(
    status: str | None = None,
    user: AuthUser = Depends(_all_roles),
    session: AsyncSession = Depends(get_session),
):
    return await claims_service.list_claims(session, user, status)


@router.get("/{claim_id}")
async def get_claim(
    claim_id: str,
    user: AuthUser = Depends(_all_roles),
    session: AsyncSession = Depends(get_session),
):
    return await claims_service.get(session, user, claim_id)


@router.post("/{claim_id}/override")
async def override(
    claim_id: str,
    body: OverrideClaimBody,
    user: AuthUser = Depends(_insurer),
    session: AsyncSession = Depends(get_session),
):
    return await claims_service.override(session, user, claim_id, body)


@router.post("/{claim_id}/settle")
async def settle(
    claim_id: str,
    user: AuthUser = Depends(_insurer),
    session: AsyncSession = Depends(get_session),
):
    return await claims_service.settle(session, user, claim_id)


@router.post("/{claim_id}/respond")
async def respond(
    claim_id: str,
    body: RespondBody,
    user: AuthUser = Depends(_hospital),
    session: AsyncSession = Depends(get_session),
):
    return await claims_service.respond_query(session, user, claim_id, body.message or "")


@router.post("/{claim_id}/resubmit")
async def resubmit(
    claim_id: str,
    body: SubmitClaimBody,
    user: AuthUser = Depends(_hospital),
    session: AsyncSession = Depends(get_session),
):
    """Resubmit a QUERIED claim with updated data — re-enters the pipeline."""
    return await claims_service.resubmit_claim(session, user, claim_id, body)

