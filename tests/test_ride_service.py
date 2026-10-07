import httpx
from fastapi.testclient import TestClient

from tests.conftest import INDIRANAGAR, MG_ROAD, auth, build_ride_app, make_token

RIDE = {"pickup": MG_ROAD, "dropoff": INDIRANAGAR}


def rider(user_id="rider-1"):
    return make_token(user_id, "rider", name="Asha")


def request_ride(ride_client, token=None):
    return ride_client.post("/rides", json=RIDE, headers=auth(token or rider()))


def driver_status(driver_client, token):
    return driver_client.get("/drivers/me", headers=auth(token)).json()


# --------------------------------------------------------------- happy path

def test_full_ride_lifecycle(ride_client, driver_client, online_driver):
    driver_id, driver_token = online_driver("driver-1")

    r = request_ride(ride_client)
    assert r.status_code == 201, r.text
    ride = r.json()
    assert ride["status"] == "driver_assigned"
    assert ride["driver"]["driver_id"] == driver_id
    assert ride["estimated_fare"] >= 80
    assert ride["currency"] == "INR"
    assert driver_status(driver_client, driver_token)["current_ride_id"] == ride["id"]

    for action, expected in [("accept", "accepted"), ("start", "in_progress"), ("complete", "completed")]:
        r = ride_client.post(f"/rides/{ride['id']}/{action}", headers=auth(driver_token))
        assert r.status_code == 200, r.text
        assert r.json()["status"] == expected

    final = r.json()
    assert [h["status"] for h in final["status_history"]] == [
        "driver_assigned", "accepted", "in_progress", "completed"
    ]
    # Driver is free again after completing.
    status = driver_status(driver_client, driver_token)
    assert status["is_available"] is True and status["current_ride_id"] is None
    # ...and has moved to where the trip ended.
    assert status["location"] == INDIRANAGAR


def test_trip_history_for_rider_and_driver(ride_client, online_driver):
    _, driver_token = online_driver("driver-1")
    ride_id = request_ride(ride_client).json()["id"]

    rider_history = ride_client.get("/rides/me", headers=auth(rider())).json()
    driver_history = ride_client.get("/rides/me", headers=auth(driver_token)).json()
    assert [r["id"] for r in rider_history] == [ride_id]
    assert [r["id"] for r in driver_history] == [ride_id]

    filtered = ride_client.get("/rides/me?status=completed", headers=auth(rider())).json()
    assert filtered == []
    assert ride_client.get("/rides/me?status=flying", headers=auth(rider())).status_code == 422


# --------------------------------------------------------------- validation

def test_identical_pickup_and_dropoff_is_rejected(ride_client):
    r = ride_client.post("/rides", json={"pickup": MG_ROAD, "dropoff": MG_ROAD}, headers=auth(rider()))
    assert r.status_code == 422


def test_drivers_cannot_request_rides(ride_client):
    r = request_ride(ride_client, make_token("driver-x", "driver"))
    assert r.status_code == 403


def test_requires_authentication(ride_client):
    assert ride_client.post("/rides", json=RIDE).status_code == 401


def test_no_available_driver(ride_client):
    r = request_ride(ride_client)
    assert r.status_code == 409
    assert "No drivers" in r.json()["detail"]


def test_rider_cannot_have_two_active_rides(ride_client, online_driver):
    online_driver("driver-1")
    online_driver("driver-2", plate="KA01AB9999")
    assert request_ride(ride_client).status_code == 201
    assert request_ride(ride_client).status_code == 409


# ------------------------------------------------------ status transitions

def test_cannot_skip_states(ride_client, online_driver):
    _, driver_token = online_driver("driver-1")
    ride_id = request_ride(ride_client).json()["id"]
    r = ride_client.post(f"/rides/{ride_id}/complete", headers=auth(driver_token))
    assert r.status_code == 409
    assert "driver_assigned" in r.json()["detail"]


def test_cannot_cancel_after_trip_started(ride_client, online_driver):
    _, driver_token = online_driver("driver-1")
    ride_id = request_ride(ride_client).json()["id"]
    ride_client.post(f"/rides/{ride_id}/accept", headers=auth(driver_token))
    ride_client.post(f"/rides/{ride_id}/start", headers=auth(driver_token))
    r = ride_client.post(f"/rides/{ride_id}/cancel", headers=auth(rider()))
    assert r.status_code == 409


