"""Claims: submit + orchestrated pipeline, listing, override, settle, tracking.

Sprint 2: refactored to use the Workflow Orchestrator for state transitions.
The submit() function now creates the claim with SUBMITTED status and delegates
to orchestrator.advance() for multi-stage processing. Override and settle go
through transition guards.

Port of backend/src/claims/claims.service.ts. All money is paise.
"""

from __future__ import annotations

import base64
import random
import time
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.deps import AuthUser
from app.core.errors import bad_request, forbidden, not_found
from app.core.money import inr, js_round
from app.models import (
    Claim,
    ClaimEvent,
    ClaimEventType,
    ClaimStatus,
    ClaimType,
    Decision,
    FraudFlag,
    FraudSeverity,
    Patient,
    Policy,
    Role,
    Tenant,
    TenantType,
    Verdict,
)
from app.models.base import utcnow
from app.schemas.ai import AiAdmission, AiBill, AiLineItem, AiPolicy, ClaimPacket
from app.schemas.claims import OverrideClaimBody, SubmitClaimBody
from app.services import serializers as S
from app.services.ai_client import ai_client
from app.services import orchestrator

_DAY_SECONDS = 86_400


# ── helpers ──────────────────────────────────────────────────
def _verdict_to_status(v: Verdict) -> ClaimStatus:
    if v == Verdict.APPROVE:
        return ClaimStatus.APPROVED
    if v == Verdict.DENY:
        return ClaimStatus.DENIED
    return ClaimStatus.QUERIED


def _severity(s: str) -> FraudSeverity:
    if s == "HIGH":
        return FraudSeverity.HIGH
    if s == "LOW":
        return FraudSeverity.LOW
    return FraudSeverity.MEDIUM


def _scope_where(user: AuthUser):
    """Restrict a claim query to what this user may see (None = no filter)."""
    role = user.get("role")
    tenant_id = user.get("tenantId")
    if role == Role.PLATFORM_ADMIN.value:
        return None
    if role in (Role.HOSPITAL_ADMIN.value, Role.HOSPITAL_STAFF.value):
        return Claim.hospital_tenant_id == (tenant_id or "__none__")
    if role in (
        Role.INSURER_ADMIN.value,
        Role.INSURER_ADJUDICATOR.value,
        Role.TPA_ADMIN.value,
        Role.TPA_REVIEWER.value,
    ):
        return Claim.insurer_tenant_id == (tenant_id or "__none__")
    return Claim.id == "__none__"


async def _new_claim_number(session: AsyncSession) -> str:
    for _ in range(8):
        n = random.randint(100000, 999998)
        candidate = f"CLM-{n}"
        taken = (
            await session.execute(select(Claim.id).where(Claim.claim_number == candidate))
        ).first()
        if not taken:
            return candidate
    return f"CLM-{int(time.time() * 1000)}"


_DETAIL_LOAD = (
    selectinload(Claim.hospital),
    selectinload(Claim.insurer),
    selectinload(Claim.policy),
    selectinload(Claim.patient),
    selectinload(Claim.fraud_flags),
    selectinload(Claim.events),
    selectinload(Claim.decisions),
    selectinload(Claim.overridden_by),
)


async def _load_detail(session: AsyncSession, claim_id: str, user: AuthUser) -> Claim:
    stmt = select(Claim).where(Claim.id == claim_id).options(*_DETAIL_LOAD)
    where = _scope_where(user)
    if where is not None:
        stmt = stmt.where(where)
    claim = (await session.execute(stmt)).scalar_one_or_none()
    if not claim:
        raise not_found("Claim not found")
    return claim


async def get(session: AsyncSession, user: AuthUser, claim_id: str) -> dict:
    return S.claim_detail(await _load_detail(session, claim_id, user))


def _build_packet(
    claim_number: str,
    claim_type: str,
    hospital_name: str,
    insurer_name: str,
    policy: Policy,
    body: SubmitClaimBody,
    los: int,
    billed: int,
) -> ClaimPacket:
    """Build the AI ClaimPacket from submission data."""
    return ClaimPacket(
        ref=claim_number,
        type=claim_type,
        hospital=hospital_name,
        insurer=insurer_name,
        policy=AiPolicy(
            policyNo=policy.plan_code,
            sumInsuredPaise=policy.sum_insured_paise,
            roomRentCapPerDayPaise=policy.room_rent_cap_per_day_paise,
            copayPct=policy.copay_pct,
            coveredProcedures=list(policy.covered_procedures or []),
            exclusions=list(policy.exclusions or []),
        ),
        admission=AiAdmission(
            admittedAt=body.admittedAt[:10],
            dischargedAt=body.dischargedAt[:10],
            lengthOfStayDays=los,
            procedure=body.procedure,
            diagnosis=body.diagnosis,
        ),
        bill=AiBill(
            lineItems=[AiLineItem(desc=li.desc, amountPaise=li.amountPaise) for li in body.lineItems],
            totalPaise=billed,
        ),
        dischargeSummary=(
            f"Patient {body.patientName} ({body.patientAge}y) admitted for "
            f"{body.procedure}; {los} day(s); billed ₹{inr(billed)}."
        ),
    )


