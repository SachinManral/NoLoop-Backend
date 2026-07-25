"""Auth request bodies (field names match the JSON the frontends send)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, EmailStr, Field


class SignupBody(BaseModel):
    orgName: str = Field(min_length=2)
    orgType: Literal["HOSPITAL", "INSURER"]
    adminName: str = Field(min_length=2)
    password: str = Field(min_length=8)


class LoginBody(BaseModel):
    email: EmailStr
    password: str
