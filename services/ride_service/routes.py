import logging
from datetime import datetime, timezone
from typing import Annotated, Any
from uuid import uuid4

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from pymongo.database import Database

from services.ride_service import repository
from services.ride_service.clients import (
    DriverClient,
    FareClient,
    get_driver_client,
    get_fare_client,
)
from services.ride_service.database import get_db
from services.ride_service.schemas import CancelRequest, RidePublic, RideRequest
from services.ride_service.state_machine import (
    InvalidTransitionError,
    RideStatus,
    validate_transition,
)
from shared.auth import CurrentUser, CurrentUserDep, DriverDep, RiderDep, Role
from shared.schemas import Location
from shared.service_client import ServiceUnavailableError, UpstreamServiceError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/rides", tags=["rides"])

DbDep = Annotated[Database, Depends(get_db)]
FareClientDep = Annotated[FareClient, Depends(get_fare_client)]
DriverClientDep = Annotated[DriverClient, Depends(get_driver_client)]

RIDE_NOT_FOUND = "Ride not found."


# ----------------------------------------------------------------- helpers

def _to_public(ride: dict[str, Any]) -> RidePublic:
    return RidePublic(
        id=ride["_id"],
        rider_id=ride["rider_id"],
        rider_name=ride["rider_name"],
        driver=ride["driver"],
        pickup=ride["pickup"],
        dropoff=ride["dropoff"],
        distance_km=ride["distance_km"],
        estimated_fare=ride["estimated_fare"],
        currency=ride["currency"],
        status=ride["status"],
        status_history=ride["status_history"],
        cancel_reason=ride.get("cancel_reason"),
        created_at=ride["created_at"],
        updated_at=ride["updated_at"],
    )


def _is_participant(ride: dict[str, Any], user: CurrentUser) -> bool:
    return user.id in (ride["rider_id"], ride["driver"]["driver_id"])


def _load_ride_for(db: Database, ride_id: str, user: CurrentUser) -> dict[str, Any]:
    """Return the ride if `user` is part of it. Otherwise 404, so we don't
    reveal that someone else's ride exists."""
    ride = repository.get_ride(db, ride_id)
    if ride is None or not _is_participant(ride, user):
        raise HTTPException(status.HTTP_404_NOT_FOUND, RIDE_NOT_FOUND)
    return ride


def _load_ride_for_assigned_driver(db: Database, ride_id: str, driver: CurrentUser) -> dict[str, Any]:
    ride = repository.get_ride(db, ride_id)
    if ride is None or ride["driver"]["driver_id"] != driver.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, RIDE_NOT_FOUND)
    return ride


def _transition(
    db: Database,
    ride: dict[str, Any],
    target: RideStatus,
    actor: CurrentUser,
    extra_fields: dict[str, Any] | None = None,
) -> dict[str, Any]:
    current = RideStatus(ride["status"])
    try:
        validate_transition(current, target)
    except InvalidTransitionError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc

    updated = repository.update_status(
        db,
        ride_id=ride["_id"],
        expected=current,
        new=target,
        changed_by=actor.id,
        extra_fields=extra_fields,
    )
    if updated is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "The ride was updated by another request. Fetch it again and retry.",
        )
    return updated


def _release_driver_safely(
    driver_client: DriverClient,
    driver_id: str,
    ride_id: str,
    location: Location | None = None,
) -> None:
    """
    Best effort: the ride's own state change already succeeded, so we don't
    fail the user's request if the Driver Service is briefly down. Release is
    idempotent, so it can safely be retried later (see README limitations).
    """
    try:
        driver_client.release(driver_id=driver_id, ride_id=ride_id, location=location)
    except (ServiceUnavailableError, UpstreamServiceError) as exc:
        logger.warning("Could not release driver %s for ride %s: %s", driver_id, ride_id, exc)


# ------------------------------------------------------------------ routes

