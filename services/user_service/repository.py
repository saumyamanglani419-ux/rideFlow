"""
All MongoDB access for users lives here (the "repository" pattern).
Routes never talk to MongoDB directly, which keeps them short and makes
it obvious where every query is.
"""

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from pymongo import ReturnDocument
from pymongo.database import Database

USERS = "users"


def ensure_indexes(db: Database) -> None:
    # The unique index is the real guarantee against duplicate emails, even if
    # two registrations race each other.
    db[USERS].create_index("email", unique=True)


def create_user(
    db: Database,
    *,
    email: str,
    password_hash: str,
    full_name: str,
    phone: str | None,
    role: str,
) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    user = {
        "_id": str(uuid4()),
        "email": email,
        "password_hash": password_hash,
        "full_name": full_name,
        "phone": phone,
        "role": role,
        "created_at": now,
        "updated_at": now,
    }
    db[USERS].insert_one(user)  # raises DuplicateKeyError if the email exists
    return user


def find_by_email(db: Database, email: str) -> dict[str, Any] | None:
    return db[USERS].find_one({"email": email})


def find_by_id(db: Database, user_id: str) -> dict[str, Any] | None:
    return db[USERS].find_one({"_id": user_id})


def update_user(db: Database, user_id: str, changes: dict[str, Any]) -> dict[str, Any] | None:
    changes = {**changes, "updated_at": datetime.now(timezone.utc)}
    return db[USERS].find_one_and_update(
        {"_id": user_id},
        {"$set": changes},
        return_document=ReturnDocument.AFTER,
    )
