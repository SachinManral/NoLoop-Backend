"""NoLoop backend — FastAPI application entry point.

Mirrors the NestJS bootstrap: permissive CORS (reflect origin + credentials),
NestJS-shaped error bodies, and the same route surface on port 4000.
Automatically initializes Postgres schema on startup.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.core.errors import register_error_handlers
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
from app.routers import (
    admin,
    auth,
    beds,
    catalog,
    claims,
    health,
    metrics,
    org,
    patients,
    track,
    whatsapp,
    workflow,
)

log = logging.getLogger("backend_main")


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
    type_name = enum_cls.__name__
    values = ", ".join(f"'{m.value}'" for m in enum_cls)
    return (
        "DO $$ BEGIN\n"
        f"  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = '{type_name}') THEN\n"
        f'    CREATE TYPE "{type_name}" AS ENUM ({values});\n'
        "  END IF;\n"
        "END $$;"
    )


ALTER_PATIENT_SQL = """
DO $$ BEGIN
    ALTER TABLE "Patient" ADD COLUMN IF NOT EXISTS "healthId" TEXT;
    ALTER TABLE "Patient" ADD COLUMN IF NOT EXISTS "aadhaarHash" TEXT;
    ALTER TABLE "Patient" ADD COLUMN IF NOT EXISTS "aadhaarLast4" TEXT;
END $$;
"""


async def init_postgres_schema():
    """Ensure all PostgreSQL enum types, tables, and patient columns exist on startup."""
    try:
        async with engine.begin() as conn:
            for enum_cls in ENUMS:
                await conn.execute(text(_create_enum_sql(enum_cls)))
            await conn.run_sync(Base.metadata.create_all)
            await conn.execute(text(ALTER_PATIENT_SQL))
        log.info("PostgreSQL schema initialized successfully.")
    except Exception as err:
        log.warning("Postgres schema init note: %s", err)



@asynccontextmanager
async def lifespan(_: FastAPI):
    await init_postgres_schema()
    yield
    await engine.dispose()


app = FastAPI(title="NoLoop backend", version="0.0.1", lifespan=lifespan)

# Allow the web + admin frontends (different origins) to call the API with credentials.
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=".*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_error_handlers(app)

for module in (auth, admin, org, patients, claims, track, beds, metrics, catalog, health, whatsapp, workflow):
    app.include_router(module.router)

