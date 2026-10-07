from datetime import datetime
from typing import Annotated, Any

from pydantic import BaseModel, BeforeValidator, EmailStr, Field, StringConstraints

from shared.auth import Role

PHONE_PATTERN = r"^\+?[0-9]{7,15}$"


def _strip(value: Any) -> Any:
    return value.strip() if isinstance(value, str) else value


# Whitespace is stripped field by field, NOT model-wide. A model-wide
# `str_strip_whitespace` would also strip passwords, silently changing what
# the user typed (" my pass " would be stored as "my pass").
Email = Annotated[EmailStr, BeforeValidator(_strip)]
FullName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=100)]
Phone = Annotated[str, StringConstraints(strip_whitespace=True, pattern=PHONE_PATTERN)]


class RegisterRequest(BaseModel):
    email: Email
    password: str = Field(min_length=8, max_length=128)  # stored exactly as typed
    full_name: FullName
    phone: Phone | None = Field(default=None, examples=["+919876543210"])
    role: Role


class LoginRequest(BaseModel):
    email: Email
    password: str = Field(min_length=1, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds


class UpdateProfileRequest(BaseModel):
    full_name: FullName | None = None
    phone: Phone | None = None


class UserPublic(BaseModel):
    """What we return to clients. Note: never includes the password hash."""

    id: str
    email: str
    full_name: str
    phone: str | None
    role: Role
    created_at: datetime
    updated_at: datetime
