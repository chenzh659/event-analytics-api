from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str | None = Field(default=None, max_length=128)


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: EmailStr
    full_name: str | None
    is_active: bool
    role: str
    version: int
    created_at: datetime


class UserAdminUpdate(BaseModel):
    full_name: str | None = Field(default=None, max_length=128)
    is_active: bool | None = None
    role: str | None = None
    version: int = Field(ge=1, description="Optimistic lock version")
