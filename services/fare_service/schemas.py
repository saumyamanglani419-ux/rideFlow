from pydantic import BaseModel

from shared.schemas import Location


class FareEstimateRequest(BaseModel):
    pickup: Location
    dropoff: Location


class FareRatesResponse(BaseModel):
    base_fare: float
    per_km_rate: float
    minimum_fare: float
    currency: str


class FareEstimateResponse(FareRatesResponse):
    distance_km: float
    estimated_fare: float
