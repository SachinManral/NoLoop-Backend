"""String enums mirroring the Prisma/Postgres enums exactly (value == name).

Sprint 2: added intermediate workflow states to ClaimStatus and corresponding
event types to ClaimEventType for the formal state-machine orchestrator.
"""

from __future__ import annotations

import enum


class TenantType(str, enum.Enum):
    INSURER = "INSURER"
    HOSPITAL = "HOSPITAL"


class Role(str, enum.Enum):
    PLATFORM_ADMIN = "PLATFORM_ADMIN"
    HOSPITAL_ADMIN = "HOSPITAL_ADMIN"
    INSURER_ADMIN = "INSURER_ADMIN"
    HOSPITAL_STAFF = "HOSPITAL_STAFF"
    INSURER_ADJUDICATOR = "INSURER_ADJUDICATOR"
    PATIENT = "PATIENT"


class UserStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    REVOKED = "REVOKED"


class ClaimType(str, enum.Enum):
    CASHLESS = "CASHLESS"
    REIMBURSEMENT = "REIMBURSEMENT"


class Verdict(str, enum.Enum):
    APPROVE = "APPROVE"
    DENY = "DENY"
    QUERY = "QUERY"


class ClaimStatus(str, enum.Enum):
    SUBMITTED = "SUBMITTED"
    PROCESSING = "PROCESSING"              # legacy — kept for backward compat
    VALIDATED = "VALIDATED"                 # Sprint 2: Query-Proofing passed
    POLICY_CHECK = "POLICY_CHECK"           # Sprint 2: rules engine evaluating
    FRAUD_CHECK = "FRAUD_CHECK"             # Sprint 2: fraud scoring in progress
    RETURNED_TO_HOSPITAL = "RETURNED_TO_HOSPITAL"  # Sprint 2: returned for docs
    APPROVED = "APPROVED"
    DENIED = "DENIED"
    QUERIED = "QUERIED"
    UNDER_REVIEW = "UNDER_REVIEW"
    SETTLED = "SETTLED"


class FraudSeverity(str, enum.Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class BedStatus(str, enum.Enum):
    AVAILABLE = "AVAILABLE"
    OCCUPIED = "OCCUPIED"
    MAINTENANCE = "MAINTENANCE"


class AdmissionStatus(str, enum.Enum):
    ADMITTED = "ADMITTED"
    DISCHARGED = "DISCHARGED"


class ClaimEventType(str, enum.Enum):
    SUBMITTED = "SUBMITTED"
    AI_STARTED = "AI_STARTED"
    AI_DECISION = "AI_DECISION"
    FRAUD_FLAGGED = "FRAUD_FLAGGED"
    QUERY_RAISED = "QUERY_RAISED"
    OVERRIDDEN = "OVERRIDDEN"
    SETTLED = "SETTLED"
    NOTE = "NOTE"
    # Sprint 2: workflow orchestrator events
    VALIDATED = "VALIDATED"
    POLICY_CHECKED = "POLICY_CHECKED"
    FRAUD_CHECKED = "FRAUD_CHECKED"
    REVIEW_ASSIGNED = "REVIEW_ASSIGNED"
    RESUBMITTED = "RESUBMITTED"
    AUTO_APPROVED = "AUTO_APPROVED"
