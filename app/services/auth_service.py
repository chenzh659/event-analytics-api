"""Auth service: register / login."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import ConflictError, UnauthorizedError
from app.core.rbac import RoleName
from app.core.security import create_access_token, hash_password, verify_password
from app.db.models.user import Role, User
from app.schemas.auth import UserCreate


class AuthService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def _get_role(self, name: str) -> Role:
        result = await self.db.execute(select(Role).where(Role.name == name))
        role = result.scalar_one_or_none()
        if role is None:
            raise RuntimeError(f"Role not seeded: {name}")
        return role

    async def register(self, data: UserCreate, *, role_name: str = RoleName.CLIENT_APP) -> User:
        existing = await self.db.execute(select(User).where(User.email == data.email))
        if existing.scalar_one_or_none():
            raise ConflictError("Email already registered", code="email_taken")

        role = await self._get_role(role_name)
        user = User(
            email=data.email.lower(),
            hashed_password=hash_password(data.password),
            full_name=data.full_name,
            role_id=role.id,
        )
        self.db.add(user)
        await self.db.flush()
        await self.db.refresh(user, attribute_names=["role"])
        # ensure role loaded
        result = await self.db.execute(
            select(User).options(selectinload(User.role)).where(User.id == user.id)
        )
        return result.scalar_one()

    async def authenticate(self, email: str, password: str) -> tuple[User, str]:
        result = await self.db.execute(
            select(User)
            .options(selectinload(User.role))
            .where(User.email == email.lower())
        )
        user = result.scalar_one_or_none()
        if user is None or not verify_password(password, user.hashed_password):
            raise UnauthorizedError("Invalid email or password")
        if not user.is_active:
            raise UnauthorizedError("User is inactive")
        token = create_access_token(subject=user.id, role=user.role.name)
        return user, token
