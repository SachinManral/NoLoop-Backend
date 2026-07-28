"""Unit tests for Multi-Tenancy & RBAC Security Guards."""

from app.core.deps import AuthUser
from app.models.enums import Role
from app.services.claims_service import _scope_where


def test_platform_admin_global_scope():
    user = AuthUser(
        id="usr_admin",
        email="admin@noloop.in",
        name="Admin",
        role=Role.PLATFORM_ADMIN.value,
        tenant_id=None,
    )
    where_clause = _scope_where(user)
    # Platform admin sees all records (empty condition: None)
    assert where_clause is None


def test_hospital_tenant_scoping():
    user = AuthUser(
        id="usr_hosp",
        email="staff@apollo.com",
        name="Staff",
        role=Role.HOSPITAL_STAFF.value,
        tenant_id="tnt_apollo_01",
    )
    where_clause = _scope_where(user)
    # Hospital user filtered strictly by hospitalTenantId
    assert where_clause is not None
    assert "hospitalTenantId" in str(where_clause) or "hospital_tenant_id" in str(where_clause)


def test_insurer_tenant_scoping():
    user = AuthUser(
        id="usr_ins",
        email="doctor@starhealth.com",
        name="Doctor",
        role=Role.INSURER_ADJUDICATOR.value,
        tenant_id="tnt_star_01",
    )
    where_clause = _scope_where(user)
    # Insurer user filtered strictly by insurerTenantId
    assert where_clause is not None
    assert "insurerTenantId" in str(where_clause) or "insurer_tenant_id" in str(where_clause)


def test_tpa_tenant_scoping():
    user = AuthUser(
        id="usr_tpa",
        email="reviewer@medassist.com",
        name="TPA Reviewer",
        role=Role.TPA_REVIEWER.value,
        tenant_id="tnt_star_01",
    )
    where_clause = _scope_where(user)
    # TPA user scoped to their insurer tenant exactly like insurer staff
    assert where_clause is not None
    assert "insurerTenantId" in str(where_clause) or "insurer_tenant_id" in str(where_clause)


def test_unknown_role_sees_nothing():
    user = AuthUser(
        id="usr_x",
        email="ghost@nowhere.com",
        name="Ghost",
        role="NOT_A_ROLE",
        tenant_id=None,
    )
    where_clause = _scope_where(user)
    # Unknown roles match no records (Claim.id == "__none__")
    assert where_clause is not None
    assert "id" in str(where_clause)


def test_patient_scoping():
    user = AuthUser(
        id="usr_patient_01",
        email="patient@gmail.com",
        name="Patient",
        role=Role.PATIENT.value,
        tenant_id="tnt_patient_01",
    )
    where_clause = _scope_where(user)
    assert where_clause is not None
    assert "patientId" in str(where_clause) or "patient_id" in str(where_clause)



