"""Demo seeder — makes the whole platform "live".

Creates a demo insurer + hospital (each with admin + staff), a policy,
policyholders, wards/beds with real occupancy, and ~50 historical claims that
are adjudicated by the REAL AI engine (HTTP, with an inline fallback if it's
down). Faithful port of backend/scripts/seed-demo.ts.

⚠️ All org/hospital/insurer names are ENTIRELY FICTIONAL.

Usage:
    python scripts/seed_demo.py
    AI_ENGINE_URL=... python scripts/seed_demo.py
"""

from __future__ import annotations

import asyncio
import os
import random
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx  # noqa: E402
from sqlalchemy import delete, or_, select, update  # noqa: E402

from app.config import settings  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.db import SessionLocal, engine  # noqa: E402
from app.models import (  # noqa: E402
    ActivityLog,
    Admission,
    AdmissionStatus,
    Bed,
    BedStatus,
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
    User,
    Verdict,
    Ward,
)

AI_URL = settings.ai_engine_url.rstrip("/")
DAY = timedelta(days=1)


def rupees(n: int) -> int:
    return n * 100


def rint(lo: int, hi: int) -> int:
    return random.randint(lo, hi)


def pick(items):
    return random.choice(items)


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


INSURER_NAME = "Everwell Assurance"
HOSPITAL_NAME = "Meadowpine Hospital"
FIRST = ["Sachin", "Priya", "Rahul", "Anita", "Vikram", "Neha", "Arjun", "Kavya",
         "Rohit", "Meera", "Aditya", "Sneha", "Karan", "Divya"]
LAST = ["Sharma", "Patel", "Reddy", "Iyer", "Nair", "Gupta", "Singh", "Mehta", "Rao", "Das"]
PROCEDURES = [
    {"name": "Appendectomy", "los": 2, "lo": 40000, "hi": 90000},
    {"name": "Cataract Surgery", "los": 1, "lo": 25000, "hi": 60000},
    {"name": "Angioplasty", "los": 3, "lo": 150000, "hi": 350000},
    {"name": "Cesarean Delivery", "los": 3, "lo": 60000, "hi": 140000},
    {"name": "Knee Replacement", "los": 4, "lo": 200000, "hi": 450000},
    {"name": "Dialysis Session", "los": 1, "lo": 8000, "hi": 20000},
]
COVERED = [p["name"] for p in PROCEDURES]
EXCLUSIONS = ["Cosmetic Rhinoplasty", "LASIK Eye Surgery", "Dental Implants"]


async def adjudicate(client: httpx.AsyncClient, packet: dict) -> dict:
    try:
        res = await client.post(f"{AI_URL}/adjudicate", json=packet, timeout=8.0)
        if res.status_code == 200:
            return res.json()
    except Exception:
        pass
    return fallback(packet)


def fallback(p: dict) -> dict:
    proc = p["admission"]["procedure"].lower()
    covered = proc in [x.lower() for x in p["policy"]["coveredProcedures"]]
    excluded = proc in [x.lower() for x in p["policy"]["exclusions"]]
    line_sum = sum(li["amountPaise"] for li in p["bill"]["lineItems"])
    over_si = p["bill"]["totalPaise"] > p["policy"]["sumInsuredPaise"]
    flags = []
    if line_sum != p["bill"]["totalPaise"] and not (
        over_si and line_sum <= p["policy"]["sumInsuredPaise"]
    ):
        flags.append({"signal": "BILL_MATH_MISMATCH", "severity": "HIGH",
                      "detail": "Line items do not sum to total."})
    if over_si:
        flags.append({"signal": "AMOUNT_OUTLIER", "severity": "MEDIUM",
                      "detail": "Exceeds sum insured."})
    if excluded:
        flags.append({"signal": "POLICY_EXCLUSION", "severity": "HIGH",
                      "detail": "Procedure excluded."})
    sig = {f["signal"] for f in flags}
    verdict = "APPROVE"
    approved: int | None = min(p["bill"]["totalPaise"], p["policy"]["sumInsuredPaise"])
    if "BILL_MATH_MISMATCH" in sig or "POLICY_EXCLUSION" in sig:
        verdict, approved = "DENY", 0
    elif not covered:
        verdict, approved = "QUERY", None
    elif "AMOUNT_OUTLIER" in sig:
        verdict, approved = "QUERY", None
    return {
        "verdict": verdict,
        "approvedAmountPaise": approved,
        "confidence": 0.6 if verdict == "QUERY" else 0.92,
        "rationale": f"{verdict} (seed fallback).",
        "citedClauseRefs": ["COVERED_PROCEDURES"] if covered else (["EXCLUSIONS"] if excluded else []),
        "fraudFlags": flags,
        "model": "seed-fallback",
    }


