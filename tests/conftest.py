"""
Shared pytest fixtures.

Tests never touch a real MongoDB or open real network connections:
  * mongomock provides an in-memory, PyMongo-compatible database.
  * FastAPI's dependency_overrides swaps each service's get_db for it.
  * The Ride Service talks to the *real* Fare and Driver apps through
    FastAPI TestClients, so service-to-service calls are genuinely tested.
"""

import os

# Must be set BEFORE any project module reads settings. Real env vars take
# priority over a developer's .env file, so tests are always deterministic.
TEST_ENV = {
    "JWT_SECRET_KEY": "test-secret-key-that-is-definitely-longer-than-32-chars",
    "JWT_ALGORITHM": "HS256",
    "ACCESS_TOKEN_EXPIRE_MINUTES": "30",
    "PASSWORD_HASH_ITERATIONS": "1000",  # fast hashing in tests only
    "INTERNAL_API_KEY": "test-internal-key",
    "BASE_FARE": "50",
    "PER_KM_RATE": "12",
    "MINIMUM_FARE": "80",
    "CURRENCY": "INR",
    "MAX_DRIVER_SEARCH_KM": "10",
}
os.environ.update(TEST_ENV)

import mongomock  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from shared.config import get_settings  # noqa: E402
from shared.security import create_access_token  # noqa: E402

get_settings.cache_clear()

# Handy coordinates (central Bengaluru), roughly 1-4 km apart.
MG_ROAD = {"latitude": 12.9758, "longitude": 77.6050}
INDIRANAGAR = {"latitude": 12.9784, "longitude": 77.6408}
KORAMANGALA = {"latitude": 12.9352, "longitude": 77.6245}
FAR_AWAY = {"latitude": 13.3409, "longitude": 77.1010}  # ~65 km away


def make_token(user_id: str, role: str, name: str = "Test User", email: str | None = None) -> str:
    settings = get_settings()
    return create_access_token(
        user_id=user_id,
        role=role,
        email=email or f"{user_id}@example.com",
        full_name=name,
        secret_key=settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
        expires_minutes=30,
    )


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def mongo():
    client = mongomock.MongoClient()
    yield client
    client.close()


@pytest.fixture
def user_app(mongo):
    from services.user_service.database import get_db
    from services.user_service.main import app
    from services.user_service.repository import ensure_indexes

    db = mongo["test_users"]
    ensure_indexes(db)
    app.dependency_overrides[get_db] = lambda: db
    yield app
    app.dependency_overrides.clear()


@pytest.fixture
def driver_app(mongo):
    from services.driver_service.database import get_db
    from services.driver_service.main import app
    from services.driver_service.repository import ensure_indexes

    db = mongo["test_drivers"]
    ensure_indexes(db)
    app.dependency_overrides[get_db] = lambda: db
    yield app
    app.dependency_overrides.clear()


@pytest.fixture
def fare_app():
    from services.fare_service.main import app

    yield app


@pytest.fixture
def user_client(user_app):
    return TestClient(user_app)


@pytest.fixture
def driver_client(driver_app):
    return TestClient(driver_app)


@pytest.fixture
def fare_client(fare_app):
    return TestClient(fare_app)


def build_ride_app(mongo, fare_http, driver_http):
    """Wire the Ride Service to the given HTTP clients for its dependencies."""
    from services.ride_service.clients import (
        DriverClient,
        FareClient,
        get_driver_client,
        get_fare_client,
    )
    from services.ride_service.database import get_db
    from services.ride_service.main import app
    from services.ride_service.repository import ensure_indexes
    from shared.service_client import ServiceClient

    db = mongo["test_rides"]
    ensure_indexes(db)
    fare = FareClient(ServiceClient("fare-service", http_client=fare_http))
    drivers = DriverClient(
        ServiceClient(
            "driver-service",
            http_client=driver_http,
            default_headers={"X-Internal-API-Key": TEST_ENV["INTERNAL_API_KEY"]},
        )
    )
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_fare_client] = lambda: fare
    app.dependency_overrides[get_driver_client] = lambda: drivers
    return app


@pytest.fixture
def ride_client(mongo, fare_client, driver_client):
    app = build_ride_app(mongo, fare_client, driver_client)
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def online_driver(driver_client):
    """Create a driver profile at MG Road and put them online. Returns (id, token)."""

    def _make(driver_id: str = "driver-1", location=MG_ROAD, plate: str = "KA01AB1234"):
        token = make_token(driver_id, "driver", name=f"Driver {driver_id}")
        r = driver_client.post(
            "/drivers/me",
            json={"vehicle_model": "Maruti Dzire", "license_plate": plate, "location": location},
            headers=auth(token),
        )
        assert r.status_code == 201, r.text
        r = driver_client.patch(
            "/drivers/me/availability", json={"is_available": True}, headers=auth(token)
        )
        assert r.status_code == 200, r.text
        return driver_id, token

    return _make
