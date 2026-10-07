"""
MongoDB access for driver profiles.

Key idea - "compare-and-set" reservation:
Two riders might request a ride at the same moment and both pick the same
nearest driver. To prevent double-booking we never "read, then write".
Instead, find_one_and_update only succeeds if the driver is *still* free:

    filter: {_id: driver, is_available: True, current_ride_id: None}
    update: {is_available: False, current_ride_id: <ride>}

MongoDB applies that single-document update atomically, so exactly one
request wins. The loser simply moves on to the next-nearest driver.
"""

from datetime import datetime, timezone
from typing import Any

from pymongo import ReturnDocument
from pymongo.database import Database

from shared.geo import haversine_km
from shared.schemas import Location

DRIVERS = "drivers"


def ensure_indexes(db: Database) -> None:
    db[DRIVERS].create_index("license_plate", unique=True)
    db[DRIVERS].create_index([("is_available", 1), ("current_ride_id", 1)])


def create_driver(
    db: Database,
    *,
    user_id: str,
    full_name: str,
    vehicle_model: str,
    license_plate: str,
    location: dict[str, float],
) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    driver = {
        "_id": user_id,  # one profile per driver account
        "full_name": full_name,
        "vehicle_model": vehicle_model,
        "license_plate": license_plate,
        "location": location,
        "is_available": False,  # drivers go online explicitly
        "current_ride_id": None,
        "created_at": now,
        "updated_at": now,
    }
    db[DRIVERS].insert_one(driver)  # DuplicateKeyError on duplicate _id or plate
    return driver


def find_driver(db: Database, driver_id: str) -> dict[str, Any] | None:
    return db[DRIVERS].find_one({"_id": driver_id})


def set_availability(
    db: Database,
    driver_id: str,
    *,
    is_available: bool,
    location: dict[str, float] | None,
) -> dict[str, Any] | None:
    """Returns None if the driver doesn't exist or is currently on a ride."""
    changes: dict[str, Any] = {
        "is_available": is_available,
        "updated_at": datetime.now(timezone.utc),
    }
    if location is not None:
        changes["location"] = location
    return db[DRIVERS].find_one_and_update(
        {"_id": driver_id, "current_ride_id": None},
        {"$set": changes},
        return_document=ReturnDocument.AFTER,
    )


def list_available(db: Database, limit: int) -> list[dict[str, Any]]:
    cursor = db[DRIVERS].find({"is_available": True, "current_ride_id": None}).limit(limit)
    return list(cursor)


def reserve_nearest_driver(
    db: Database,
    *,
    pickup: Location,
    ride_id: str,
    max_distance_km: float,
) -> tuple[dict[str, Any], float] | None:
    """
    Pick the closest free driver within max_distance_km and atomically mark
    them as busy with this ride. Returns (driver, distance_km) or None.

    We rank candidates in Python with the haversine formula, which is clear
    and works everywhere. At real scale you'd use a MongoDB 2dsphere index
    with $near so the database does the geo search.
    """
    candidates = db[DRIVERS].find({"is_available": True, "current_ride_id": None})
    ranked: list[tuple[float, dict[str, Any]]] = []
    for driver in candidates:
        loc = driver["location"]
        distance = haversine_km(pickup.latitude, pickup.longitude, loc["latitude"], loc["longitude"])
        if distance <= max_distance_km:
            ranked.append((distance, driver))
    ranked.sort(key=lambda pair: pair[0])

    for distance, driver in ranked:
        reserved = db[DRIVERS].find_one_and_update(
            {"_id": driver["_id"], "is_available": True, "current_ride_id": None},
            {
                "$set": {
                    "is_available": False,
                    "current_ride_id": ride_id,
                    "updated_at": datetime.now(timezone.utc),
                }
            },
            return_document=ReturnDocument.AFTER,
        )
        if reserved is not None:
            return reserved, round(distance, 2)
        # Someone else grabbed this driver a moment ago - try the next one.
    return None


def release_driver(
    db: Database,
    driver_id: str,
    ride_id: str,
    location: dict[str, float] | None = None,
) -> bool:
    """
    Free a driver after their ride ends, optionally moving them to `location`.
    Only releases if they are still on *this* ride, so the call is safe to
    repeat (idempotent).
    """
    changes: dict[str, Any] = {
        "is_available": True,
        "current_ride_id": None,
        "updated_at": datetime.now(timezone.utc),
    }
    if location is not None:
        changes["location"] = location
    result = db[DRIVERS].update_one(
        {"_id": driver_id, "current_ride_id": ride_id},
        {"$set": changes},
    )
    return result.modified_count == 1
