"""Distance calculation. Pure Python, no dependencies."""

import math

EARTH_RADIUS_KM = 6371.0088  # mean Earth radius


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Straight-line ("as the crow flies") distance between two points on Earth.

    Real apps use road distance from a routing engine; that needs a paid or
    self-hosted maps service, which is out of scope here. Haversine is a
    standard, explainable approximation.
    """
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))
