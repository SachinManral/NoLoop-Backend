"""ORM -> dict serialisers producing the EXACT camelCase JSON the NestJS API
returned (field names + nesting must match so the frontends are unaffected)."""

from __future__ import annotations

from app.models import (
    ActivityLog,
    Admission,
    Claim,
    ClaimEvent,
    Decision,
    FraudFlag,
    Patient,
    Policy,
    Tenant,
    User,
)


def _enum(v):
    return v.value if v is not None else None


# ── auth ─────────────────────────────────────────────────────
def user_account(u: User) -> dict:
    return {
        "id": u.id,
        "email": u.email,
        "name": u.name,
        "role": _enum(u.role),
        "tenantId": u.tenant_id,
    }


# ── admin / org ──────────────────────────────────────────────
def org_summary(t: Tenant, employee_count: int) -> dict:
    return {
        "id": t.id,
        "name": t.name,
        "type": _enum(t.type),
        "createdAt": t.created_at,
        "employeeCount": employee_count,
    }


def org_member(u: User) -> dict:
    return {
        "id": u.id,
        "name": u.name,
        "email": u.email,
        "role": _enum(u.role),
        "status": _enum(u.status),
        "createdAt": u.created_at,
    }


def org_detail(t: Tenant, members: list[User]) -> dict:
    return {
        "id": t.id,
        "name": t.name,
        "type": _enum(t.type),
        "createdAt": t.created_at,
        "users": [org_member(u) for u in members],
    }


def log_entry(log: ActivityLog) -> dict:
    return {
        "id": log.id,
        "tenantId": log.tenant_id,
        "actorId": log.actor_id,
        "action": log.action,
        "detail": log.detail,
        "metadata": log.metadata_,
        "createdAt": log.created_at,
        "tenant": (
            {"name": log.tenant.name, "type": _enum(log.tenant.type)}
            if log.tenant
            else None
        ),
        "actor": (
            {"name": log.actor.name, "email": log.actor.email} if log.actor else None
        ),
    }


def user_roster(u: User) -> dict:
    return {
        "id": u.id,
        "name": u.name,
        "email": u.email,
        "role": _enum(u.role),
        "status": _enum(u.status),
        "createdAt": u.created_at,
        "tenant": (
            {"id": u.tenant.id, "name": u.tenant.name, "type": _enum(u.tenant.type)}
            if u.tenant
            else None
        ),
    }


def user_admin_fields(u: User) -> dict:
    """Shape returned by updateUser / setStatus."""
    return {
        "id": u.id,
        "name": u.name,
        "email": u.email,
        "role": _enum(u.role),
        "status": _enum(u.status),
    }


def employee(u: User) -> dict:
    return {
        "id": u.id,
        "name": u.name,
        "email": u.email,
        "role": _enum(u.role),
        "createdAt": u.created_at,
    }


# ── beds ─────────────────────────────────────────────────────
def admission(a: Admission) -> dict:
    return {
        "id": a.id,
        "hospitalTenantId": a.hospital_tenant_id,
        "bedId": a.bed_id,
        "patientId": a.patient_id,
        "patientName": a.patient_name,
        "patientAge": a.patient_age,
        "patientGender": a.patient_gender,
        "diagnosis": a.diagnosis,
        "procedure": a.procedure,
        "status": _enum(a.status),
        "admittedAt": a.admitted_at,
        "dischargedAt": a.discharged_at,
        "createdAt": a.created_at,
    }


# ── catalog ──────────────────────────────────────────────────
def policy_with_counts(p: Policy, patients: int, claims: int) -> dict:
    return {
        "id": p.id,
        "insurerTenantId": p.insurer_tenant_id,
        "name": p.name,
        "planCode": p.plan_code,
        "sumInsuredPaise": p.sum_insured_paise,
        "roomRentCapPerDayPaise": p.room_rent_cap_per_day_paise,
        "copayPct": p.copay_pct,
        "waitingPeriodDays": p.waiting_period_days,
        "coveredProcedures": list(p.covered_procedures or []),
        "exclusions": list(p.exclusions or []),
        "createdAt": p.created_at,
        "_count": {"patients": patients, "claims": claims},
    }


def patient_with_counts(p: Patient, claims: int) -> dict:
    return {
        "id": p.id,
        "insurerTenantId": p.insurer_tenant_id,
        "policyId": p.policy_id,
        "memberId": p.member_id,
        "name": p.name,
        "age": p.age,
        "gender": p.gender,
        "phone": p.phone,
        "createdAt": p.created_at,
        "policy": {"name": p.policy.name} if p.policy else None,
        "_count": {"claims": claims},
    }


# ── claims ───────────────────────────────────────────────────
def fraud_flag(f: FraudFlag) -> dict:
    return {
        "id": f.id,
        "claimId": f.claim_id,
        "signal": f.signal,
        "severity": _enum(f.severity),
        "detail": f.detail,
        "createdAt": f.created_at,
    }


