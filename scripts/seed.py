"""Seed roles and default users."""

import asyncio

from sqlalchemy import select

from app.config import get_settings
from app.core.rbac import RoleName
from app.core.security import hash_password
from app.db.models.user import Role, User
from app.db.session import async_session_factory

ROLES = [
    (RoleName.ADMIN, "Full administrative access"),
    (RoleName.ANALYST, "Read metrics and events"),
    (RoleName.CLIENT_APP, "Ingest events"),
]


async def seed() -> None:
    settings = get_settings()
    async with async_session_factory() as session:
        for name, desc in ROLES:
            existing = await session.execute(select(Role).where(Role.name == name.value))
            if existing.scalar_one_or_none() is None:
                session.add(Role(name=name.value, description=desc))
        await session.flush()

        async def ensure_user(email: str, password: str, role_name: str, full_name: str) -> None:
            result = await session.execute(select(User).where(User.email == email.lower()))
            if result.scalar_one_or_none() is not None:
                return
            role_result = await session.execute(select(Role).where(Role.name == role_name))
            role = role_result.scalar_one()
            session.add(
                User(
                    email=email.lower(),
                    hashed_password=hash_password(password),
                    full_name=full_name,
                    role_id=role.id,
                )
            )

        await ensure_user(
            settings.seed_admin_email,
            settings.seed_admin_password,
            RoleName.ADMIN.value,
            "Admin User",
        )
        await ensure_user(
            settings.seed_analyst_email,
            settings.seed_analyst_password,
            RoleName.ANALYST.value,
            "Analyst User",
        )
        await ensure_user(
            settings.seed_client_email,
            settings.seed_client_password,
            RoleName.CLIENT_APP.value,
            "Client App",
        )
        await session.commit()
        print("[seed] roles and users ready")


if __name__ == "__main__":
    asyncio.run(seed())
