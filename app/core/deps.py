"""Auth dependencies — the FastAPI equivalents of JwtAuthGuard + RolesGuard.

`get_current_user` verifies the Bearer token and returns the decoded payload
(`{ sub, role, tenantId, iat, exp }`), exactly what NestJS attaches to
`req.user`. `require_roles(...)` layers on the role check.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

import jwt
from fastapi import Depends, Request

from app.core.errors import forbidden, unauthorized
from app.core.security import verify_token

# An authenticated principal: the decoded JWT payload.
AuthUser = dict


async def get_current_user(request: Request) -> AuthUser:
    header = request.headers.get("authorization")
    if not header or not header.startswith("Bearer "):
        raise unauthorized("Missing bearer token")
    try:
        return verify_token(header[7:])
    except jwt.PyJWTError:
        raise unauthorized("Invalid or expired token")


def require_roles(*roles: str) -> Callable[[AuthUser], Awaitable[AuthUser]]:
    """Dependency factory: 401 if unauthenticated, 403 if role not allowed."""

    async def _guard(user: AuthUser = Depends(get_current_user)) -> AuthUser:
        if roles and user.get("role") not in roles:
            raise forbidden("Insufficient role")
        return user

    return _guard
