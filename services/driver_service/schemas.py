from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from shared.schemas import Location


class DriverProfileCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    vehicle_model: str = Field(min_length=2, max_length=60, examples=["Maruti Suzuki Dzire"])
    license_plate: str = Field(
        pattern=r"^[A-Z0-9][A-Z0-9 -]{3,14}$", examples=["KA01AB1234"]
    )
    location: Location

    @field_validator("license_plate", mode="before")
    @classmethod
    def normalise_plate(cls, value: Any) -> Any:
        # Runs before the pattern check, so "ka01ab1234" is accepted and stored uppercase.
        return value.strip().upper() if isinstance(value, str) else value


class AvailabilityUpdate(BaseModel):
    is_available: bool
    location: Location | None = None


class DriverProfile(BaseModel):
    id: str  # same as the driver's user id
    full_name: str
    vehicle_model: str
    license_plate: str
    is_available: bool
    current_ride_id: str | None
    location: Location
    created_at: datetime
    updated_at: datetime


class AvailableDriver(BaseModel):
    """Public view for riders: no licence plate until a ride is assigned."""

    driver_id: str
    full_name: str
    vehicle_model: str
    location: Location


# ----- internal (service-to-service) models -----

class AssignRequest(BaseModel):
    ride_id: str = Field(min_length=1)
    pickup: Location


class AssignedDriver(BaseModel):
    driver_id: str
    full_name: str
    vehicle_model: str
    license_plate: str
    distance_km: float


class ReleaseRequest(BaseModel):
    ride_id: str = Field(min_length=1)
    # Where the driver is now. Sent on completion (the drop-off point) so the
    # next nearest-driver search uses the driver's real position.
    location: Location | None = None


class ReleaseResponse(BaseModel):
    driver_id: str
    released: bool
