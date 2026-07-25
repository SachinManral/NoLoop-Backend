"""Org-admin self-service request bodies."""

from __future__ import annotations

from pydantic import BaseModel, Field


class CreateEmployeeBody(BaseModel):
    name: str = Field(min_length=2)
    password: str = Field(min_length=8)