# ── submit + orchestrated pipeline ───────────────────────────
async def submit(session: AsyncSession, user: AuthUser, body: SubmitClaimBody) -> dict:
    tenant_id = user.get("tenantId")
    if not tenant_id:
        raise bad_request("No hospital on token")
    hospital = (
        await session.execute(select(Tenant).where(Tenant.id == tenant_id))
    ).scalar_one_or_none()
    if not hospital or hospital.type != TenantType.HOSPITAL:
        raise forbidden("Only hospitals can submit claims")

    insurer = (
        await session.execute(select(Tenant).where(Tenant.id == body.insurerTenantId))
    ).scalar_one_or_none()
    if not insurer or insurer.type != TenantType.INSURER:
        raise bad_request("Target insurer not found")

    patient = None
    if body.memberId:
        patient = (
            await session.execute(
                select(Patient)
                .where(Patient.member_id == body.memberId)
                .options(selectinload(Patient.policy))
            )
        ).scalar_one_or_none()
        if patient and patient.insurer_tenant_id != insurer.id:
            patient = None

    policy: Policy | None = patient.policy if patient else None
    if policy is None:
        policy = (
            await session.execute(
                select(Policy)
                .where(Policy.insurer_tenant_id == insurer.id)
                .order_by(Policy.created_at.asc())
                .limit(1)
            )
        ).scalar_one_or_none()
    if not policy:
        raise bad_request("This insurer has no policy configured yet")

    billed = (
        body.totalPaise
        if body.totalPaise is not None
        else sum(li.amountPaise for li in body.lineItems)
    )
    admitted_at = _parse_dt(body.admittedAt)
    discharged_at = _parse_dt(body.dischargedAt)
    los = max(
        1, js_round((discharged_at - admitted_at).total_seconds() / _DAY_SECONDS)
    )

    claim_number = await _new_claim_number(session)
    submitted_at = utcnow()
    line_items = [li.model_dump() for li in body.lineItems]

    # Create claim with SUBMITTED status (Sprint 2: not PROCESSING)
    claim = Claim(
        claim_number=claim_number,
        type=ClaimType(body.type) if body.type else ClaimType.CASHLESS,
        hospital_tenant_id=hospital.id,
        insurer_tenant_id=insurer.id,
        policy_id=policy.id,
        patient_id=patient.id if patient else None,
        admission_id=body.admissionId,
        patient_name=body.patientName,
        patient_age=body.patientAge,
        patient_gender=body.patientGender,
        diagnosis=body.diagnosis,
        procedure=body.procedure,
        admitted_at=admitted_at,
        discharged_at=discharged_at,
        length_of_stay_days=los,
        sum_insured_paise=policy.sum_insured_paise,
        billed_paise=billed,
        line_items=line_items,
        status=ClaimStatus.SUBMITTED,
        submitted_by_id=user.get("sub"),
        submitted_at=submitted_at,
    )
    session.add(claim)
    await session.flush()

    # Record submission event
    session.add(
        ClaimEvent(
            claim_id=claim.id,
            type=ClaimEventType.SUBMITTED,
            message=(
                f"Claim {claim_number} submitted by {hospital.name} to {insurer.name}."
            ),
            actor_id=user.get("sub"),
        )
    )
    # Persist claim + SUBMITTED event before entering the pipeline, so a
    # failed/timed-out pipeline still leaves a visible, auditable record.
    await session.commit()

    # Build the AI packet
    packet = _build_packet(
        claim_number=claim_number,
        claim_type=claim.type.value,
        hospital_name=hospital.name,
        insurer_name=insurer.name,
        policy=policy,
        body=body,
        los=los,
        billed=billed,
    )

    # Sprint 2: delegate to the orchestrator for multi-stage processing
    await orchestrator.advance(session, claim, packet, user)

    return await get(session, user, claim.id)


