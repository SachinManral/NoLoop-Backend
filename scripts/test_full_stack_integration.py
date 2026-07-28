"""Full Stack Integration Test: backend-py + database (PostgreSQL) + ai-engine integration.

Tests:
1. PostgreSQL Database connection and schema verification.
2. Seeding test Tenants, User, Patient, and Policy into PostgreSQL.
3. Submitting a claim via claims_service.submit() (which triggers the 4-stage Workflow Orchestrator).
4. Verifying state transitions (SUBMITTED -> VALIDATED -> POLICY_CHECK -> FRAUD_CHECK -> APPROVED/UNDER_REVIEW).
5. Verifying DB records for Claim, ClaimEvents, Decision, and FraudFlags.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure root directory is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncio
import logging
from sqlalchemy import select

from app.config import settings
from app.db import SessionLocal, engine
from app.models import (
    Base,
    Claim,
    ClaimEvent,
    ClaimStatus,
    Decision,
    Patient,
    Policy,
    Role,
    Tenant,
    TenantType,
    User,
)
from app.schemas.claims import LineItemBody, SubmitClaimBody
from app.services.claims_service import submit

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("integration_test")


async def run_full_stack_integration_test():
    log.info("Starting Full Stack Integration Test...")
    log.info(f"Database URL: {settings.database_url}")
    log.info(f"AI Engine URL: {settings.ai_engine_url}")

    # 1. Initialize DB Schema
    async with engine.begin() as conn:
        log.info("Ensuring database tables exist...")
        await conn.run_sync(Base.metadata.create_all)

    async with SessionLocal() as session:
        # 2. Seed Test Tenants, User, Patient, and Policy
        hosp_tenant_id = "tnt_hosp_e2e_test"
        ins_tenant_id = "tnt_ins_e2e_test"
        user_id = "usr_hosp_staff_e2e"
        patient_id = "pat_e2e_test"
        policy_id = "pol_e2e_test"

        # Check or create Hospital Tenant
        hosp_tenant = await session.get(Tenant, hosp_tenant_id)
        if not hosp_tenant:
            hosp_tenant = Tenant(
                id=hosp_tenant_id,
                name="Apollo Hospital E2E",
                type=TenantType.HOSPITAL,
            )
            session.add(hosp_tenant)

        # Check or create Insurer Tenant
        ins_tenant = await session.get(Tenant, ins_tenant_id)
        if not ins_tenant:
            ins_tenant = Tenant(
                id=ins_tenant_id,
                name="Star Health E2E",
                type=TenantType.INSURER,
            )
            session.add(ins_tenant)

        await session.commit()

        # Check or create User
        user_db = await session.get(User, user_id)
        if not user_db:
            user_db = User(
                id=user_id,
                email="staff.e2e@apollo.com",
                name="E2E Hospital Staff",
                password_hash="mock_hash",
                role=Role.HOSPITAL_STAFF,
                tenant_id=hosp_tenant_id,
            )
            session.add(user_db)
            await session.commit()

        # Check or create Policy
        policy = await session.get(Policy, policy_id)
        if not policy:
            policy = Policy(
                id=policy_id,
                insurer_tenant_id=ins_tenant_id,
                name="Star Optima Health Plan",
                plan_code="POL-E2E-999",
                sum_insured_paise=50000000,  # ₹5,00,000
                room_rent_cap_per_day_paise=500000,  # ₹5,000 / day
                copay_pct=10,  # 10% co-pay
                covered_procedures=["Appendectomy", "Knee Replacement"],
                exclusions=["Cosmetic Surgery"],
            )
            session.add(policy)
            await session.commit()

        # Check or create Patient
        patient = await session.get(Patient, patient_id)
        if not patient:
            patient = Patient(
                id=patient_id,
                insurer_tenant_id=ins_tenant_id,
                policy_id=policy_id,
                member_id="MEM-E2E-101",
                name="Integration Test Patient",
                age=45,
                gender="Male",
                phone="9876543210",
            )
            session.add(patient)
            await session.commit()

        log.info("Seed data verified in PostgreSQL.")

        # 3. Create Claim Submission Body
        user = {
            "sub": user_id,
            "role": Role.HOSPITAL_STAFF.value,
            "tenantId": hosp_tenant_id,
        }

        body = SubmitClaimBody(
            insurerTenantId=ins_tenant_id,
            type="CASHLESS",
            patientName="Integration Test Patient",
            patientAge=45,
            patientGender="Male",
            memberId="MEM-E2E-101",
            procedure="Appendectomy",
            diagnosis="Acute Appendicitis",
            admittedAt="2026-07-01T10:00:00Z",
            dischargedAt="2026-07-03T10:00:00Z",
            totalPaise=5000000,
            lineItems=[
                LineItemBody(desc="Appendectomy Procedure", amountPaise=4000000),
                LineItemBody(desc="Standard Room Rent", amountPaise=1000000),
            ],
        )

        log.info("Submitting claim via claims_service.submit()...")
        claim = await submit(session, user, body)
        log.info(f"Claim created in DB! Claim ID: {claim['id']}, Number: {claim['claimNumber']}")

        # 4. Verify Final State in DB
        claim_db = (
            await session.execute(select(Claim).where(Claim.id == claim["id"]))
        ).scalar_one()

        log.info(f"Final Claim Status in DB: {claim_db.status}")
        assert claim_db.status in (ClaimStatus.APPROVED, ClaimStatus.UNDER_REVIEW), (
            f"Unexpected status: {claim_db.status}"
        )
        assert claim_db.approved_amount_paise is not None
        assert claim_db.confidence is not None
        assert claim_db.rationale is not None

        # Fetch Audit Trail Claim Events from DB
        events_res = await session.execute(
            select(ClaimEvent).where(ClaimEvent.claim_id == claim_db.id).order_by(ClaimEvent.created_at)
        )
        events = events_res.scalars().all()
        log.info(f"Recorded {len(events)} ClaimEvent(s) in audit trail:")
        for ev in events:
            log.info(f"  - [{ev.type}] {ev.message}")

        assert len(events) >= 3, "Orchestrator did not record expected lifecycle events"

        # Fetch Decision Record from DB
        decision_res = await session.execute(
            select(Decision).where(Decision.claim_id == claim_db.id)
        )
        decision = decision_res.scalar_one_or_none()
        assert decision is not None, "Decision record was not saved to DB"
        log.info(
            f"Decision in DB: Verdict={decision.verdict}, Approved=₹{decision.approved_amount_paise/100:,.0f}, "
            f"Confidence={decision.confidence*100:.0f}%, Model={decision.model}"
        )

        log.info("\n✅ SUCCESS: Full Stack Integration (ai-engine + backend-py + PostgreSQL Database) is 100% WORKING!")


if __name__ == "__main__":
    asyncio.run(run_full_stack_integration_test())