def test_rider_cancel_releases_driver(ride_client, driver_client, online_driver):
    _, driver_token = online_driver("driver-1")
    ride_id = request_ride(ride_client).json()["id"]
    r = ride_client.post(
        f"/rides/{ride_id}/cancel", json={"reason": "Changed plans"}, headers=auth(rider())
    )
    assert r.status_code == 200
    assert r.json()["status"] == "cancelled"
    assert r.json()["cancel_reason"] == "Changed plans"
    status = driver_status(driver_client, driver_token)
    assert status["is_available"] is True
    assert status["location"] == MG_ROAD  # cancelled before moving: location unchanged

    # And the rider can now book again.
    assert request_ride(ride_client).status_code == 201


def test_cancel_without_body(ride_client, online_driver):
    _, driver_token = online_driver("driver-1")
    ride_id = request_ride(ride_client).json()["id"]
    r = ride_client.post(f"/rides/{ride_id}/cancel", headers=auth(driver_token))
    assert r.status_code == 200
    assert r.json()["cancel_reason"] is None


# ------------------------------------------------------------ authorisation

def test_other_users_cannot_see_or_act_on_a_ride(ride_client, online_driver):
    online_driver("driver-1")
    ride_id = request_ride(ride_client).json()["id"]
    stranger_rider = make_token("rider-2", "rider")
    stranger_driver = make_token("driver-2", "driver")

    assert ride_client.get(f"/rides/{ride_id}", headers=auth(stranger_rider)).status_code == 404
    assert ride_client.post(f"/rides/{ride_id}/accept", headers=auth(stranger_driver)).status_code == 404
    assert ride_client.post(f"/rides/{ride_id}/cancel", headers=auth(stranger_rider)).status_code == 404
    # A rider can't perform driver actions, even on their own ride.
    assert ride_client.post(f"/rides/{ride_id}/accept", headers=auth(rider())).status_code == 403


def test_unknown_ride(ride_client):
    assert ride_client.get("/rides/does-not-exist", headers=auth(rider())).status_code == 404


# ---------------------------------------------- service communication errors

def _unreachable_client() -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    return httpx.Client(transport=httpx.MockTransport(handler), base_url="http://down")


def _failing_client(status_code: int) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, json={"detail": "boom"})

    return httpx.Client(transport=httpx.MockTransport(handler), base_url="http://broken")


def test_fare_service_down_returns_503(mongo, driver_client, online_driver):
    online_driver("driver-1")
    app = build_ride_app(mongo, _unreachable_client(), driver_client)
    try:
        r = request_ride(TestClient(app))
        assert r.status_code == 503
        assert "fare-service" in r.json()["detail"]
    finally:
        app.dependency_overrides.clear()


def test_driver_service_down_returns_503(mongo, fare_client):
    app = build_ride_app(mongo, fare_client, _unreachable_client())
    try:
        r = request_ride(TestClient(app))
        assert r.status_code == 503
        assert "driver-service" in r.json()["detail"]
    finally:
        app.dependency_overrides.clear()


def test_fare_service_error_returns_502(mongo, driver_client):
    app = build_ride_app(mongo, _failing_client(500), driver_client)
    try:
        assert request_ride(TestClient(app)).status_code == 502
    finally:
        app.dependency_overrides.clear()


def test_ride_completes_even_if_driver_release_fails(mongo, fare_client, driver_client, online_driver):
    """The ride's state is the source of truth; a failed release is logged, not fatal."""
    _, driver_token = online_driver("driver-1")
    app = build_ride_app(mongo, fare_client, driver_client)
    client = TestClient(app)
    ride_id = request_ride(client).json()["id"]
    client.post(f"/rides/{ride_id}/accept", headers=auth(driver_token))
    client.post(f"/rides/{ride_id}/start", headers=auth(driver_token))

    # Driver Service goes down before completion.
    app = build_ride_app(mongo, fare_client, _unreachable_client())
    try:
        r = TestClient(app).post(f"/rides/{ride_id}/complete", headers=auth(driver_token))
        assert r.status_code == 200
        assert r.json()["status"] == "completed"
    finally:
        app.dependency_overrides.clear()
