"""Auto-seed routine that runs on startup if the database is fresh."""

from __future__ import annotations

import logging
from sqlalchemy import select, func

from app.core.security import hash_password
from app.db import SessionLocal
from app.models import (
    Bed,
    Patient,
    Policy,
    Role,
    Tenant,
    TenantType,
    User,
    Ward,
)

log = logging.getLogger("auto_seed")

COVERED_PROCEDURES = [
    "Laparoscopic Cholecystectomy",
    "Emergency Appendectomy",
    "Appendectomy",
    "Total Knee Replacement",
    "Cataract Surgery (Phaco)",
    "Coronary Angiography",
    "Normal Delivery / Cesarean",
    "Hernia Repair (Mesh)",
    "Dialysis (Per Session)",
    "Chemotherapy Cycle",
    "Fracture Fixation (ORIF)",
    "Tonsillectomy",
]

EXCLUSIONS = [
    "Rhinoplasty (Cosmetic)",
    "Liposuction",
    "Experimental Stem Cell Therapy",
    "Teeth Whitening",
    "Refractive Eye Surgery (LASIK)",
    "Hair Transplant",
]


async def auto_seed_if_empty() -> None:
    """Checks if database is unseeded and automatically initializes standard demo data."""
    async with SessionLocal() as session:
        try:
            # Check if policies already exist
            policy_count = (await session.execute(select(func.count(Policy.id)))).scalar_one_or_none() or 0
            if policy_count > 0:
                log.info("Database already has policies (%d found).", policy_count)
                return

            log.info("Fresh database detected. Auto-seeding NoLoop demo organizations and policies...")

            # 1. Platform Admin
            admin_user = (
                await session.execute(select(User).where(User.email == "admin@noloop.in"))
            ).scalar_one_or_none()
            if not admin_user:
                session.add(
                    User(
                        email="admin@noloop.in",
                        name="Platform Administrator",
                        password_hash=hash_password("Admin@12345"),
                        role=Role.PLATFORM_ADMIN,
                    )
                )

            # 2. Insurer Tenant & Users
            insurer = (
                await session.execute(select(Tenant).where(Tenant.name == "Everwell Assurance"))
            ).scalar_one_or_none()
            if not insurer:
                insurer = Tenant(name="Everwell Assurance", type=TenantType.INSURER)
                session.add(insurer)
                await session.flush()

            existing_emails = set(
                (await session.execute(select(User.email))).scalars().all()
            )

            if "everwell.assurance@noloop.in" not in existing_emails:
                session.add(
                    User(
                        email="everwell.assurance@noloop.in",
                        name="Everwell Admin",
                        password_hash=hash_password("Insurer@123"),
                        role=Role.INSURER_ADMIN,
                        tenant_id=insurer.id,
                    )
                )
            if "adjudicator.everwellassurance@noloop.in" not in existing_emails:
                session.add(
                    User(
                        email="adjudicator.everwellassurance@noloop.in",
                        name="Asha Verma",
                        password_hash=hash_password("Adjudicator@123"),
                        role=Role.INSURER_ADJUDICATOR,
                        tenant_id=insurer.id,
                    )
                )
            if "tpa.everwellassurance@noloop.in" not in existing_emails:
                session.add(
                    User(
                        email="tpa.everwellassurance@noloop.in",
                        name="Rohit Nair",
                        password_hash=hash_password("Tpa@12345"),
                        role=Role.TPA_REVIEWER,
                        tenant_id=insurer.id,
                    )
                )

            # 3. Hospital Tenant & Users
            hospital = (
                await session.execute(select(Tenant).where(Tenant.name == "Meadowpine Hospital"))
            ).scalar_one_or_none()
            if not hospital:
                hospital = Tenant(name="Meadowpine Hospital", type=TenantType.HOSPITAL)
                session.add(hospital)
                await session.flush()

            if "meadowpine.hospital@noloop.in" not in existing_emails:
                session.add(
                    User(
                        email="meadowpine.hospital@noloop.in",
                        name="Dr. Rajesh Sharma",
                        password_hash=hash_password("Hospital@123"),
                        role=Role.HOSPITAL_ADMIN,
                        tenant_id=hospital.id,
                    )
                )
            if "nurse.meadowpinehospital@noloop.in" not in existing_emails:
                session.add(
                    User(
                        email="nurse.meadowpinehospital@noloop.in",
                        name="Ravi Kumar",
                        password_hash=hash_password("Hospital@123"),
                        role=Role.HOSPITAL_STAFF,
                        tenant_id=hospital.id,
                    )
                )

            await session.flush()

            # 4. Policies
            policy1 = Policy(
                insurer_tenant_id=insurer.id,
                name="Everwell Platinum Health Protect",
                plan_code="EW-PLT-1000",
                sum_insured_paise=100000000,  # ₹10,00,000
                room_rent_cap_per_day_paise=1000000,  # ₹10,000 / day
                copay_pct=10,
                waiting_period_days=30,
                covered_procedures=COVERED_PROCEDURES,
                exclusions=EXCLUSIONS,
            )
            policy2 = Policy(
                insurer_tenant_id=insurer.id,
                name="Everwell Comprehensive Secure Care",
                plan_code="EW-SEC-500",
                sum_insured_paise=50000000,  # ₹5,00,000
                room_rent_cap_per_day_paise=500000,  # ₹5,00,000 / day
                copay_pct=0,
                waiting_period_days=30,
                covered_procedures=COVERED_PROCEDURES,
                exclusions=EXCLUSIONS,
            )
            session.add_all([policy1, policy2])
            await session.flush()

            # 5. Sample Patients
            p1 = Patient(
                insurer_tenant_id=insurer.id,
                policy_id=policy1.id,
                member_id="EW-100234",
                name="Sachin Manral",
                age=32,
                gender="M",
                phone="9876543210",
            )
            p2 = Patient(
                insurer_tenant_id=insurer.id,
                policy_id=policy1.id,
                member_id="EW-100235",
                name="Aarav Sharma",
                age=38,
                gender="M",
                phone="9876543211",
            )
            session.add_all([p1, p2])

            # 6. Hospital Wards & Beds
            wards = [
                ("General Ward", 10),
                ("ICU / Critical Care", 6),
                ("Private Deluxe", 8),
            ]
            for wname, bcount in wards:
                ward = Ward(hospital_tenant_id=hospital.id, name=wname)
                session.add(ward)
                await session.flush()
                for b in range(1, bcount + 1):
                    session.add(
                        Bed(hospital_tenant_id=hospital.id, ward_id=ward.id, label=f"{wname[0]}{b}")
                    )

            await session.commit()
            log.info("Auto-seed completed successfully.")
        except Exception as e:
            await session.rollback()
            log.error("Auto-seed failed: %s", e)