@router.post("", response_model=RidePublic, status_code=status.HTTP_201_CREATED)
def request_ride(
    payload: RideRequest,
    rider: RiderDep,
    db: DbDep,
    fare_client: FareClientDep,
    driver_client: DriverClientDep,
) -> RidePublic:
    """
    Request a ride. Steps:
      1. Make sure the rider has no other active ride.
      2. Ask the Fare Service for a price.
      3. Ask the Driver Service to reserve the nearest free driver.
      4. Save the ride. If saving fails, release the driver again
         (a "compensating action", since we can't use one transaction
         across two services' databases).
    """
    if repository.find_active_ride_for_rider(db, rider.id):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "You already have an active ride. Complete or cancel it first.",
        )

    fare = fare_client.estimate(payload.pickup, payload.dropoff)

    ride_id = str(uuid4())
    driver = driver_client.reserve_nearest(ride_id=ride_id, pickup=payload.pickup)
    if driver is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "No drivers are available near your pickup point right now. Please try again shortly.",
        )

    now = datetime.now(timezone.utc)
    ride = {
        "_id": ride_id,
        "rider_id": rider.id,
        "rider_name": rider.full_name,
        "driver": {
            "driver_id": driver.driver_id,
            "full_name": driver.full_name,
            "vehicle_model": driver.vehicle_model,
            "license_plate": driver.license_plate,
        },
        "pickup": payload.pickup.model_dump(),
        "dropoff": payload.dropoff.model_dump(),
        "distance_km": fare.distance_km,
        "estimated_fare": fare.estimated_fare,
        "currency": fare.currency,
        "status": RideStatus.DRIVER_ASSIGNED.value,
        "status_history": [
            {"status": RideStatus.DRIVER_ASSIGNED.value, "changed_by": rider.id, "changed_at": now}
        ],
        "cancel_reason": None,
        "created_at": now,
        "updated_at": now,
    }
    try:
        repository.create_ride(db, ride)
    except Exception:
        _release_driver_safely(driver_client, driver.driver_id, ride_id)
        raise
    return _to_public(ride)


@router.get("/me", response_model=list[RidePublic])
def my_trip_history(
    user: CurrentUserDep,
    db: DbDep,
    ride_status: Annotated[RideStatus | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[RidePublic]:
    """Your rides, newest first. Riders see rides they took; drivers see rides they drove.
    Drivers can poll `?status=driver_assigned` to find new rides to accept."""
    owner_field = "rider_id" if user.role == Role.RIDER else "driver.driver_id"
    rides = repository.list_rides(
        db, owner_field=owner_field, user_id=user.id, status=ride_status, limit=limit
    )
    return [_to_public(r) for r in rides]


@router.get("/{ride_id}", response_model=RidePublic)
def get_ride(ride_id: str, user: CurrentUserDep, db: DbDep) -> RidePublic:
    return _to_public(_load_ride_for(db, ride_id, user))


@router.post("/{ride_id}/accept", response_model=RidePublic)
def accept_ride(ride_id: str, driver: DriverDep, db: DbDep) -> RidePublic:
    ride = _load_ride_for_assigned_driver(db, ride_id, driver)
    return _to_public(_transition(db, ride, RideStatus.ACCEPTED, driver))


@router.post("/{ride_id}/start", response_model=RidePublic)
def start_ride(ride_id: str, driver: DriverDep, db: DbDep) -> RidePublic:
    ride = _load_ride_for_assigned_driver(db, ride_id, driver)
    return _to_public(_transition(db, ride, RideStatus.IN_PROGRESS, driver))


@router.post("/{ride_id}/complete", response_model=RidePublic)
def complete_ride(
    ride_id: str, driver: DriverDep, db: DbDep, driver_client: DriverClientDep
) -> RidePublic:
    ride = _load_ride_for_assigned_driver(db, ride_id, driver)
    updated = _transition(db, ride, RideStatus.COMPLETED, driver)
    # The driver is now at the drop-off point; tell the Driver Service so the
    # next nearest-driver search uses their real position.
    _release_driver_safely(
        driver_client, driver.id, ride_id, location=Location.model_validate(updated["dropoff"])
    )
    return _to_public(updated)


@router.post("/{ride_id}/cancel", response_model=RidePublic)
def cancel_ride(
    ride_id: str,
    user: CurrentUserDep,
    db: DbDep,
    driver_client: DriverClientDep,
    payload: Annotated[CancelRequest | None, Body()] = None,
) -> RidePublic:
    """Rider or assigned driver can cancel before the trip starts."""
    ride = _load_ride_for(db, ride_id, user)
    reason = payload.reason if payload else None
    updated = _transition(db, ride, RideStatus.CANCELLED, user, {"cancel_reason": reason})
    _release_driver_safely(driver_client, ride["driver"]["driver_id"], ride_id)
    return _to_public(updated)
