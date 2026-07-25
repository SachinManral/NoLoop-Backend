"""Admin (platform god-mode) request bodies."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

_StaffOrAdminRole = Literal[
    "HOSPITAL_ADMIN", "INSURER_ADMIN", "HOSPITAL_STAFF", "INSURER_ADJUDICATOR"
]


class CreateOrgBody(BaseModel):
    type: Literal["HOSPITAL", "INSURER"]
    name: str = Field(min_length=2)
    adminName: str = Field(min_length=2)
    password: str | None = Field(default=None, min_length=8)


class AdminCreateUserBody(BaseModel):
    tenantId: str
    name: str = Field(min_length=2)
    role: _StaffOrAdminRole | None = None
    password: str | None = Field(default=None, min_length=8)


class UpdateUserBody(BaseModel):
    name: str | None = Field(default=None, min_length=2)
    role: _StaffOrAdminRole | None = None


class ResetPasswordBody(BaseModel):
    password: str | None = Field(default=None, min_length=8)
