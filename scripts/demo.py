"""
Walk through a complete ride against the RUNNING services.

    python scripts/demo.py

Start all four services first. Safe to re-run:
  * a fresh rider and driver are created each run (random emails/plates),
  * the pickup point is nudged slightly each run, so drivers left online by
    earlier runs or manual testing are never closer than the demo driver,
  * the demo driver goes offline at the end so it can't be matched later.
"""

import random
import sys

import httpx

USER = "http://127.0.0.1:8001"
DRIVER = "http://127.0.0.1:8002"
RIDE = "http://127.0.0.1:8003"
FARE = "http://127.0.0.1:8004"

# Central Bengaluru, nudged by up to ~1 km per run (see docstring).
PICKUP = {
    "latitude": round(12.9758 + random.uniform(-0.01, 0.01), 6),
    "longitude": round(77.6050 + random.uniform(-0.01, 0.01), 6),
}
DROPOFF = {"latitude": 12.9784, "longitude": 77.6408}


def check(response: httpx.Response, step: str) -> dict:
    if response.is_error:
        print(f"FAILED at '{step}': HTTP {response.status_code} {response.text}")
        sys.exit(1)
    print(f"  ok  {step}")
    return response.json()


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def signup(client: httpx.Client, role: str, name: str) -> str:
    email = f"{role}{random.randint(10_000, 99_999)}@example.com"
    body = {"email": email, "password": "password123", "full_name": name, "role": role}
    check(client.post(f"{USER}/auth/register", json=body), f"register {role} {email}")
    token = check(
        client.post(f"{USER}/auth/login", json={"email": email, "password": "password123"}),
        f"login {role}",
    )["access_token"]
    return token


def main() -> None:
    with httpx.Client(timeout=10) as client:
        try:
            for url in (USER, DRIVER, RIDE, FARE):
                client.get(f"{url}/health").raise_for_status()
        except httpx.HTTPError:
            print("Could not reach all services. Start them first (see README).")
            sys.exit(1)

        print("1. Accounts")
        rider = signup(client, "rider", "Demo Rider")
        driver = signup(client, "driver", "Demo Driver")

        print("2. Driver goes online")
        plate = f"KA01DM{random.randint(1000, 9999)}"
        profile = check(
            client.post(
                f"{DRIVER}/drivers/me",
                json={"vehicle_model": "Maruti Dzire", "license_plate": plate, "location": PICKUP},
                headers=bearer(driver),
            ),
            "create driver profile",
        )
        check(
            client.patch(
                f"{DRIVER}/drivers/me/availability", json={"is_available": True}, headers=bearer(driver)
            ),
            "go online",
        )

        try:
            run_trip(client, rider, driver, profile["id"])
        finally:
            # Best effort: take the demo driver offline so later runs don't match them.
            client.patch(
                f"{DRIVER}/drivers/me/availability", json={"is_available": False}, headers=bearer(driver)
            )


def run_trip(client: httpx.Client, rider: str, driver: str, driver_id: str) -> None:
    print("3. Rider gets a quote and books")
    quote = check(
        client.post(f"{FARE}/fares/estimate", json={"pickup": PICKUP, "dropoff": DROPOFF}),
        "fare estimate",
    )
    print(f"      {quote['distance_km']} km -> {quote['estimated_fare']} {quote['currency']}")
    ride = check(
        client.post(f"{RIDE}/rides", json={"pickup": PICKUP, "dropoff": DROPOFF}, headers=bearer(rider)),
        "request ride",
    )
    print(f"      ride {ride['id']} assigned to {ride['driver']['full_name']}")
    if ride["driver"]["driver_id"] != driver_id:
        print(
            "\nAnother online driver was closer and got this ride, so the demo driver\n"
            "can't accept it. Take other test drivers offline (or cancel the ride)\n"
            "and run the demo again."
        )
        check(client.post(f"{RIDE}/rides/{ride['id']}/cancel", headers=bearer(rider)), "cancel ride")
        sys.exit(1)

    print("4. Driver completes the trip")
    for action in ("accept", "start", "complete"):
        ride = check(client.post(f"{RIDE}/rides/{ride['id']}/{action}", headers=bearer(driver)), action)

    print("5. Trip history")
    history = check(client.get(f"{RIDE}/rides/me", headers=bearer(rider)), "rider history")
    print(f"      latest ride status: {history[0]['status']}")
    print("\nDemo finished successfully.")


if __name__ == "__main__":
    main()
