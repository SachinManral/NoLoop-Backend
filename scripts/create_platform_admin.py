"""Create (or update) the platform admin account.

Usage:
    python scripts/create_platform_admin.py <email> <password> [name]
"""

from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select  # noqa: E402

from app.core.security import hash_password  # noqa: E402
from app.db import SessionLocal, engine  # noqa: E402
from app.models import Role, User  # noqa: E402


async def main() -> None:
    args = sys.argv[1:]
    if len(args) < 2:
        print("Usage: python scripts/create_platform_admin.py <email> <password> [name]")
        sys.exit(1)
    email, password = args[0], args[1]
    name = args[2] if len(args) > 2 else "Platform Admin"
    password_hash = hash_password(password)

    async with SessionLocal() as session:
        user = (
            await session.execute(select(User).where(User.email == email))
        ).scalar_one_or_none()
        if user:
            user.password_hash = password_hash
            user.role = Role.PLATFORM_ADMIN
            user.name = name
        else:
            user = User(
                email=email,
                password_hash=password_hash,
                role=Role.PLATFORM_ADMIN,
                name=name,
            )
            session.add(user)
        await session.commit()
        print(f"✅ Platform admin ready: {user.email} (role {user.role.value})")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
