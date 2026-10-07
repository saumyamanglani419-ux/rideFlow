from tests.conftest import INDIRANAGAR, MG_ROAD


def test_rates(fare_client):
    assert fare_client.get("/fares/rates").json() == {
        "base_fare": 50.0,
        "per_km_rate": 12.0,
        "minimum_fare": 80.0,
        "currency": "INR",
    }


def test_estimate(fare_client):
    r = fare_client.post("/fares/estimate", json={"pickup": MG_ROAD, "dropoff": INDIRANAGAR})
    assert r.status_code == 200
    body = r.json()
    assert 3.5 < body["distance_km"] < 4.5
    assert body["estimated_fare"] == round(max(50 + body["distance_km"] * 12, 80), 2)
    assert body["currency"] == "INR"


def test_estimate_rejects_invalid_coordinates(fare_client):
    bad = {"latitude": 123, "longitude": 77.6}
    r = fare_client.post("/fares/estimate", json={"pickup": bad, "dropoff": INDIRANAGAR})
    assert r.status_code == 422
