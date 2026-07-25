"""Declarative base and shared column helpers.

Prisma names tables after the model (PascalCase) and columns after the field
(camelCase). SQLAlchemy quotes mixed-case identifiers, so using those names
verbatim maps us straight onto the existing schema with zero migrations.
"""

from __future__ import annotations

import enum
from datetime import datetime, timezone

import cuid
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


def gen_cuid() -> str:
    """Prisma uses cuid() for ids; match the format for new rows."""
    return cuid.cuid()


def utcnow() -> datetime:
    """Naive UTC timestamp, matching Prisma's `@default(now())` storage."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def pg_enum(py_enum: type[enum.Enum], name: str) -> SAEnum:
    """Bind to an existing native Postgres enum (created by Prisma).

    `create_type=False` stops SQLAlchemy from trying to re-create it, and
    `values_callable` persists the member *value* (we keep value == name).
    """
    return SAEnum(
        py_enum,
        name=name,
        create_type=False,
        native_enum=True,
        values_callable=lambda e: [m.value for m in e],
    )
