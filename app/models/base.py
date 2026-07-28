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


def gen_id(prefix: str = "") -> str:
    """Generate clean, self-describing IDs (e.g., clm_..., tnt_..., pat_...)."""
    c_val = cuid.cuid()
    return f"{prefix}_{c_val}" if prefix else c_val


def gen_cuid() -> str:
    """Prisma uses cuid() for ids; match the format for new rows."""
    return gen_id()


def gen_claim_id() -> str:
    """Generate a clean, self-describing claim ID with clm_ prefix."""
    return gen_id("clm")


def gen_health_id(aadhaar: str | None = None) -> str:
    """Generate a 14-digit lifetime ABHA-compatible Health ID (NL-HID-XXXX-XXXX-XXXX)."""
    import hashlib
    import random

    if aadhaar and len(aadhaar.strip()) >= 4:
        clean = "".join(c for c in aadhaar if c.isdigit())
        h = hashlib.sha256(clean.encode("utf-8")).hexdigest()
        n1 = int(h[0:4], 16) % 9000 + 1000
        n2 = int(h[4:8], 16) % 9000 + 1000
        n3 = int(h[8:12], 16) % 9000 + 1000
        return f"NL-HID-{n1}-{n2}-{n3}"

    n1 = random.randint(1000, 9999)
    n2 = random.randint(1000, 9999)
    n3 = random.randint(1000, 9999)
    return f"NL-HID-{n1}-{n2}-{n3}"





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
