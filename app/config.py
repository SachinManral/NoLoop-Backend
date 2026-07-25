"""Application configuration, loaded from the environment / `.env`.

Mirrors the env contract of the NestJS backend so the two are drop-in
interchangeable: same DATABASE_URL, JWT_SECRET, AI_ENGINE_URL, API_PORT.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # Database — the pooled Supabase connection (same as Prisma's DATABASE_URL).
    database_url: str = "postgresql://postgres:postgres@localhost:5432/noloop"
    direct_url: str | None = None

    # Auth — must match the NestJS backend for cross-compatible tokens.
    jwt_secret: str = "dev-secret-change-me"
    jwt_expires_in: str = "7d"

    # The Python AI adjudication engine.
    ai_engine_url: str = "http://localhost:8000"

    # HTTP server.
    api_port: int = 4000


settings = Settings()