async def extract_document(file_bytes: bytes | None, mimetype: str | None) -> dict:
    if not file_bytes:
        raise bad_request("No file uploaded")
    encoded = base64.b64encode(file_bytes).decode("ascii")
    return await ai_client.extract_document(encoded, mimetype or "image/jpeg")


# ── listing + detail ─────────────────────────────────────────
async def list_claims(session: AsyncSession, user: AuthUser, status: str | None) -> list[dict]:
    stmt = (
        select(Claim)
        .options(
            selectinload(Claim.hospital),
            selectinload(Claim.insurer),
            selectinload(Claim.fraud_flags),
        )
        .order_by(Claim.submitted_at.desc())
        .limit(200)
    )
    where = _scope_where(user)
    if where is not None:
        stmt = stmt.where(where)
    if status:
        stmt = stmt.where(Claim.status == ClaimStatus(status))
    claims = (await session.execute(stmt)).scalars().all()
    return [S.claim_summary(c, len(c.fraud_flags)) for c in claims]


async def track(session: AsyncSession, claim_number: str) -> dict:
    claim = (
        await session.execute(
            select(Claim)
            .where(Claim.claim_number == claim_number)
            .options(
                selectinload(Claim.hospital),
                selectinload(Claim.insurer),
                selectinload(Claim.events),
                selectinload(Claim.fraud_flags),
            )
        )
    ).scalar_one_or_none()
    if not claim:
        raise not_found("No claim with that number")
    return S.claim_track(claim, len(claim.fraud_flags))


# ── insurer override / settle ────────────────────────────────
async def override(
    session: AsyncSession, user: AuthUser, claim_id: str, body: OverrideClaimBody
) -> dict:
    claim = await _find_scoped(session, user, claim_id)

    # Sprint 2: guard the transition through the orchestrator
    if body.verdict == "APPROVE":
        target_status = ClaimStatus.SETTLED if body.settle else ClaimStatus.APPROVED
    elif body.verdict == "DENY":
        target_status = ClaimStatus.DENIED
    else:
        target_status = ClaimStatus.QUERIED

    # Validate the transition is legal
    orchestrator.guard_transition(claim.status, target_status)

    if body.verdict == "APPROVE":
        approved = (
            body.approvedAmountPaise
            if body.approvedAmountPaise is not None
            else (
                claim.approved_amount_paise
                if claim.approved_amount_paise is not None
                else claim.billed_paise
            )
        )
    elif body.verdict == "DENY":
        approved = 0
    else:
        approved = claim.approved_amount_paise

    now = utcnow()
    claim.status = target_status
    claim.verdict = Verdict(body.verdict)
    claim.approved_amount_paise = approved
    claim.overridden_by_id = user.get("sub")
    claim.override_note = body.note
    claim.overridden_at = now
    if body.settle:
        claim.settled_at = now

    amount_suffix = (
        f" (₹{inr(approved)})" if body.verdict == "APPROVE" and approved is not None else ""
    )
    session.add(
        ClaimEvent(
            claim_id=claim_id,
            type=ClaimEventType.OVERRIDDEN,
            message=f"Adjudicator override → {body.verdict}{amount_suffix}. {body.note}",
            actor_id=user.get("sub"),
        )
    )
    if body.settle:
        session.add(
            ClaimEvent(
                claim_id=claim_id,
                type=ClaimEventType.SETTLED,
                message="Claim settled — payout released.",
                actor_id=user.get("sub"),
            )
        )
    await session.commit()
    return await get(session, user, claim_id)


async def settle(session: AsyncSession, user: AuthUser, claim_id: str) -> dict:
    claim = await _find_scoped(session, user, claim_id)

    # Sprint 2: guard the transition
    orchestrator.guard_transition(claim.status, ClaimStatus.SETTLED)

    claim.status = ClaimStatus.SETTLED
    claim.settled_at = utcnow()
    session.add(
        ClaimEvent(
            claim_id=claim_id,
            type=ClaimEventType.SETTLED,
            message="Claim settled — payout released.",
            actor_id=user.get("sub"),
        )
    )
    await session.commit()
    return await get(session, user, claim_id)


async def respond_query(
    session: AsyncSession, user: AuthUser, claim_id: str, message: str
) -> dict:
    """Hospital responds to a query — transitions QUERIED → UNDER_REVIEW."""
    claim = await _find_scoped(session, user, claim_id)

    # Sprint 2: guard the transition (QUERIED → SUBMITTED for resubmit,
    # or just add a note if they're just responding without resubmit)
    if claim.status == ClaimStatus.QUERIED:
        claim.status = ClaimStatus.UNDER_REVIEW
    session.add(
        ClaimEvent(
            claim_id=claim_id,
            type=ClaimEventType.NOTE,
            message=f"Hospital response: {message}",
            actor_id=user.get("sub"),
        )
    )
    await session.commit()
    return await get(session, user, claim_id)


