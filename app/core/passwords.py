"""Temporary password generation — port of backend/src/common/password.ts."""

from __future__ import annotations

import secrets

# No ambiguous characters (no I, O, l, 0, 1).
_CHARS = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def gen_password() -> str:
    """Readable one-time password, e.g. "Noloop-7F3K9Q"."""
    suffix = "".join(secrets.choice(_CHARS) for _ in range(6))
    return f"Noloop-{suffix}"
