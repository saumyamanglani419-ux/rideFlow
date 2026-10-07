from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pymongo.database import Database
from pymongo.errors import DuplicateKeyError

from services.driver_service import repository
from services.driver_service.database import get_db
from services.driver_service.schemas import (
    AssignedDriver,
    AssignRequest,
    AvailabilityUpdate,
    AvailableDriver,
    DriverProfile,
    DriverProfileCreate,
    ReleaseRequest,
    ReleaseResponse,
)
from shared.auth import CurrentUserDep, DriverDep, verify_internal_api_key
from shared.config import get_settings

DbDep = Annotated[Database, Depends(get_db)]

router = APIRouter(prefix="/drivers", tags=["drivers"])

# Every route on this router requires the X-Internal-API-Key header.
internal_router = APIRouter(
    prefix="/internal/drivers",
    tags=["internal (service-to-service)"],
    dependencies=[Depends(verify_internal_api_key)],
)


def _to_profile(driver: dict[str, Any]) -> DriverProfile:
    return DriverProfile(
        id=driver["_id"],
        full_name=driver["full_name"],
        vehicle_model=driver["vehicle_model"],
        license_plate=driver["license_plate"],
        is_available=driver["is_available"],
        current_ride_id=driver.get("current_ride_id"),
        location=driver["location"],
        created_at=driver["created_at"],
        updated_at=driver["updated_at"],
    )


@router.post("/me", response_model=DriverProfile, status_code=status.HTTP_201_CREATED)
def create_my_profile(payload: DriverProfileCreate, driver: DriverDep, db: DbDep) -> DriverProfile:
    """Create the vehicle profile for the logged-in driver (starts offline)."""
    if repository.find_driver(db, driver.id):
        raise HTTPException(status.HTTP_409_CONFLICT, "You already have a driver profile.")
    try:
        doc = repository.create_driver(
            db,
            user_id=driver.id,
            full_name=driver.full_name,
            vehicle_model=payload.vehicle_model,
            license_plate=payload.license_plate,
            location=payload.location.model_dump(),
        )
    except DuplicateKeyError:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "This licence plate is already registered."
        ) from None
    return _to_profile(doc)


@router.get("/me", response_model=DriverProfile)
def get_my_profile(driver: DriverDep, db: DbDep) -> DriverProfile:
    doc = repository.find_driver(db, driver.id)
    if doc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Create your driver profile first.")
    return _to_profile(doc)


@router.patch("/me/availability", response_model=DriverProfile)
def update_my_availability(payload: AvailabilityUpdate, driver: DriverDep, db: DbDep) -> DriverProfile:
    """Go online/offline and optionally update your current location."""
    doc = repository.find_driver(db, driver.id)
    if doc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Create your driver profile first.")

    updated = repository.set_availability(
        db,
        driver.id,
        is_available=payload.is_available,
        location=payload.location.model_dump() if payload.location else None,
    )
    if updated is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "You can't change availability during an active ride. Complete or cancel it first.",
        )
    return _to_profile(updated)


@router.get("/available", response_model=list[AvailableDriver])
def list_available_drivers(
    _: CurrentUserDep,
    db: DbDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[AvailableDriver]:
    """Drivers who are online and not on a ride (any logged-in user)."""
    return [
        AvailableDriver(
            driver_id=d["_id"],
            full_name=d["full_name"],
            vehicle_model=d["vehicle_model"],
            location=d["location"],
        )
        for d in repository.list_available(db, limit)
    ]


@internal_router.post("/assign", response_model=AssignedDriver)
def assign_nearest_driver(payload: AssignRequest, db: DbDep) -> AssignedDriver:
    """Called by the Ride Service: reserve the nearest free driver for a ride."""
    result = repository.reserve_nearest_driver(
        db,
        pickup=payload.pickup,
        ride_id=payload.ride_id,
        max_distance_km=get_settings().max_driver_search_km,
    )
    if result is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No available driver nearby.")
    driver, distance_km = result
    return AssignedDriver(
        driver_id=driver["_id"],
        full_name=driver["full_name"],
        vehicle_model=driver["vehicle_model"],
        license_plate=driver["license_plate"],
        distance_km=distance_km,
    )


@internal_router.post("/{driver_id}/release", response_model=ReleaseResponse)
def release_driver(driver_id: str, payload: ReleaseRequest, db: DbDep) -> ReleaseResponse:
    """Called by the Ride Service when a ride completes or is cancelled. Idempotent."""
    if repository.find_driver(db, driver_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Driver not found.")
    released = repository.release_driver(
        db,
        driver_id,
        payload.ride_id,
        location=payload.location.model_dump() if payload.location else None,
    )
    return ReleaseResponse(driver_id=driver_id, released=released)
