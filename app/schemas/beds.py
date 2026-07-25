"""Bed/admission request bodies."""

from __future__ import annotations

from pydantic import BaseModel, Field


class AdmitBody(BaseModel):
    patientName: str = Field(min_length=2)
    patientAge: int = Field(ge=0)
    patientGender: str
    diagnosis: str = Field(min_length=2)
    procedure: str = Field(min_length=2)
    wardId: str | None = None
    memberId: str | None = None
