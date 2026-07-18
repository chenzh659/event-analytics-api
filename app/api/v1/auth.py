from fastapi import APIRouter, status

from app.core.rbac import RoleName
from app.deps import CurrentUser, DbSession
from app.schemas.auth import TokenResponse, UserCreate, UserLogin, UserRead
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


def _to_user_read(user) -> UserRead:
    return UserRead(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        is_active=user.is_active,
        role=user.role.name,
        version=user.version,
        created_at=user.created_at,
    )


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def register(body: UserCreate, db: DbSession) -> UserRead:
    service = AuthService(db)
    user = await service.register(body, role_name=RoleName.CLIENT_APP)
    return _to_user_read(user)


@router.post("/login", response_model=TokenResponse)
async def login(body: UserLogin, db: DbSession) -> TokenResponse:
    service = AuthService(db)
    _user, token = await service.authenticate(body.email, body.password)
    return TokenResponse(access_token=token)


@router.get("/me", response_model=UserRead)
async def me(user: CurrentUser) -> UserRead:
    return _to_user_read(user)
