"""JWT + password helpers, wire-compatible with the NestJS backend.

@nestjs/jwt signs HS256 with `JWT_SECRET` and a `{ sub, role, tenantId }`
payload plus `iat`/`exp`. We sign/verify the same way with the same secret, so
tokens issued by either backend are mutually valid. Passwords use bcrypt at
cost 10 (bcryptjs hashes verify directly).
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.config import settings

_ALGO = "HS256"

# "7d" / "12h" / "30m" / "3600" -> seconds.
_DURATION = re.compile(r"^(\d+)\s*([smhd])?$")
_UNIT_SECONDS = {"s": 1, "m": 60, "h": 3600, "d": 86400}


def _expires_seconds(spec: str) -> int:
    m = _DURATION.match(spec.strip())
    if not m:
        return 7 * 86400
    value, unit = int(m.group(1)), m.group(2) or "s"
    return value * _UNIT_SECONDS[unit]


def sign_token(sub: str, role: str, tenant_id: str | None) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": sub,
        "role": role,
        "tenantId": tenant_id,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=_expires_seconds(settings.jwt_expires_in))).timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=_ALGO)


def verify_token(token: str) -> dict:
    """Decode + verify a bearer token; raises jwt exceptions on failure."""
    return jwt.decode(token, settings.jwt_secret, algorithms=[_ALGO])


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt(rounds=10)).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False
