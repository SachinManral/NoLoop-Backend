"""Async database engine + session factory.

The DATABASE_URL is the same Postgres string Prisma uses (often a Supabase
*pooled* connection through pgbouncer). We normalise it for SQLAlchemy/asyncpg:

  * force the ``postgresql+asyncpg`` driver,
  * translate ``sslmode`` into an asyncpg ``ssl`` connect-arg,
  * drop pgbouncer/Prisma-only query params and disable the statement cache
    (required when talking to pgbouncer in transaction-pooling mode).
"""

from __future__ import annotations

import ssl
from collections.abc import AsyncGenerator
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import settings

# Query params Prisma/Supabase add that asyncpg does not understand.
_STRIP_PARAMS = {"pgbouncer", "connection_limit", "sslmode", "schema", "options"}


def _build_engine_args(raw_url: str) -> tuple[str, dict]:
    parts = urlsplit(raw_url)

    scheme = parts.scheme
    if scheme in ("postgres", "postgresql"):
        scheme = "postgresql+asyncpg"

    query = parse_qs(parts.query)
    connect_args: dict = {}

    sslmode = query.get("sslmode", [None])[0]
    if sslmode and sslmode != "disable":
        # Supabase serves a valid cert; a default context verifies it.
        connect_args["ssl"] = ssl.create_default_context()

    # pgbouncer (transaction mode) is incompatible with prepared statements.
    if query.get("pgbouncer", ["false"])[0] == "true":
        connect_args["statement_cache_size"] = 0

    kept = {k: v for k, v in query.items() if k not in _STRIP_PARAMS}
    clean = urlunsplit(
        (scheme, parts.netloc, parts.path, urlencode(kept, doseq=True), parts.fragment)
    )
    return clean, connect_args


_url, _connect_args = _build_engine_args(settings.database_url)

engine = create_async_engine(
    _url,
    connect_args=_connect_args,
    pool_pre_ping=True,
    echo=False,
)

SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency: yields a session and always closes it."""
    async with SessionLocal() as session:
        yield session
