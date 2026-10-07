"""
One realistic journey through all four services, using tokens issued by the
real User Service. This proves the services agree on the JWT format.
"""

from tests.conftest import INDIRANAGAR, MG_ROAD, auth


def _register_and_login(user_client, email, role, name):
    r = user_client.post(
        "/auth/register",
        json={"email": email, "password": "password123", "full_name": name, "role": role},
    )
    assert r.status_code == 201, r.text
    r = user_client.post("/auth/login", json={"email": email, "password": "password123"})
    assert r.status_code == 200, r.text
    return r.json()["access_token"], r.json()


def test_rider_books_and_completes_a_trip(user_client, driver_client, ride_client, fare_client):
    rider_token, _ = _register_and_login(user_client, "asha@example.com", "rider", "Asha Rao")
    driver_token, _ = _register_and_login(user_client, "ravi@example.com", "driver", "Ravi Kumar")
    driver_id = user_client.get("/users/me", headers=auth(driver_token)).json()["id"]

    # Driver sets up their vehicle and goes online.
    r = driver_client.post(
        "/drivers/me",
        json={"vehicle_model": "Hyundai Aura", "license_plate": "KA05MN4321", "location": MG_ROAD},
        headers=auth(driver_token),
    )
    assert r.status_code == 201, r.text
    assert r.json()["full_name"] == "Ravi Kumar"  # name came from the JWT
    driver_client.patch("/drivers/me/availability", json={"is_available": True}, headers=auth(driver_token))

    # Rider checks the price, then books.
    quote = fare_client.post("/fares/estimate", json={"pickup": MG_ROAD, "dropoff": INDIRANAGAR}).json()
    r = ride_client.post("/rides", json={"pickup": MG_ROAD, "dropoff": INDIRANAGAR}, headers=auth(rider_token))
    assert r.status_code == 201, r.text
    ride = r.json()
    assert ride["driver"]["driver_id"] == driver_id
    assert ride["estimated_fare"] == quote["estimated_fare"]
    assert ride["rider_name"] == "Asha Rao"

    # Driver finds the new ride, then drives it.
    pending = ride_client.get("/rides/me?status=driver_assigned", headers=auth(driver_token)).json()
    assert [p["id"] for p in pending] == [ride["id"]]
    for action in ("accept", "start", "complete"):
        assert ride_client.post(f"/rides/{ride['id']}/{action}", headers=auth(driver_token)).status_code == 200

    history = ride_client.get("/rides/me", headers=auth(rider_token)).json()
    assert history[0]["status"] == "completed"
    assert driver_client.get("/drivers/me", headers=auth(driver_token)).json()["is_available"] is True