async def resubmit_claim(
    session: AsyncSession, user: AuthUser, claim_id: str, body: SubmitClaimBody
) -> dict:
    """Hospital resubmits a QUERIED claim — re-enters the full pipeline.

    Sprint 2: uses the orchestrator's resubmit flow.
    """
    claim = await _find_scoped(session, user, claim_id)

    if claim.status not in (ClaimStatus.QUERIED, ClaimStatus.RETURNED_TO_HOSPITAL):
        raise bad_request(
            f"Can only resubmit claims in QUERIED or RETURNED_TO_HOSPITAL status, "
            f"current status: {claim.status.value}"
        )

    # Look up related entities for packet building
    hospital = (
        await session.execute(select(Tenant).where(Tenant.id == claim.hospital_tenant_id))
    ).scalar_one()
    insurer = (
        await session.execute(select(Tenant).where(Tenant.id == claim.insurer_tenant_id))
    ).scalar_one()
    policy = (
        await session.execute(select(Policy).where(Policy.id == claim.policy_id))
    ).scalar_one_or_none()

    if not policy:
        raise bad_request("Policy not found for this claim")

    billed = (
        body.totalPaise
        if body.totalPaise is not None
        else sum(li.amountPaise for li in body.lineItems)
    )
    admitted_at = _parse_dt(body.admittedAt)
    discharged_at = _parse_dt(body.dischargedAt)
    los = max(
        1, js_round((discharged_at - admitted_at).total_seconds() / _DAY_SECONDS)
    )

    # Update claim fields with resubmitted data
    claim.patient_name = body.patientName
    claim.patient_age = body.patientAge
    claim.patient_gender = body.patientGender
    claim.diagnosis = body.diagnosis
    claim.procedure = body.procedure
    claim.admitted_at = admitted_at
    claim.discharged_at = discharged_at
    claim.length_of_stay_days = los
    claim.billed_paise = billed
    claim.line_items = [li.model_dump() for li in body.lineItems]

    # Build the packet and run the orchestrator resubmit flow
    packet = _build_packet(
        claim_number=claim.claim_number,
        claim_type=claim.type.value,
        hospital_name=hospital.name,
        insurer_name=insurer.name,
        policy=policy,
        body=body,
        los=los,
        billed=billed,
    )

    await orchestrator.resubmit(session, claim, packet, user)

    return await get(session, user, claim.id)


# ── workflow info endpoints ──────────────────────────────────
async def get_valid_transitions(
    session: AsyncSession, user: AuthUser, claim_id: str
) -> dict:
    """Return the valid next states for a claim."""
    claim = await _find_scoped(session, user, claim_id)
    return {
        "claimId": claim.id,
        "currentStatus": claim.status.value,
        "validTransitions": orchestrator.valid_next_states(claim.status),
    }


async def get_timeline(
    session: AsyncSession, user: AuthUser, claim_id: str
) -> dict:
    """Return the full event timeline with stage durations."""
    claim = await _load_detail(session, claim_id, user)
    events = sorted(claim.events, key=lambda e: e.created_at)

    timeline: list[dict] = []
    for i, evt in enumerate(events):
        entry = S.claim_event(evt)
        # Calculate duration to next event
        if i < len(events) - 1:
            delta = (events[i + 1].created_at - evt.created_at).total_seconds()
            entry["durationToNextMs"] = int(delta * 1000)
        else:
            entry["durationToNextMs"] = None
        timeline.append(entry)

    return {
        "claimId": claim.id,
        "claimNumber": claim.claim_number,
        "currentStatus": claim.status.value,
        "timeline": timeline,
        "totalEvents": len(timeline),
    }


# ── internal ─────────────────────────────────────────────────
async def _find_scoped(session: AsyncSession, user: AuthUser, claim_id: str) -> Claim:
    stmt = select(Claim).where(Claim.id == claim_id)
    where = _scope_where(user)
    if where is not None:
        stmt = stmt.where(where)
    claim = (await session.execute(stmt)).scalar_one_or_none()
    if not claim:
        raise not_found("Claim not found")
    return claim


def _parse_dt(value: str) -> datetime:
    """Parse an ISO date/datetime string into a naive UTC datetime."""
    s = value.replace("Z", "+00:00")
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt
