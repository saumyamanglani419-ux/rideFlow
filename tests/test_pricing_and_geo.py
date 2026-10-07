import pytest

from services.fare_service.pricing import FareRates, calculate_fare
from shared.geo import haversine_km

RATES = FareRates(base_fare=50, per_km_rate=12, minimum_fare=80)


def test_haversine_one_degree_of_longitude_at_equator():
    assert haversine_km(0, 0, 0, 1) == pytest.approx(111.19, abs=0.01)


def test_haversine_same_point_is_zero():
    assert haversine_km(12.97, 77.6, 12.97, 77.6) == 0


def test_haversine_is_symmetric():
    assert haversine_km(12.9, 77.5, 13.1, 77.7) == pytest.approx(haversine_km(13.1, 77.7, 12.9, 77.5))


def test_fare_uses_base_plus_distance():
    # 50 + 10 * 12 = 170
    assert calculate_fare(10, RATES) == 170.0


def test_short_trip_gets_minimum_fare():
    # 50 + 1 * 12 = 62, below the 80 minimum
    assert calculate_fare(1, RATES) == 80.0


def test_fare_is_rounded_to_two_decimals():
    assert calculate_fare(3.333, RATES) == 90.0  # 50 + 39.996 = 89.996 -> 90.0
    assert calculate_fare(7.0049, RATES) == 134.06  # 50 + 84.0588


def test_negative_distance_is_rejected():
    with pytest.raises(ValueError):
        calculate_fare(-1, RATES)
