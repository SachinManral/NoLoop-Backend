"""AI-engine contract — mirrors ai/app/schemas.py and backend ai.types.ts.

These models are (de)serialised verbatim to/from the Python AI engine at
``$AI_ENGINE_URL``; the camelCase field names are the wire format.
"""

from __future__ import annotations

from pydantic import BaseModel


class AiLineItem(BaseModel):
    desc: str
    amountPaise: int


class AiPolicy(BaseModel):
    policyNo: str | None = None
    sumInsuredPaise: int
    roomRentCapPerDayPaise: int | None = None
    copayPct: int = 0
    coveredProcedures: list[str] = []
    exclusions: list[str] = []


class AiAdmission(BaseModel):
    admittedAt: str | None = None
    dischargedAt: str | None = None
    lengthOfStayDays: int
    procedure: str
    diagnosis: str | None = None


class AiBill(BaseModel):
    lineItems: list[AiLineItem]
    totalPaise: int


class ClaimPacket(BaseModel):
    ref: str
    type: str | None = None
    hospital: str | None = None
    insurer: str | None = None
    policy: AiPolicy
    admission: AiAdmission
    bill: AiBill
    dischargeSummary: str | None = None


class AiFraudFlag(BaseModel):
    signal: str
    severity: str
    detail: str


class AiDeduction(BaseModel):
    label: str
    amountPaise: int


class AiDecision(BaseModel):
    ref: str
    verdict: str
    rationale: str
    citedClauseRefs: list[str] = []
    fraudFlags: list[AiFraudFlag] = []
    approvedAmountPaise: int | None = None
    deductions: list[AiDeduction] = []
    confidence: float
    model: str
