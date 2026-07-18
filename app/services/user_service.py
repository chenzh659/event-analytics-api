"""User admin service with optimistic locking."""

from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import ConflictError, NotFoundError
from app.core.rbac import RoleName
from app.db.models.user import Role, User
from app.schemas.auth import UserAdminUpdate


class UserService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_users(self, *, limit: int = 50, offset: int = 0) -> list[User]:
        result = await self.db.execute(
            select(User)
            .options(selectinload(User.role))
            .order_by(User.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def update_user(self, user_id: UUID, data: UserAdminUpdate) -> User:
        result = await self.db.execute(
            select(User).options(selectinload(User.role)).where(User.id == user_id)
        )
        user = result.scalar_one_or_none()
        if user is None:
            raise NotFoundError("User not found")

        values: dict = {"version": user.version + 1}
        if data.full_name is not None:
            values["full_name"] = data.full_name
        if data.is_active is not None:
            values["is_active"] = data.is_active
        if data.role is not None:
            try:
                RoleName(data.role)
            except ValueError as exc:
                raise ConflictError(f"Invalid role: {data.role}") from exc
            role_result = await self.db.execute(select(Role).where(Role.name == data.role))
            role = role_result.scalar_one_or_none()
            if role is None:
                raise NotFoundError("Role not found")
            values["role_id"] = role.id

        stmt = (
            update(User)
            .where(User.id == user_id, User.version == data.version)
            .values(**values)
            .returning(User.id)
        )
        updated = await self.db.execute(stmt)
        if updated.scalar_one_or_none() is None:
            raise ConflictError(
                "Version conflict: resource was modified by another request",
                code="version_conflict",
            )

        result = await self.db.execute(
            select(User).options(selectinload(User.role)).where(User.id == user_id)
        )
        return result.scalar_one()
