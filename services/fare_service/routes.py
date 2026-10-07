from fastapi import APIRouter

from services.fare_service.pricing import FareRates, calculate_fare
from services.fare_service.schemas import (
    FareEstimateRequest,
    FareEstimateResponse,
    FareRatesResponse,
)
from shared.config import get_settings
from shared.geo import haversine_km

router = APIRouter(prefix="/fares", tags=["fares"])


def _current_rates() -> FareRates:
    settings = get_settings()
    return FareRates(
        base_fare=settings.base_fare,
        per_km_rate=settings.per_km_rate,
        minimum_fare=settings.minimum_fare,
    )


@router.get("/rates", response_model=FareRatesResponse)
def get_rates() -> FareRatesResponse:
    """Current pricing configuration."""
    rates = _current_rates()
    return FareRatesResponse(
        base_fare=rates.base_fare,
        per_km_rate=rates.per_km_rate,
        minimum_fare=rates.minimum_fare,
        currency=get_settings().currency,
    )


@router.post("/estimate", response_model=FareEstimateResponse)
def estimate_fare(payload: FareEstimateRequest) -> FareEstimateResponse:
    """
    Estimate a fare from pickup to dropoff.

    Public on purpose: like most ride apps, you can check a price before
    logging in. The Ride Service also calls this when a ride is requested.
    """
    distance_km = round(
        haversine_km(
            payload.pickup.latitude,
            payload.pickup.longitude,
            payload.dropoff.latitude,
            payload.dropoff.longitude,
        ),
        2,
    )
    rates = _current_rates()
    return FareEstimateResponse(
        distance_km=distance_km,
        estimated_fare=calculate_fare(distance_km, rates),
        base_fare=rates.base_fare,
        per_km_rate=rates.per_km_rate,
        minimum_fare=rates.minimum_fare,
        currency=get_settings().currency,
    )
