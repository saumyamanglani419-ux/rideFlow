from datetime import datetime

from pydantic import BaseModel, Field, model_validator

from services.ride_service.state_machine import RideStatus
from shared.schemas import Location


class RideRequest(BaseModel):
    pickup: Location
    dropoff: Location

    @model_validator(mode="after")
    def pickup_and_dropoff_differ(self) -> "RideRequest":
        if (self.pickup.latitude, self.pickup.longitude) == (
            self.dropoff.latitude,
            self.dropoff.longitude,
        ):
            raise ValueError("Pickup and dropoff must be different locations.")
        return self


class CancelRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=200)


class DriverSummary(BaseModel):
    driver_id: str
    full_name: str
    vehicle_model: str
    license_plate: str


class StatusChange(BaseModel):
    status: RideStatus
    changed_by: str
    changed_at: datetime


class RidePublic(BaseModel):
    id: str
    rider_id: str
    rider_name: str
    driver: DriverSummary
    pickup: Location
    dropoff: Location
    distance_km: float
    estimated_fare: float
    currency: str
    status: RideStatus
    status_history: list[StatusChange]
    cancel_reason: str | None = None
    created_at: datetime
    updated_at: datetime
