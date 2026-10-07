"""
MongoDB access for rides.

Status updates use optimistic concurrency: the update filter includes the
status we *expect* the ride to be in. If two requests race (say, the rider
cancels while the driver presses "start"), only the first one matches; the
second gets None back and we return 409 Conflict instead of silently
overwriting.
"""

from datetime import datetime, timezone
from typing import Any

from pymongo import DESCENDING, ReturnDocument
from pymongo.database import Database

from services.ride_service.state_machine import ACTIVE_STATUSES, RideStatus

RIDES = "rides"


def ensure_indexes(db: Database) -> None:
    db[RIDES].create_index([("rider_id", 1), ("created_at", DESCENDING)])
    db[RIDES].create_index([("driver.driver_id", 1), ("created_at", DESCENDING)])


def create_ride(db: Database, ride: dict[str, Any]) -> dict[str, Any]:
    db[RIDES].insert_one(ride)
    return ride


def get_ride(db: Database, ride_id: str) -> dict[str, Any] | None:
    return db[RIDES].find_one({"_id": ride_id})


def find_active_ride_for_rider(db: Database, rider_id: str) -> dict[str, Any] | None:
    return db[RIDES].find_one(
        {"rider_id": rider_id, "status": {"$in": [s.value for s in ACTIVE_STATUSES]}}
    )


def list_rides(
    db: Database,
    *,
    owner_field: str,
    user_id: str,
    status: RideStatus | None,
    limit: int,
) -> list[dict[str, Any]]:
    query: dict[str, Any] = {owner_field: user_id}
    if status is not None:
        query["status"] = status.value
    cursor = db[RIDES].find(query).sort("created_at", DESCENDING).limit(limit)
    return list(cursor)


def update_status(
    db: Database,
    *,
    ride_id: str,
    expected: RideStatus,
    new: RideStatus,
    changed_by: str,
    extra_fields: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    now = datetime.now(timezone.utc)
    return db[RIDES].find_one_and_update(
        {"_id": ride_id, "status": expected.value},
        {
            "$set": {"status": new.value, "updated_at": now, **(extra_fields or {})},
            "$push": {
                "status_history": {
                    "status": new.value,
                    "changed_by": changed_by,
                    "changed_at": now,
                }
            },
        },
        return_document=ReturnDocument.AFTER,
    )