def claim_event(e: ClaimEvent) -> dict:
    return {
        "id": e.id,
        "claimId": e.claim_id,
        "type": _enum(e.type),
        "message": e.message,
        "actorId": e.actor_id,
        "metadata": e.metadata_,
        "createdAt": e.created_at,
    }


def decision(d: Decision) -> dict:
    return {
        "id": d.id,
        "claimId": d.claim_id,
        "verdict": _enum(d.verdict),
        "approvedAmountPaise": d.approved_amount_paise,
        "confidence": d.confidence,
        "rationale": d.rationale,
        "citedClauseRefs": list(d.cited_clause_refs or []),
        "model": d.model,
        "latencyMs": d.latency_ms,
        "createdAt": d.created_at,
    }


def claim_summary(c: Claim, fraud_count: int) -> dict:
    return {
        "id": c.id,
        "claimNumber": c.claim_number,
        "type": _enum(c.type),
        "patientName": c.patient_name,
        "procedure": c.procedure,
        "hospital": c.hospital.name,
        "insurer": c.insurer.name,
        "billedPaise": c.billed_paise,
        "approvedAmountPaise": c.approved_amount_paise,
        "status": _enum(c.status),
        "verdict": _enum(c.verdict),
        "confidence": c.confidence,
        "fraudFlagCount": fraud_count,
        "tatSeconds": c.tat_seconds,
        "submittedAt": c.submitted_at,
        "decidedAt": c.decided_at,
    }


def claim_detail(c: Claim) -> dict:
    """Full claim with the same nested includes Prisma returned for `get`."""
    return {
        "id": c.id,
        "claimNumber": c.claim_number,
        "type": _enum(c.type),
        "hospitalTenantId": c.hospital_tenant_id,
        "insurerTenantId": c.insurer_tenant_id,
        "policyId": c.policy_id,
        "patientId": c.patient_id,
        "admissionId": c.admission_id,
        "patientName": c.patient_name,
        "patientAge": c.patient_age,
        "patientGender": c.patient_gender,
        "diagnosis": c.diagnosis,
        "procedure": c.procedure,
        "admittedAt": c.admitted_at,
        "dischargedAt": c.discharged_at,
        "lengthOfStayDays": c.length_of_stay_days,
        "sumInsuredPaise": c.sum_insured_paise,
        "billedPaise": c.billed_paise,
        "lineItems": c.line_items,
        "status": _enum(c.status),
        "verdict": _enum(c.verdict),
        "approvedAmountPaise": c.approved_amount_paise,
        "confidence": c.confidence,
        "rationale": c.rationale,
        "citedClauseRefs": list(c.cited_clause_refs or []),
        "aiModel": c.ai_model,
        "aiLatencyMs": c.ai_latency_ms,
        "tatSeconds": c.tat_seconds,
        "submittedById": c.submitted_by_id,
        "overriddenById": c.overridden_by_id,
        "overrideNote": c.override_note,
        "overriddenAt": c.overridden_at,
        "submittedAt": c.submitted_at,
        "decidedAt": c.decided_at,
        "settledAt": c.settled_at,
        "hospital": {"name": c.hospital.name},
        "insurer": {"name": c.insurer.name},
        "policy": (
            {"name": c.policy.name, "planCode": c.policy.plan_code}
            if c.policy
            else None
        ),
        "patient": {"memberId": c.patient.member_id} if c.patient else None,
        # fraudFlags asc, events asc, decisions desc — matches Prisma `orderBy`.
        "fraudFlags": [
            fraud_flag(f) for f in sorted(c.fraud_flags, key=lambda f: f.created_at)
        ],
        "events": [
            claim_event(e) for e in sorted(c.events, key=lambda e: e.created_at)
        ],
        "decisions": [
            decision(d)
            for d in sorted(c.decisions, key=lambda d: d.created_at, reverse=True)
        ],
        "overriddenBy": (
            {"name": c.overridden_by.name, "email": c.overridden_by.email}
            if c.overridden_by
            else None
        ),
    }


def claim_track(c: Claim, flag_count: int) -> dict:
    return {
        "claimNumber": c.claim_number,
        "patientName": c.patient_name,
        "procedure": c.procedure,
        "hospital": c.hospital.name,
        "insurer": c.insurer.name,
        "status": _enum(c.status),
        "verdict": _enum(c.verdict),
        "billedPaise": c.billed_paise,
        "approvedAmountPaise": c.approved_amount_paise,
        "rationale": c.rationale,
        "tatSeconds": c.tat_seconds,
        "submittedAt": c.submitted_at,
        "decidedAt": c.decided_at,
        "settledAt": c.settled_at,
        "events": [
            claim_event(e) for e in sorted(c.events, key=lambda e: e.created_at)
        ],
        "flagCount": flag_count,
    }
