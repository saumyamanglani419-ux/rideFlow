from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pymongo.database import Database
from pymongo.errors import DuplicateKeyError

from services.user_service import repository
from services.user_service.database import get_db
from services.user_service.schemas import (
    LoginRequest,
    RegisterRequest,
    TokenResponse,
    UpdateProfileRequest,
    UserPublic,
)
from shared.auth import CurrentUserDep
from shared.config import get_settings
from shared.security import create_access_token, hash_password, verify_password

router = APIRouter()
DbDep = Annotated[Database, Depends(get_db)]


def _to_public(user: dict[str, Any]) -> UserPublic:
    return UserPublic(
        id=user["_id"],
        email=user["email"],
        full_name=user["full_name"],
        phone=user.get("phone"),
        role=user["role"],
        created_at=user["created_at"],
        updated_at=user["updated_at"],
    )


@router.post(
    "/auth/register",
    response_model=UserPublic,
    status_code=status.HTTP_201_CREATED,
    tags=["auth"],
)
def register(payload: RegisterRequest, db: DbDep) -> UserPublic:
    """Create a rider or driver account."""
    email = payload.email.lower()
    duplicate = HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists.")

    if repository.find_by_email(db, email):
        raise duplicate

    settings = get_settings()
    try:
        user = repository.create_user(
            db,
            email=email,
            password_hash=hash_password(payload.password, settings.password_hash_iterations),
            full_name=payload.full_name,
            phone=payload.phone,
            role=payload.role.value,
        )
    except DuplicateKeyError:  # two requests raced past the check above
        raise duplicate from None
    return _to_public(user)


@router.post("/auth/login", response_model=TokenResponse, tags=["auth"])
def login(payload: LoginRequest, db: DbDep) -> TokenResponse:
    """Exchange email + password for a JWT access token."""
    user = repository.find_by_email(db, payload.email.lower())
    # Same message for "no such user" and "wrong password" so attackers
    # can't use this endpoint to discover which emails are registered.
    if user is None or not verify_password(payload.password, user["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    settings = get_settings()
    token = create_access_token(
        user_id=user["_id"],
        role=user["role"],
        email=user["email"],
        full_name=user["full_name"],
        secret_key=settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
        expires_minutes=settings.access_token_expire_minutes,
    )
    return TokenResponse(access_token=token, expires_in=settings.access_token_expire_minutes * 60)


@router.get("/users/me", response_model=UserPublic, tags=["users"])
def get_my_profile(current_user: CurrentUserDep, db: DbDep) -> UserPublic:
    user = repository.find_by_id(db, current_user.id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found.")
    return _to_public(user)


@router.patch("/users/me", response_model=UserPublic, tags=["users"])
def update_my_profile(
    payload: UpdateProfileRequest, current_user: CurrentUserDep, db: DbDep
) -> UserPublic:
    """
    Update name and/or phone. A name change appears in tokens issued at the
    next login (existing tokens keep the old name until they expire).
    """
    changes = payload.model_dump(exclude_unset=True, exclude_none=True)
    if not changes:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Provide at least one field to update.")

    user = repository.update_user(db, current_user.id, changes)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found.")
    return _to_public(user)
