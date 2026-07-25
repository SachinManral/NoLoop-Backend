"""SQLAlchemy ORM models, mapped 1:1 onto the existing Prisma schema.

Table names are the Prisma model names (PascalCase) and columns are the Prisma
field names (camelCase) — both quoted by SQLAlchemy, so no migration is needed.
All money is paise (Integer). Relationships exist for eager-loading the same
shapes the NestJS services pull via Prisma `include`.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Float, ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, gen_cuid, pg_enum, utcnow
from app.models.enums import (
    AdmissionStatus,
    BedStatus,
    ClaimEventType,
    ClaimStatus,
    ClaimType,
    FraudSeverity,
    Role,
    TenantType,
    UserStatus,
    Verdict,
)


class Tenant(Base):
    __tablename__ = "Tenant"

    id: Mapped[str] = mapped_column("id", Text, primary_key=True, default=gen_cuid)
    type: Mapped[TenantType] = mapped_column("type", pg_enum(TenantType, "TenantType"))
    name: Mapped[str] = mapped_column("name", Text)
    created_at: Mapped[datetime] = mapped_column("createdAt", default=utcnow)

    users: Mapped[list["User"]] = relationship(back_populates="tenant")
    activity_logs: Mapped[list["ActivityLog"]] = relationship(back_populates="tenant")
    policies: Mapped[list["Policy"]] = relationship(back_populates="insurer")
    patients: Mapped[list["Patient"]] = relationship(back_populates="insurer")
    wards: Mapped[list["Ward"]] = relationship(back_populates="hospital")
    beds: Mapped[list["Bed"]] = relationship(back_populates="hospital")
    admissions: Mapped[list["Admission"]] = relationship(back_populates="hospital")


class User(Base):
    __tablename__ = "User"

    id: Mapped[str] = mapped_column("id", Text, primary_key=True, default=gen_cuid)
    email: Mapped[str] = mapped_column("email", Text, unique=True)
    name: Mapped[str | None] = mapped_column("name", Text, nullable=True)
    password_hash: Mapped[str] = mapped_column("passwordHash", Text)
    role: Mapped[Role] = mapped_column("role", pg_enum(Role, "Role"))
    status: Mapped[UserStatus] = mapped_column(
        "status", pg_enum(UserStatus, "UserStatus"), default=UserStatus.ACTIVE
    )
    tenant_id: Mapped[str | None] = mapped_column(
        "tenantId", ForeignKey("Tenant.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column("createdAt", default=utcnow)

    tenant: Mapped["Tenant | None"] = relationship(back_populates="users")


class ActivityLog(Base):
    __tablename__ = "ActivityLog"

    id: Mapped[str] = mapped_column("id", Text, primary_key=True, default=gen_cuid)
    tenant_id: Mapped[str | None] = mapped_column(
        "tenantId", ForeignKey("Tenant.id"), nullable=True
    )
    actor_id: Mapped[str | None] = mapped_column(
        "actorId", ForeignKey("User.id"), nullable=True
    )
    action: Mapped[str] = mapped_column("action", Text)
    detail: Mapped[str | None] = mapped_column("detail", Text, nullable=True)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column("createdAt", default=utcnow)

    tenant: Mapped["Tenant | None"] = relationship(back_populates="activity_logs")
    actor: Mapped["User | None"] = relationship()


class Policy(Base):
    __tablename__ = "Policy"

    id: Mapped[str] = mapped_column("id", Text, primary_key=True, default=gen_cuid)
    insurer_tenant_id: Mapped[str] = mapped_column(
        "insurerTenantId", ForeignKey("Tenant.id")
    )
    name: Mapped[str] = mapped_column("name", Text)
    plan_code: Mapped[str] = mapped_column("planCode", Text)
    sum_insured_paise: Mapped[int] = mapped_column("sumInsuredPaise", Integer)
    room_rent_cap_per_day_paise: Mapped[int | None] = mapped_column(
        "roomRentCapPerDayPaise", Integer, nullable=True
    )
    copay_pct: Mapped[int] = mapped_column("copayPct", Integer, default=0)
    waiting_period_days: Mapped[int] = mapped_column("waitingPeriodDays", Integer, default=0)
    covered_procedures: Mapped[list[str]] = mapped_column(
        "coveredProcedures", ARRAY(Text), default=list
    )
    exclusions: Mapped[list[str]] = mapped_column("exclusions", ARRAY(Text), default=list)
    created_at: Mapped[datetime] = mapped_column("createdAt", default=utcnow)

    insurer: Mapped["Tenant"] = relationship(back_populates="policies")
    patients: Mapped[list["Patient"]] = relationship(back_populates="policy")
    claims: Mapped[list["Claim"]] = relationship(back_populates="policy")


class Patient(Base):
    __tablename__ = "Patient"

    id: Mapped[str] = mapped_column("id", Text, primary_key=True, default=gen_cuid)
    insurer_tenant_id: Mapped[str] = mapped_column(
        "insurerTenantId", ForeignKey("Tenant.id")
    )
    policy_id: Mapped[str | None] = mapped_column(
        "policyId", ForeignKey("Policy.id"), nullable=True
    )
    member_id: Mapped[str] = mapped_column("memberId", Text, unique=True)
    name: Mapped[str] = mapped_column("name", Text)
    age: Mapped[int] = mapped_column("age", Integer)
    gender: Mapped[str] = mapped_column("gender", Text)
    phone: Mapped[str | None] = mapped_column("phone", Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column("createdAt", default=utcnow)

    insurer: Mapped["Tenant"] = relationship(back_populates="patients")
    policy: Mapped["Policy | None"] = relationship(back_populates="patients")
    admissions: Mapped[list["Admission"]] = relationship(back_populates="patient")
    claims: Mapped[list["Claim"]] = relationship(back_populates="patient")


class Ward(Base):
    __tablename__ = "Ward"

    id: Mapped[str] = mapped_column("id", Text, primary_key=True, default=gen_cuid)
    hospital_tenant_id: Mapped[str] = mapped_column(
        "hospitalTenantId", ForeignKey("Tenant.id")
    )
    name: Mapped[str] = mapped_column("name", Text)
    created_at: Mapped[datetime] = mapped_column("createdAt", default=utcnow)

    hospital: Mapped["Tenant"] = relationship(back_populates="wards")
    beds: Mapped[list["Bed"]] = relationship(back_populates="ward")


class Bed(Base):
    __tablename__ = "Bed"

    id: Mapped[str] = mapped_column("id", Text, primary_key=True, default=gen_cuid)
    hospital_tenant_id: Mapped[str] = mapped_column(
        "hospitalTenantId", ForeignKey("Tenant.id")
    )
    ward_id: Mapped[str] = mapped_column("wardId", ForeignKey("Ward.id"))
    label: Mapped[str] = mapped_column("label", Text)
    status: Mapped[BedStatus] = mapped_column(
        "status", pg_enum(BedStatus, "BedStatus"), default=BedStatus.AVAILABLE
    )
    created_at: Mapped[datetime] = mapped_column("createdAt", default=utcnow)

    hospital: Mapped["Tenant"] = relationship(back_populates="beds")
    ward: Mapped["Ward"] = relationship(back_populates="beds")
    admissions: Mapped[list["Admission"]] = relationship(back_populates="bed")


class Admission(Base):
    __tablename__ = "Admission"

    id: Mapped[str] = mapped_column("id", Text, primary_key=True, default=gen_cuid)
    hospital_tenant_id: Mapped[str] = mapped_column(
        "hospitalTenantId", ForeignKey("Tenant.id")
    )
    bed_id: Mapped[str | None] = mapped_column(
        "bedId", ForeignKey("Bed.id"), nullable=True
    )
    patient_id: Mapped[str | None] = mapped_column(
        "patientId", ForeignKey("Patient.id"), nullable=True
    )
    patient_name: Mapped[str] = mapped_column("patientName", Text)
    patient_age: Mapped[int] = mapped_column("patientAge", Integer)
    patient_gender: Mapped[str] = mapped_column("patientGender", Text)
    diagnosis: Mapped[str] = mapped_column("diagnosis", Text)
    procedure: Mapped[str] = mapped_column("procedure", Text)
    status: Mapped[AdmissionStatus] = mapped_column(
        "status", pg_enum(AdmissionStatus, "AdmissionStatus"), default=AdmissionStatus.ADMITTED
    )
    admitted_at: Mapped[datetime] = mapped_column("admittedAt", default=utcnow)
    discharged_at: Mapped[datetime | None] = mapped_column(
        "dischargedAt", nullable=True
    )
    created_at: Mapped[datetime] = mapped_column("createdAt", default=utcnow)

    hospital: Mapped["Tenant"] = relationship(back_populates="admissions")
    bed: Mapped["Bed | None"] = relationship(back_populates="admissions")
    patient: Mapped["Patient | None"] = relationship(back_populates="admissions")
    claim: Mapped["Claim | None"] = relationship(back_populates="admission")


class Claim(Base):
    __tablename__ = "Claim"

    id: Mapped[str] = mapped_column("id", Text, primary_key=True, default=gen_cuid)
    claim_number: Mapped[str] = mapped_column("claimNumber", Text, unique=True)
    type: Mapped[ClaimType] = mapped_column(
        "type", pg_enum(ClaimType, "ClaimType"), default=ClaimType.CASHLESS
    )

    hospital_tenant_id: Mapped[str] = mapped_column(
        "hospitalTenantId", ForeignKey("Tenant.id")
    )
    insurer_tenant_id: Mapped[str] = mapped_column(
        "insurerTenantId", ForeignKey("Tenant.id")
    )
    policy_id: Mapped[str | None] = mapped_column(
        "policyId", ForeignKey("Policy.id"), nullable=True
    )
    patient_id: Mapped[str | None] = mapped_column(
        "patientId", ForeignKey("Patient.id"), nullable=True
    )
    admission_id: Mapped[str | None] = mapped_column(
        "admissionId", ForeignKey("Admission.id"), nullable=True, unique=True
    )

    patient_name: Mapped[str] = mapped_column("patientName", Text)
    patient_age: Mapped[int] = mapped_column("patientAge", Integer)
    patient_gender: Mapped[str] = mapped_column("patientGender", Text)
    diagnosis: Mapped[str] = mapped_column("diagnosis", Text)
    procedure: Mapped[str] = mapped_column("procedure", Text)
    admitted_at: Mapped[datetime] = mapped_column("admittedAt")
    discharged_at: Mapped[datetime] = mapped_column("dischargedAt")
    length_of_stay_days: Mapped[int] = mapped_column("lengthOfStayDays", Integer)
    sum_insured_paise: Mapped[int] = mapped_column("sumInsuredPaise", Integer)
    billed_paise: Mapped[int] = mapped_column("billedPaise", Integer)
    line_items: Mapped[list | dict] = mapped_column("lineItems", JSONB)

    status: Mapped[ClaimStatus] = mapped_column(
        "status", pg_enum(ClaimStatus, "ClaimStatus"), default=ClaimStatus.SUBMITTED
    )

    verdict: Mapped[Verdict | None] = mapped_column(
        "verdict", pg_enum(Verdict, "Verdict"), nullable=True
    )
    approved_amount_paise: Mapped[int | None] = mapped_column(
        "approvedAmountPaise", Integer, nullable=True
    )
    confidence: Mapped[float | None] = mapped_column("confidence", Float, nullable=True)
    rationale: Mapped[str | None] = mapped_column("rationale", Text, nullable=True)
    cited_clause_refs: Mapped[list[str]] = mapped_column(
        "citedClauseRefs", ARRAY(Text), default=list
    )
    ai_model: Mapped[str | None] = mapped_column("aiModel", Text, nullable=True)
    ai_latency_ms: Mapped[int | None] = mapped_column("aiLatencyMs", Integer, nullable=True)
    tat_seconds: Mapped[int | None] = mapped_column("tatSeconds", Integer, nullable=True)

    submitted_by_id: Mapped[str | None] = mapped_column(
        "submittedById", ForeignKey("User.id"), nullable=True
    )
    overridden_by_id: Mapped[str | None] = mapped_column(
        "overriddenById", ForeignKey("User.id"), nullable=True
    )
    override_note: Mapped[str | None] = mapped_column("overrideNote", Text, nullable=True)
    overridden_at: Mapped[datetime | None] = mapped_column("overriddenAt", nullable=True)

    submitted_at: Mapped[datetime] = mapped_column("submittedAt", default=utcnow)
    decided_at: Mapped[datetime | None] = mapped_column("decidedAt", nullable=True)
    settled_at: Mapped[datetime | None] = mapped_column("settledAt", nullable=True)

    hospital: Mapped["Tenant"] = relationship(foreign_keys=[hospital_tenant_id])
    insurer: Mapped["Tenant"] = relationship(foreign_keys=[insurer_tenant_id])
    policy: Mapped["Policy | None"] = relationship(back_populates="claims")
    patient: Mapped["Patient | None"] = relationship(back_populates="claims")
    admission: Mapped["Admission | None"] = relationship(back_populates="claim")
    submitted_by: Mapped["User | None"] = relationship(foreign_keys=[submitted_by_id])
    overridden_by: Mapped["User | None"] = relationship(foreign_keys=[overridden_by_id])
    decisions: Mapped[list["Decision"]] = relationship(
        back_populates="claim", cascade="all, delete-orphan"
    )
    fraud_flags: Mapped[list["FraudFlag"]] = relationship(
        back_populates="claim", cascade="all, delete-orphan"
    )
    events: Mapped[list["ClaimEvent"]] = relationship(
        back_populates="claim", cascade="all, delete-orphan"
    )


class Decision(Base):
    __tablename__ = "Decision"

    id: Mapped[str] = mapped_column("id", Text, primary_key=True, default=gen_cuid)
    claim_id: Mapped[str] = mapped_column(
        "claimId", ForeignKey("Claim.id", ondelete="CASCADE")
    )
    verdict: Mapped[Verdict] = mapped_column("verdict", pg_enum(Verdict, "Verdict"))
    approved_amount_paise: Mapped[int | None] = mapped_column(
        "approvedAmountPaise", Integer, nullable=True
    )
    confidence: Mapped[float] = mapped_column("confidence", Float)
    rationale: Mapped[str] = mapped_column("rationale", Text)
    cited_clause_refs: Mapped[list[str]] = mapped_column(
        "citedClauseRefs", ARRAY(Text), default=list
    )
    model: Mapped[str] = mapped_column("model", Text)
    latency_ms: Mapped[int] = mapped_column("latencyMs", Integer)
    created_at: Mapped[datetime] = mapped_column("createdAt", default=utcnow)

    claim: Mapped["Claim"] = relationship(back_populates="decisions")


class FraudFlag(Base):
    __tablename__ = "FraudFlag"

    id: Mapped[str] = mapped_column("id", Text, primary_key=True, default=gen_cuid)
    claim_id: Mapped[str] = mapped_column(
        "claimId", ForeignKey("Claim.id", ondelete="CASCADE")
    )
    signal: Mapped[str] = mapped_column("signal", Text)
    severity: Mapped[FraudSeverity] = mapped_column(
        "severity", pg_enum(FraudSeverity, "FraudSeverity")
    )
    detail: Mapped[str] = mapped_column("detail", Text)
    created_at: Mapped[datetime] = mapped_column("createdAt", default=utcnow)

    claim: Mapped["Claim"] = relationship(back_populates="fraud_flags")


class ClaimEvent(Base):
    __tablename__ = "ClaimEvent"

    id: Mapped[str] = mapped_column("id", Text, primary_key=True, default=gen_cuid)
    claim_id: Mapped[str] = mapped_column(
        "claimId", ForeignKey("Claim.id", ondelete="CASCADE")
    )
    type: Mapped[ClaimEventType] = mapped_column(
        "type", pg_enum(ClaimEventType, "ClaimEventType")
    )
    message: Mapped[str] = mapped_column("message", Text)
    actor_id: Mapped[str | None] = mapped_column(
        "actorId", ForeignKey("User.id"), nullable=True
    )
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column("createdAt", default=utcnow)

    claim: Mapped["Claim"] = relationship(back_populates="events")
    actor: Mapped["User | None"] = relationship()
