# NoLoop backend (Python / FastAPI)

A faithful Python rewrite of the NestJS API. It is **wire-compatible** with the
original: same routes, same camelCase JSON, the same JWT format (HS256 + shared
`JWT_SECRET`), bcrypt password compatibility, and the same Postgres/Supabase
database (no schema changes). The `web` (:3000) and `admin` (:3001) frontends and
the `ai` engine (:8000) run unchanged against it on **:4000**.

## Architecture

```
app/
  main.py            FastAPI app: CORS, error handlers, router mounting
  config.py          env settings (DATABASE_URL, JWT_SECRET, AI_ENGINE_URL, …)
  db.py              async SQLAlchemy engine + session (asyncpg)
  models/            ORM mapped 1:1 onto the existing Prisma tables (camelCase)
  schemas/           Pydantic request bodies + the AI-engine contract
  core/              security (JWT/bcrypt), deps (guards), errors, slug, money
  services/          business logic (one module per domain) + serializers
  routers/           thin HTTP layer (the "controllers")
scripts/             create_platform_admin.py, seed_demo.py, generate_synthetic_claims.py
```

Layering is `routers → services → models`, mirroring NestJS controller/service/module.

## Setup

```bash
cd noloop-app/backend-py
python -m venv .venv && source .venv/bin/activate   # or: py -m venv .venv
pip install -e .                                    # installs from pyproject.toml

cp .env.example .env
# Fill .env with the SAME values your NestJS backend used — crucially
# DATABASE_URL and JWT_SECRET — so the DB and existing tokens keep working.
```

## Run

```bash
./start.ps1               # uvicorn on :4000 (honours $API_PORT)
# or:
uvicorn app.main:app --port 4000 --reload
```

Health check (proves DB connectivity): `GET http://localhost:4000/health` →
`{"status":"ok","db":"connected"}`.

Interactive API docs: `http://localhost:4000/docs`.

## Scripts

```bash
python scripts/create_platform_admin.py admin@noloop.in 'StrongPass123'
python scripts/seed_demo.py                 # honours $AI_ENGINE_URL
python scripts/generate_synthetic_claims.py 20 42
```

## Relationship to the old backend

The original NestJS backend still lives in `../backend/` untouched. Run whichever
you like on :4000 — both speak the same protocol against the same database. Once
you're satisfied with parity, the old one can be removed.
