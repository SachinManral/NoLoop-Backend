"""Tenant Subdomain & White-Label Middleware for NoLoop Platform.

Sprint 4: Resolves white-label tenant subdomains (e.g. apollo.noloop.in -> tenant 'apollo')
from request Host headers and injects tenant isolation context into request state.
"""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class TenantSubdomainMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        host = request.headers.get("host", "").split(":")[0].lower()
        parts = host.split(".")

        tenant_slug = None
        # E.g. apollo.noloop.in or starhealth.noloop.in -> parts = ['apollo', 'noloop', 'in']
        if len(parts) >= 3 and parts[0] not in ("www", "api", "app", "localhost"):
            tenant_slug = parts[0]

        request.state.tenant_slug = tenant_slug
        response = await call_next(request)

        if tenant_slug:
            response.headers["X-NoLoop-Tenant"] = tenant_slug

        return response
