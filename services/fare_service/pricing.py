"""
Fare formula, kept free of FastAPI so it is trivial to unit-test.

    fare = max(base_fare + distance_km * per_km_rate, minimum_fare)

Money note: we round to 2 decimals and use floats for readability. A real
payments system would store integer minor units (paise/cents) or Decimal to
avoid floating-point rounding surprises.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class FareRates:
    base_fare: float
    per_km_rate: float
    minimum_fare: float


def calculate_fare(distance_km: float, rates: FareRates) -> float:
    if distance_km < 0:
        raise ValueError("distance_km cannot be negative")
    raw_fare = rates.base_fare + distance_km * rates.per_km_rate
    return round(max(raw_fare, rates.minimum_fare), 2)
