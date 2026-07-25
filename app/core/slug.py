"""Email/slug helpers — ports of backend/src/common/slug.ts."""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable

EMAIL_DOMAIN = "noloop.in"

_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def to_dotted(name: str) -> str:
    """"Acme Hospital" -> "acme.hospital" (words joined by dots)."""
    spaced = _NON_ALNUM.sub(" ", name.lower()).strip()
    return ".".join(w for w in spaced.split() if w)


def to_compact(name: str) -> str:
    """"Acme Hospital" -> "acmehospital" (alphanumeric only)."""
    return _NON_ALNUM.sub("", name.lower())


async def unique_email(
    local_base: str, exists: Callable[[str], Awaitable[bool]]
) -> str:
    """Build a unique email, appending 1, 2, 3… on collision."""
    candidate = f"{local_base}@{EMAIL_DOMAIN}"
    n = 1
    while await exists(candidate):
        candidate = f"{local_base}{n}@{EMAIL_DOMAIN}"
        n += 1
    return candidate