def build_claim(policy_sum_insured: int) -> dict:
    r = random.random()
    if r < 0.6:
        anomaly = "CLEAN"
    elif r < 0.72:
        anomaly = "LENGTH_OF_STAY_ANOMALY"
    elif r < 0.84:
        anomaly = "BILL_MATH_MISMATCH"
    elif r < 0.93:
        anomaly = "POLICY_EXCLUSION"
    else:
        anomaly = "AMOUNT_OUTLIER"

    excluded = anomaly == "POLICY_EXCLUSION"
    proc = (
        {"name": pick(EXCLUSIONS), "los": 2, "lo": 50000, "hi": 120000}
        if excluded
        else pick(PROCEDURES)
    )
    los = proc["los"] + rint(8, 14) if anomaly == "LENGTH_OF_STAY_ANOMALY" else max(
        1, proc["los"] + rint(-1, 1)
    )
    submitted_at = utcnow() - rint(0, 6) * DAY - timedelta(seconds=rint(0, 80000))
    admitted_at = submitted_at - (los + 1) * DAY
    discharged_at = admitted_at + los * DAY
    room_per_day = rupees(rint(3000, 8000))
    procedure_cost = rupees(rint(proc["lo"], proc["hi"]))
    meds = rupees(rint(2000, 15000))
    items = [
        {"desc": f"Room charges ({los} days)", "amountPaise": room_per_day * los},
        {"desc": proc["name"], "amountPaise": procedure_cost},
        {"desc": "Medicines & consumables", "amountPaise": meds},
    ]
    line_sum = sum(it["amountPaise"] for it in items)
    total = line_sum
    if anomaly == "AMOUNT_OUTLIER":
        total = policy_sum_insured + rupees(rint(50000, 200000))
    if anomaly == "BILL_MATH_MISMATCH":
        total = line_sum + rupees(rint(15000, 60000))
    return {
        "proc": proc, "los": los, "submittedAt": submitted_at, "admittedAt": admitted_at,
        "dischargedAt": discharged_at, "items": items, "total": total, "anomaly": anomaly,
    }


def fmt(d: datetime) -> str:
    return d.date().isoformat()


async def _cleanup(session, name: str) -> None:
    """Remove any prior demo org with this name (idempotent re-seed)."""
    tenant = (
        await session.execute(select(Tenant).where(Tenant.name == name).limit(1))
    ).scalar_one_or_none()
    if not tenant:
        return
    tid = tenant.id
    member_ids = (
        await session.execute(select(User.id).where(User.tenant_id == tid))
    ).scalars().all()
    await session.execute(
        delete(Claim).where(or_(Claim.hospital_tenant_id == tid, Claim.insurer_tenant_id == tid))
    )
    await session.execute(
        update(ClaimEvent).where(ClaimEvent.actor_id.in_(member_ids)).values(actor_id=None)
    )
    await session.execute(delete(Admission).where(Admission.hospital_tenant_id == tid))
    await session.execute(delete(Bed).where(Bed.hospital_tenant_id == tid))
    await session.execute(delete(Ward).where(Ward.hospital_tenant_id == tid))
    await session.execute(delete(Patient).where(Patient.insurer_tenant_id == tid))
    await session.execute(delete(Policy).where(Policy.insurer_tenant_id == tid))
    await session.execute(
        delete(ActivityLog).where(
            or_(ActivityLog.tenant_id == tid, ActivityLog.actor_id.in_(member_ids))
        )
    )
    await session.execute(delete(User).where(User.tenant_id == tid))
    await session.execute(delete(Tenant).where(Tenant.id == tid))
    await session.commit()


