"""
Typed clients for the services the Ride Service depends on.

The Ride Service defines its own small models for the responses it needs
instead of importing the other services' code. That keeps services loosely
coupled: the Driver Service can change its internals freely as long as the
HTTP contract stays the same.
"""

from functools import lru_cache

from pydantic import BaseModel, ValidationError

from shared.config import get_settings
from shared.schemas import Location
from shared.service_client import ServiceClient, UpstreamServiceError


class FareEstimate(BaseModel):
    distance_km: float
    estimated_fare: float
    currency: str


class AssignedDriver(BaseModel):
    driver_id: str
    full_name: str
    vehicle_model: str
    license_plate: str
    distance_km: float


class FareClient:
    def __init__(self, client: ServiceClient):
        self._client = client

    def estimate(self, pickup: Location, dropoff: Location) -> FareEstimate:
        response = self._client.request(
            "POST",
            "/fares/estimate",
            json={"pickup": pickup.model_dump(), "dropoff": dropoff.model_dump()},
        )
        if response.status_code != 200:
            raise UpstreamServiceError(
                self._client.service_name, response.status_code, ServiceClient.error_detail(response)
            )
        try:
            return FareEstimate.model_validate(response.json())
        except (ValueError, ValidationError) as exc:
            raise UpstreamServiceError(
                self._client.service_name, response.status_code, "malformed response"
            ) from exc


class DriverClient:
    def __init__(self, client: ServiceClient):
        self._client = client

    def reserve_nearest(self, *, ride_id: str, pickup: Location) -> AssignedDriver | None:
        """Returns the reserved driver, or None if nobody is available nearby."""
        response = self._client.request(
            "POST",
            "/internal/drivers/assign",
            json={"ride_id": ride_id, "pickup": pickup.model_dump()},
        )
        if response.status_code == 404:
            return None
        if response.status_code != 200:
            raise UpstreamServiceError(
                self._client.service_name, response.status_code, ServiceClient.error_detail(response)
            )
        try:
            return AssignedDriver.model_validate(response.json())
        except (ValueError, ValidationError) as exc:
            raise UpstreamServiceError(
                self._client.service_name, response.status_code, "malformed response"
            ) from exc

    def release(self, *, driver_id: str, ride_id: str, location: Location | None = None) -> None:
        body: dict = {"ride_id": ride_id}
        if location is not None:
            body["location"] = location.model_dump()
        response = self._client.request("POST", f"/internal/drivers/{driver_id}/release", json=body)
        if response.status_code != 200:
            raise UpstreamServiceError(
                self._client.service_name, response.status_code, ServiceClient.error_detail(response)
            )


# ----- FastAPI dependencies (tests override these) -----

@lru_cache
def get_fare_client() -> FareClient:
    settings = get_settings()
    return FareClient(
        ServiceClient(
            "fare-service",
            settings.fare_service_url,
            timeout=settings.service_timeout_seconds,
        )
    )


@lru_cache
def get_driver_client() -> DriverClient:
    settings = get_settings()
    return DriverClient(
        ServiceClient(
            "driver-service",
            settings.driver_service_url,
            timeout=settings.service_timeout_seconds,
            default_headers={"X-Internal-API-Key": settings.internal_api_key},
        )
    )
