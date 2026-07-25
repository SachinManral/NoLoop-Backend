"""Claim submit / override / respond request bodies."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class LineItemBody(BaseModel):
    desc: str = Field(min_length=2)
    amountPaise: int = Field(ge=0)


class SubmitClaimBody(BaseModel):
    insurerTenantId: str
    type: Literal["CASHLESS", "REIMBURSEMENT"] | None = None
    patientName: str = Field(min_length=2)
    patientAge: int = Field(ge=0)
    patientGender: str
    memberId: str | None = None
    diagnosis: str = Field(min_length=2)
    procedure: str = Field(min_length=2)
    admittedAt: str
    dischargedAt: str
    lineItems: list[LineItemBody]
    totalPaise: int | None = Field(default=None, ge=0)
    admissionId: str | None = None


class OverrideClaimBody(BaseModel):
    verdict: Literal["APPROVE", "DENY", "QUERY"]
    approvedAmountPaise: int | None = Field(default=None, ge=0)
    note: str = Field(min_length=3)
    settle: bool | None = None


class RespondBody(BaseModel):
    message: str = ""