async def main() -> None:
    print("🌱 Seeding NoLoop demo data…")
    async with SessionLocal() as session:
        for name in (INSURER_NAME, HOSPITAL_NAME):
            await _cleanup(session, name)

        insurer = Tenant(name=INSURER_NAME, type=TenantType.INSURER)
        session.add(insurer)
        await session.flush()
        session.add_all([
            User(email="everwell.assurance@noloop.in", name="Everwell Admin",
                 password_hash=hash_password("Insurer@123"),
                 role=Role.INSURER_ADMIN, tenant_id=insurer.id),
            User(email="adjudicator.everwellassurance@noloop.in", name="Asha Verma",
                 password_hash=hash_password("Adjudicator@123"),
                 role=Role.INSURER_ADJUDICATOR, tenant_id=insurer.id),
        ])

        hospital = Tenant(name=HOSPITAL_NAME, type=TenantType.HOSPITAL)
        session.add(hospital)
        await session.flush()
        session.add(
            User(email="meadowpine.hospital@noloop.in", name="Meadowpine Admin",
                 password_hash=hash_password("Hospital@123"),
                 role=Role.HOSPITAL_ADMIN, tenant_id=hospital.id)
        )
        hosp_staff = User(
            email="nurse.meadowpinehospital@noloop.in", name="Ravi Kumar",
            password_hash=hash_password("Staff@123"),
            role=Role.HOSPITAL_STAFF, tenant_id=hospital.id,
        )
        session.add(hosp_staff)
        await session.flush()

        policy = Policy(
            insurer_tenant_id=insurer.id,
            name="Everwell Secure Health",
            plan_code="EW-SEC-500",
            sum_insured_paise=rupees(500000),
            room_rent_cap_per_day_paise=rupees(6000),
            copay_pct=10,
            waiting_period_days=30,
            covered_procedures=COVERED,
            exclusions=EXCLUSIONS,
        )
        session.add(policy)
        await session.flush()

        patients = []
        for i in range(12):
            p = Patient(
                insurer_tenant_id=insurer.id,
                policy_id=policy.id,
                member_id=f"EW-{100000 + i}",
                name=f"{pick(FIRST)} {pick(LAST)}",
                age=rint(8, 82),
                gender=pick(["M", "F"]),
                phone=f"9{rint(100000000, 999999999)}",
            )
            session.add(p)
            patients.append(p)
        await session.flush()

        ward_defs = [
            ("General Ward", 12), ("ICU", 6), ("Maternity", 6), ("Private Rooms", 8)
        ]
        all_beds: list[Bed] = []
        for wname, count in ward_defs:
            ward = Ward(hospital_tenant_id=hospital.id, name=wname)
            session.add(ward)
            await session.flush()
            for b in range(1, count + 1):
                bed = Bed(hospital_tenant_id=hospital.id, ward_id=ward.id, label=f"{wname[0]}{b}")
                session.add(bed)
                all_beds.append(bed)
        await session.flush()

        occupy_count = round(len(all_beds) * 0.6)
        for i in range(occupy_count):
            bed = all_beds[i]
            proc = pick(PROCEDURES)
            p = pick(patients)
            session.add(
                Admission(
                    hospital_tenant_id=hospital.id, bed_id=bed.id, patient_id=p.id,
                    patient_name=p.name, patient_age=p.age, patient_gender=p.gender,
                    diagnosis=f"{proc['name']} indicated", procedure=proc["name"],
                    status=AdmissionStatus.ADMITTED,
                    admitted_at=utcnow() - rint(0, 8) * DAY,
                )
            )
            bed.status = BedStatus.OCCUPIED
        await session.flush()

        n = 52
        approved = denied = queried = engine_used = 0
        async with httpx.AsyncClient() as client:
            for i in range(n):
                c = build_claim(policy.sum_insured_paise)
                link_patient = pick(patients) if random.random() < 0.5 else None
                ctype = "CASHLESS" if random.random() < 0.7 else "REIMBURSEMENT"
                packet = {
                    "ref": f"SEED-{i}",
                    "type": ctype,
                    "hospital": hospital.name,
                    "insurer": insurer.name,
                    "policy": {
                        "policyNo": policy.plan_code,
                        "sumInsuredPaise": policy.sum_insured_paise,
                        "roomRentCapPerDayPaise": policy.room_rent_cap_per_day_paise,
                        "copayPct": policy.copay_pct,
                        "coveredProcedures": COVERED,
                        "exclusions": EXCLUSIONS,
                    },
                    "admission": {
                        "admittedAt": fmt(c["admittedAt"]),
                        "dischargedAt": fmt(c["dischargedAt"]),
                        "lengthOfStayDays": c["los"],
                        "procedure": c["proc"]["name"],
                        "diagnosis": f"{c['proc']['name']} indicated",
                    },
                    "bill": {"lineItems": c["items"], "totalPaise": c["total"]},
                }
                decision = await adjudicate(client, packet)
                if decision.get("model") != "seed-fallback":
                    engine_used += 1

                verdict = decision["verdict"]
                status = (
                    ClaimStatus.APPROVED if verdict == "APPROVE"
                    else ClaimStatus.DENIED if verdict == "DENY"
                    else ClaimStatus.QUERIED
                )
                if status == ClaimStatus.APPROVED:
                    approved += 1
                elif status == ClaimStatus.DENIED:
                    denied += 1
                else:
                    queried += 1
                tat = rint(12, 52)
                decided_at = c["submittedAt"] + timedelta(seconds=tat)
                patient_name = link_patient.name if link_patient else f"{pick(FIRST)} {pick(LAST)}"
                claim_number = f"CLM-{200000 + i}"
                latency = rint(120, 900)

                claim = Claim(
                    claim_number=claim_number,
                    type=ClaimType(ctype),
                    hospital_tenant_id=hospital.id,
                    insurer_tenant_id=insurer.id,
                    policy_id=policy.id,
                    patient_id=link_patient.id if link_patient else None,
                    patient_name=patient_name,
                    patient_age=link_patient.age if link_patient else rint(8, 82),
                    patient_gender=link_patient.gender if link_patient else pick(["M", "F"]),
                    diagnosis=f"{c['proc']['name']} indicated",
                    procedure=c["proc"]["name"],
                    admitted_at=c["admittedAt"],
                    discharged_at=c["dischargedAt"],
                    length_of_stay_days=c["los"],
                    sum_insured_paise=policy.sum_insured_paise,
                    billed_paise=c["total"],
                    line_items=c["items"],
                    status=status,
                    verdict=Verdict(verdict),
                    approved_amount_paise=decision.get("approvedAmountPaise"),
                    confidence=decision["confidence"],
                    rationale=decision["rationale"],
                    cited_clause_refs=decision.get("citedClauseRefs") or [],
                    ai_model=decision["model"],
                    ai_latency_ms=latency,
                    tat_seconds=tat,
                    submitted_by_id=hosp_staff.id,
                    submitted_at=c["submittedAt"],
                    decided_at=decided_at,
                )
                session.add(claim)
                await session.flush()

                session.add(
                    Decision(
                        claim_id=claim.id, verdict=Verdict(verdict),
                        approved_amount_paise=decision.get("approvedAmountPaise"),
                        confidence=decision["confidence"], rationale=decision["rationale"],
                        cited_clause_refs=decision.get("citedClauseRefs") or [],
                        model=decision["model"], latency_ms=latency, created_at=decided_at,
                    )
                )
                for f in decision.get("fraudFlags") or []:
                    session.add(
                        FraudFlag(
                            claim_id=claim.id, signal=f["signal"],
                            severity=FraudSeverity(f["severity"]), detail=f["detail"],
                            created_at=decided_at,
                        )
                    )
                session.add_all([
                    ClaimEvent(claim_id=claim.id, type=ClaimEventType.SUBMITTED,
                               message=f"Claim {claim_number} submitted.",
                               created_at=c["submittedAt"]),
                    ClaimEvent(claim_id=claim.id, type=ClaimEventType.AI_STARTED,
                               message="AI adjudication engine started.",
                               created_at=c["submittedAt"] + timedelta(seconds=1)),
                    ClaimEvent(claim_id=claim.id, type=ClaimEventType.AI_DECISION,
                               message=f"AI verdict: {verdict}. {decision['rationale']}",
                               created_at=decided_at),
                ])
                if decision.get("fraudFlags"):
                    session.add(
                        ClaimEvent(
                            claim_id=claim.id, type=ClaimEventType.FRAUD_FLAGGED,
                            message=f"{len(decision['fraudFlags'])} anomaly signal(s).",
                            created_at=decided_at,
                        )
                    )
        await session.commit()

    await engine.dispose()
    print("\n✅ Demo seeded.")
    print(f"   Insurer:  {INSURER_NAME}")
    print(f"   Hospital: {HOSPITAL_NAME}")
    print(f"   Beds: {len(all_beds)} ({occupy_count} occupied)")
    print(f"   Patients: {len(patients)}")
    print(f"   Claims: {n}  → {approved} approved, {denied} denied, {queried} queried")
    print(f"   AI engine used for {engine_used}/{n} (rest via fallback)\n")
    print("🔑 Demo logins (all @noloop.in):")
    print("   Hospital admin:  meadowpine.hospital@noloop.in  /  Hospital@123")
    print("   Hospital staff:  nurse.meadowpinehospital@noloop.in  /  Staff@123")
    print("   Insurer admin:   everwell.assurance@noloop.in  /  Insurer@123")
    print("   Adjudicator:     adjudicator.everwellassurance@noloop.in  /  Adjudicator@123\n")


if __name__ == "__main__":
    asyncio.run(main())
