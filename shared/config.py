"""
Central configuration for every RideFlow service.

All settings come from environment variables. A `.env` file in the project
root is loaded automatically (via python-dotenv) so you don't have to export
variables by hand during local development. Real environment variables always
win over values in `.env`, which is what the tests rely on.
"""

import os
from dataclasses import dataclass
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()

MIN_SECRET_LENGTH = 32


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(
            f"Missing required environment variable '{name}'. "
            "Copy .env.example to .env and fill it in."
        )
    return value


def _str(name: str, default: str) -> str:
    value = os.getenv(name, "").strip()
    return value or default


def _float(name: str, default: float) -> float:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise RuntimeError(f"Environment variable '{name}' must be a number, got {raw!r}.") from exc


def _int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise RuntimeError(f"Environment variable '{name}' must be an integer, got {raw!r}.") from exc


@dataclass(frozen=True)
class Settings:
    # MongoDB: one server, but a separate database per service.
    mongodb_uri: str
    user_db_name: str
    driver_db_name: str
    ride_db_name: str

    # Security
    jwt_secret_key: str
    jwt_algorithm: str
    access_token_expire_minutes: int
    password_hash_iterations: int
    internal_api_key: str

    # Where the Ride Service finds the services it depends on.
    fare_service_url: str
    driver_service_url: str
    service_timeout_seconds: float

    # Pricing (Fare Service)
    base_fare: float
    per_km_rate: float
    minimum_fare: float
    currency: str

    # Matching (Driver Service)
    max_driver_search_km: float


@lru_cache
def get_settings() -> Settings:
    """Read settings once and cache them for the life of the process."""
    settings = Settings(
        mongodb_uri=_str("MONGODB_URI", "mongodb://127.0.0.1:27017"),
        user_db_name=_str("USER_DB_NAME", "rideflow_users"),
        driver_db_name=_str("DRIVER_DB_NAME", "rideflow_drivers"),
        ride_db_name=_str("RIDE_DB_NAME", "rideflow_rides"),
        jwt_secret_key=_required("JWT_SECRET_KEY"),
        jwt_algorithm=_str("JWT_ALGORITHM", "HS256"),
        access_token_expire_minutes=_int("ACCESS_TOKEN_EXPIRE_MINUTES", 60),
        password_hash_iterations=_int("PASSWORD_HASH_ITERATIONS", 600_000),
        internal_api_key=_required("INTERNAL_API_KEY"),
        fare_service_url=_str("FARE_SERVICE_URL", "http://127.0.0.1:8004"),
        driver_service_url=_str("DRIVER_SERVICE_URL", "http://127.0.0.1:8002"),
        service_timeout_seconds=_float("SERVICE_TIMEOUT_SECONDS", 5.0),
        base_fare=_float("BASE_FARE", 50.0),
        per_km_rate=_float("PER_KM_RATE", 12.0),
        minimum_fare=_float("MINIMUM_FARE", 80.0),
        currency=_str("CURRENCY", "INR"),
        max_driver_search_km=_float("MAX_DRIVER_SEARCH_KM", 10.0),
    )
    _validate(settings)
    return settings


def _validate(settings: Settings) -> None:
    if len(settings.jwt_secret_key) < MIN_SECRET_LENGTH:
        raise RuntimeError(
            f"JWT_SECRET_KEY must be at least {MIN_SECRET_LENGTH} characters. Generate one with: "
            'python -c "import secrets; print(secrets.token_urlsafe(48))"'
        )
    if settings.password_hash_iterations < 1:
        raise RuntimeError("PASSWORD_HASH_ITERATIONS must be positive.")
    for name in ("base_fare", "per_km_rate", "minimum_fare"):
        if getattr(settings, name) < 0:
            raise RuntimeError(f"{name.upper()} cannot be negative.")
    if settings.max_driver_search_km <= 0:
        raise RuntimeError("MAX_DRIVER_SEARCH_KM must be greater than zero.")
