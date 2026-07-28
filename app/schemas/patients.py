"""Patient registration and Aadhaar lookup Pydantic schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field


class RegisterPatientBody(BaseModel):
    insurerTenantId: str
    name: str = Field(min_length=2)
    age: int = Field(ge=0, le=120)
    gender: str
    phone: str | None = None
    aadhaarNumber: str = Field(min_length=12, max_length=12, description="Required 12-digit Aadhaar Card number")
    policyId: str | None = None
    memberId: str | None = None



class AadhaarLookupQuery(BaseModel):
    aadhaarNumber: str = Field(min_length=12, max_length=12, description="12-digit Aadhaar Card number")


class PatientResponse(BaseModel):
    id: str
    healthId: str
    memberId: str
    name: str
    age: int
    gender: str
    phone: str | None = None
    aadhaarLast4: str | None = None
    insurerTenantId: str
    policyId: str | None = None
