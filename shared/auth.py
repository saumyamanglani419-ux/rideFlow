"""
FastAPI authentication dependencies used by every protected endpoint.

How it works:
  1. The client sends `Authorization: Bearer <token>`.
  2. get_current_user verifies the JWT signature and expiry locally.
  3. require_role(...) additionally checks the user's role.

Service-to-service calls use a separate shared key in the
`X-Internal-API-Key` header, so internal endpoints (like "reserve a driver")
can't be called by ordinary users even if they have a valid login token.
"""

import secrets
from enum import StrEnum
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ValidationError

from shared.config import get_settings
from shared.security import TokenError, decode_access_token


class Role(StrEnum):
    RIDER = "rider"
    DRIVER = "driver"


class CurrentUser(BaseModel):
    id: str
    email: str
    role: Role
    full_name: str


_bearer_scheme = HTTPBearer(
    auto_error=False,
    description="Paste the access_token returned by the User Service's POST /auth/login.",
)


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)],
) -> CurrentUser:
    if credentials is None:
        raise _unauthorized("Not authenticated. Send an 'Authorization: Bearer <token>' header.")

    settings = get_settings()
    try:
        claims = decode_access_token(
            credentials.credentials,
            secret_key=settings.jwt_secret_key,
            algorithm=settings.jwt_algorithm,
        )
        return CurrentUser(
            id=claims["sub"],
            email=claims.get("email", ""),
            role=claims["role"],
            full_name=claims.get("name", ""),
        )
    except TokenError as exc:
        raise _unauthorized(str(exc)) from exc
    except (ValidationError, KeyError) as exc:
        raise _unauthorized("Invalid authentication token.") from exc


def require_role(role: Role):
    """Build a dependency that only lets users with `role` through."""

    def checker(user: Annotated[CurrentUser, Depends(get_current_user)]) -> CurrentUser:
        if user.role != role:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Only users with the '{role.value}' role can do this.",
            )
        return user

    return checker


def verify_internal_api_key(
    x_internal_api_key: Annotated[
        str | None, Header(description="Shared key for service-to-service calls")
    ] = None,
) -> None:
    expected = get_settings().internal_api_key
    if not x_internal_api_key or not secrets.compare_digest(x_internal_api_key, expected):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This endpoint is for internal service calls only.",
        )


# Ready-made type aliases so route signatures stay short and readable.
CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]
RiderDep = Annotated[CurrentUser, Depends(require_role(Role.RIDER))]
DriverDep = Annotated[CurrentUser, Depends(require_role(Role.DRIVER))]
