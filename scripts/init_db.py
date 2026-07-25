"""Bootstrap a fresh Postgres database with the NoLoop schema.

The ORM models (app/models) are mapped onto a schema the original Prisma
backend used to create, so they intentionally do NOT create the Postgres enum
types themselves (``create_type=False``). On a brand-new database there is
nothing to map onto yet, so this script:

  1. creates the native Postgres ENUM types (idempotently), then
  2. creates every table from the SQLAlchemy metadata.

Run it once against an empty database before seeding:

    python scripts/init_db.py

It is safe to re-run: existing enum types and tables are skipped.
"""

from __future__ import annotations

import asyncio

from sqlalchemy import text

from app.db import engine
from app.models import Base
from app.models.enums import (
    AdmissionStatus,
    BedStatus,
    ClaimEventType,
    ClaimStatus,
    ClaimType,
    FraudSeverity,
    Role,
    TenantType,
    UserStatus,
    Verdict,
)

# Each Postgres enum type is named after its Python enum class (matching the
# `name=` passed to pg_enum() in app/models/base.py). value == name for all.
ENUMS = [
    TenantType,
    Role,
    UserStatus,
    ClaimType,
    Verdict,
    ClaimStatus,
    FraudSeverity,
    BedStatus,
    AdmissionStatus,
    ClaimEventType,
]


def _create_enum_sql(enum_cls) -> str:
    """CREATE TYPE ... AS ENUM, guarded so re-runs don't error."""
    type_name = enum_cls.__name__
    values = ", ".join(f"'{m.value}'" for m in enum_cls)
    return (
        "DO $$ BEGIN\n"
        f"  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = '{type_name}') THEN\n"
        f'    CREATE TYPE "{type_name}" AS ENUM ({values});\n'
        "  END IF;\n"
        "END $$;"
    )


async def main() -> None:
    async with engine.begin() as conn:
        print("Creating enum types…")
        for enum_cls in ENUMS:
            await conn.execute(text(_create_enum_sql(enum_cls)))
            print(f"  ✓ {enum_cls.__name__}")

        print("Creating tables…")
        await conn.run_sync(Base.metadata.create_all)

    await engine.dispose()
    print("✅ Schema ready. Next: python scripts/seed_demo.py")


if __name__ == "__main__":
    asyncio.run(main())
