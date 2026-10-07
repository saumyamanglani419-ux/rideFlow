from tests.conftest import FAR_AWAY, INDIRANAGAR, KORAMANGALA, MG_ROAD, auth, make_token

INTERNAL = {"X-Internal-API-Key": "test-internal-key"}
PROFILE = {"vehicle_model": "Maruti Dzire", "license_plate": "ka01ab1234", "location": MG_ROAD}


def test_rider_cannot_create_driver_profile(driver_client):
    token = make_token("rider-1", "rider")
    r = driver_client.post("/drivers/me", json=PROFILE, headers=auth(token))
    assert r.status_code == 403


def test_create_profile_starts_offline_and_normalises_plate(driver_client):
    token = make_token("driver-1", "driver", name="Ravi")
    r = driver_client.post("/drivers/me", json=PROFILE, headers=auth(token))
    assert r.status_code == 201
    body = r.json()
    assert body["id"] == "driver-1"
    assert body["full_name"] == "Ravi"
    assert body["license_plate"] == "KA01AB1234"
    assert body["is_available"] is False


def test_duplicate_profile_and_duplicate_plate(driver_client):
    t1 = make_token("driver-1", "driver")
    t2 = make_token("driver-2", "driver")
    assert driver_client.post("/drivers/me", json=PROFILE, headers=auth(t1)).status_code == 201
    assert driver_client.post("/drivers/me", json=PROFILE, headers=auth(t1)).status_code == 409
    r = driver_client.post("/drivers/me", json=PROFILE, headers=auth(t2))
    assert r.status_code == 409
    assert "plate" in r.json()["detail"]


def test_invalid_plate_is_rejected(driver_client):
    token = make_token("driver-1", "driver")
    r = driver_client.post("/drivers/me", json={**PROFILE, "license_plate": "@@"}, headers=auth(token))
    assert r.status_code == 422


def test_availability_requires_profile(driver_client):
    token = make_token("driver-1", "driver")
    r = driver_client.patch("/drivers/me/availability", json={"is_available": True}, headers=auth(token))
    assert r.status_code == 404


def test_go_online_and_appear_in_available_list(driver_client, online_driver):
    online_driver("driver-1")
    rider = make_token("rider-1", "rider")
    r = driver_client.get("/drivers/available", headers=auth(rider))
    assert r.status_code == 200
    assert [d["driver_id"] for d in r.json()] == ["driver-1"]
    assert "license_plate" not in r.json()[0]


def test_internal_endpoints_require_internal_key(driver_client, online_driver):
    online_driver("driver-1")
    body = {"ride_id": "ride-1", "pickup": MG_ROAD}
    assert driver_client.post("/internal/drivers/assign", json=body).status_code == 403
    r = driver_client.post(
        "/internal/drivers/assign", json=body, headers={"X-Internal-API-Key": "wrong"}
    )
    assert r.status_code == 403


def test_assign_picks_nearest_driver_and_marks_them_busy(driver_client, online_driver):
    online_driver("near", location=MG_ROAD, plate="KA01AA0001")
    online_driver("further", location=KORAMANGALA, plate="KA01AA0002")

    r = driver_client.post(
        "/internal/drivers/assign",
        json={"ride_id": "ride-1", "pickup": INDIRANAGAR},
        headers=INTERNAL,
    )
    assert r.status_code == 200
    assert r.json()["driver_id"] == "near"

    # The reserved driver is no longer available, so the next ride gets the other one.
    r2 = driver_client.post(
        "/internal/drivers/assign",
        json={"ride_id": "ride-2", "pickup": INDIRANAGAR},
        headers=INTERNAL,
    )
    assert r2.json()["driver_id"] == "further"

    # Nobody left.
    r3 = driver_client.post(
        "/internal/drivers/assign",
        json={"ride_id": "ride-3", "pickup": INDIRANAGAR},
        headers=INTERNAL,
    )
    assert r3.status_code == 404


def test_assign_ignores_drivers_outside_search_radius(driver_client, online_driver):
    online_driver("far", location=FAR_AWAY)
    r = driver_client.post(
        "/internal/drivers/assign",
        json={"ride_id": "ride-1", "pickup": MG_ROAD},
        headers=INTERNAL,
    )
    assert r.status_code == 404


def test_busy_driver_cannot_toggle_availability_until_released(driver_client, online_driver):
    driver_id, token = online_driver("driver-1")
    driver_client.post(
        "/internal/drivers/assign", json={"ride_id": "ride-1", "pickup": MG_ROAD}, headers=INTERNAL
    )
    r = driver_client.patch("/drivers/me/availability", json={"is_available": False}, headers=auth(token))
    assert r.status_code == 409

    # Releasing for the wrong ride does nothing; the right ride frees the driver.
    wrong = driver_client.post(
        f"/internal/drivers/{driver_id}/release", json={"ride_id": "other"}, headers=INTERNAL
    )
    assert wrong.json()["released"] is False
    ok = driver_client.post(
        f"/internal/drivers/{driver_id}/release", json={"ride_id": "ride-1"}, headers=INTERNAL
    )
    assert ok.json()["released"] is True
    # Releasing again is harmless (idempotent).
    again = driver_client.post(
        f"/internal/drivers/{driver_id}/release", json={"ride_id": "ride-1"}, headers=INTERNAL
    )
    assert again.status_code == 200 and again.json()["released"] is False

    me = driver_client.get("/drivers/me", headers=auth(token)).json()
    assert me["is_available"] is True and me["current_ride_id"] is None


def test_release_unknown_driver(driver_client):
    r = driver_client.post("/internal/drivers/nope/release", json={"ride_id": "x"}, headers=INTERNAL)
    assert r.status_code == 404


def test_release_can_move_driver_to_new_location(driver_client, online_driver):
    driver_id, token = online_driver("driver-1", location=MG_ROAD)
    driver_client.post(
        "/internal/drivers/assign", json={"ride_id": "ride-1", "pickup": MG_ROAD}, headers=INTERNAL
    )
    r = driver_client.post(
        f"/internal/drivers/{driver_id}/release",
        json={"ride_id": "ride-1", "location": KORAMANGALA},
        headers=INTERNAL,
    )
    assert r.json()["released"] is True
    assert driver_client.get("/drivers/me", headers=auth(token)).json()["location"] == KORAMANGALA
