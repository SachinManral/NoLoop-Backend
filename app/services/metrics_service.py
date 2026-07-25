"""Role-scoped analytics dashboard. Port of metrics.service.ts."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from math import floor

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import BedStatus, Bed, Claim, ClaimStatus, Role, Verdict
from app.core.deps import AuthUser


def _round(x: float) -> int:
    """Math.round — half up."""
    return floor(x + 0.5)


def _scope(user: AuthUser):
    role = user.get("role")
    tenant_id = user.get("tenantId")
    if role in (Role.HOSPITAL_ADMIN.value, Role.HOSPITAL_STAFF.value):
        return (Claim.hospital_tenant_id == (tenant_id or "__none__"), "HOSPITAL", tenant_id)
    if role in (Role.INSURER_ADMIN.value, Role.INSURER_ADJUDICATOR.value):
        return (Claim.insurer_tenant_id == (tenant_id or "__none__"), "INSURER", None)
    return (None, "PLATFORM", None)


async def summary(session: AsyncSession, user: AuthUser) -> dict:
    where, label, hospital_id = _scope(user)

    stmt = select(Claim).options(selectinload(Claim.fraud_flags)).order_by(
        Claim.submitted_at.desc()
    )
    if where is not None:
        stmt = stmt.where(where)
    claims = (await session.execute(stmt)).scalars().all()

    total = len(claims)
    decided = [c for c in claims if c.verdict is not None]
    approved = len([c for c in claims if c.verdict == Verdict.APPROVE])
    denied = len([c for c in claims if c.verdict == Verdict.DENY])
    queried = len([c for c in claims if c.verdict == Verdict.QUERY])
    flagged = len([c for c in claims if len(c.fraud_flags) > 0])
    auto = len([c for c in decided if not c.overridden_by_id])

    def count(status: ClaimStatus) -> int:
        return len([c for c in claims if c.status == status])

    tats = [c.tat_seconds for c in decided if isinstance(c.tat_seconds, int)]
    avg_tat = _round(sum(tats) / len(tats)) if tats else 0

    billed_paise = sum(c.billed_paise for c in claims)
    approved_paise = sum(
        (c.approved_amount_paise or 0)
        for c in claims
        if c.status in (ClaimStatus.APPROVED, ClaimStatus.SETTLED)
    )
    saved_paise = sum(
        max(0, c.billed_paise - (c.approved_amount_paise or 0)) for c in decided
    )

    signal_counts: dict[str, int] = {}
    for c in claims:
        for f in c.fraud_flags:
            signal_counts[f.signal] = signal_counts.get(f.signal, 0) + 1
    top_signals = sorted(
        ({"signal": s, "count": n} for s, n in signal_counts.items()),
        key=lambda x: x["count"],
        reverse=True,
    )

    trend = []
    today = datetime.now(timezone.utc)
    for i in range(6, -1, -1):
        key = (today - timedelta(days=i)).date().isoformat()
        day_claims = [
            c for c in claims if c.submitted_at.date().isoformat() == key
        ]
        trend.append(
            {
                "date": key,
                "count": len(day_claims),
                "approvedPaise": sum((c.approved_amount_paise or 0) for c in day_claims),
            }
        )

    def pct(n: int, d: int) -> int:
        return _round(n / d * 100) if d else 0

    result: dict = {
        "scope": label,
        "totals": {
            "claims": total,
            "decided": len(decided),
            "processing": count(ClaimStatus.PROCESSING),
            "approved": count(ClaimStatus.APPROVED),
            "denied": count(ClaimStatus.DENIED),
            "queried": count(ClaimStatus.QUERIED),
            "underReview": count(ClaimStatus.UNDER_REVIEW),
            "settled": count(ClaimStatus.SETTLED),
        },
        "rates": {
            "approvalPct": pct(approved, len(decided)),
            "denialPct": pct(denied, len(decided)),
            "queryPct": pct(queried, len(decided)),
            "autoDecisionPct": pct(auto, len(decided)),
            "fraudPct": pct(flagged, total),
        },
        "tat": {
            "avgSeconds": avg_tat,
            "fastestSeconds": min(tats) if tats else 0,
            "slowestSeconds": max(tats) if tats else 0,
        },
        "money": {
            "billedPaise": billed_paise,
            "approvedPaise": approved_paise,
            "savedPaise": saved_paise,
        },
        "fraud": {
            "totalFlags": sum(signal_counts.values()),
            "flaggedClaims": flagged,
            "topSignals": top_signals,
        },
        "trend": trend,
        "recent": [
            {
                "claimNumber": c.claim_number,
                "patientName": c.patient_name,
                "procedure": c.procedure,
                "status": c.status.value,
                "verdict": c.verdict.value if c.verdict else None,
                "billedPaise": c.billed_paise,
                "approvedAmountPaise": c.approved_amount_paise,
                "tatSeconds": c.tat_seconds,
                "flagCount": len(c.fraud_flags),
                "submittedAt": c.submitted_at,
            }
            for c in claims[:8]
        ],
    }

    if label == "HOSPITAL" and hospital_id:
        total_beds = (
            await session.execute(
                select(func.count()).select_from(Bed).where(Bed.hospital_tenant_id == hospital_id)
            )
        ).scalar_one()
        occupied = (
            await session.execute(
                select(func.count())
                .select_from(Bed)
                .where(Bed.hospital_tenant_id == hospital_id, Bed.status == BedStatus.OCCUPIED)
            )
        ).scalar_one()
        maintenance = (
            await session.execute(
                select(func.count())
                .select_from(Bed)
                .where(Bed.hospital_tenant_id == hospital_id, Bed.status == BedStatus.MAINTENANCE)
            )
        ).scalar_one()
        result["beds"] = {
            "totalBeds": total_beds,
            "occupied": occupied,
            "available": total_beds - occupied - maintenance,
            "occupancyRate": _round(occupied / total_beds * 100) if total_beds else 0,
        }

    return result
