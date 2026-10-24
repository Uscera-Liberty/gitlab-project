from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field

Role = Literal["admin", "user"]


class UserCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    role: Role = "user"


class UserUpdate(BaseModel):
    """Все поля необязательные: обновляются только переданные."""

    name: str | None = Field(default=None, min_length=1, max_length=100)
    email: EmailStr | None = None
    role: Role | None = None


class User(BaseModel):
    id: int
    name: str
    email: EmailStr
    role: Role
    created_at: datetime
