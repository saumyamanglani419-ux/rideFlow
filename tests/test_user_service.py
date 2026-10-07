from tests.conftest import auth

RIDER = {
    "email": "Asha@Example.com",
    "password": "supersecret1",
    "full_name": "Asha Rao",
    "phone": "+919876543210",
    "role": "rider",
}


def register(client, **overrides):
    return client.post("/auth/register", json={**RIDER, **overrides})


def login(client, email=RIDER["email"], password=RIDER["password"]):
    return client.post("/auth/login", json={"email": email, "password": password})


def test_health(user_client):
    assert user_client.get("/health").json() == {"service": "user-service", "status": "ok"}


def test_register_returns_public_profile_without_password(user_client):
    r = register(user_client)
    assert r.status_code == 201
    body = r.json()
    assert body["email"] == "asha@example.com"  # normalised to lowercase
    assert body["role"] == "rider"
    assert "password" not in body and "password_hash" not in body


def test_duplicate_email_is_rejected_case_insensitively(user_client):
    assert register(user_client).status_code == 201
    r = register(user_client, email="ASHA@example.COM")
    assert r.status_code == 409


def test_register_validation_errors(user_client):
    assert register(user_client, email="not-an-email").status_code == 422
    assert register(user_client, password="short").status_code == 422
    assert register(user_client, role="admin").status_code == 422
    assert register(user_client, phone="12ab").status_code == 422


def test_login_and_get_profile(user_client):
    register(user_client)
    r = login(user_client)
    assert r.status_code == 200
    token = r.json()["access_token"]
    assert r.json()["token_type"] == "bearer"
    assert r.json()["expires_in"] == 30 * 60

    me = user_client.get("/users/me", headers=auth(token))
    assert me.status_code == 200
    assert me.json()["full_name"] == "Asha Rao"


def test_login_failures_share_one_message(user_client):
    register(user_client)
    wrong_password = login(user_client, password="wrong-password")
    unknown_email = login(user_client, email="nobody@example.com")
    assert wrong_password.status_code == unknown_email.status_code == 401
    assert wrong_password.json()["detail"] == unknown_email.json()["detail"]


def test_protected_endpoint_requires_valid_token(user_client):
    assert user_client.get("/users/me").status_code == 401
    assert user_client.get("/users/me", headers=auth("garbage.token.value")).status_code == 401


def test_update_profile(user_client):
    register(user_client)
    token = login(user_client).json()["access_token"]
    r = user_client.patch("/users/me", json={"full_name": "Asha R."}, headers=auth(token))
    assert r.status_code == 200
    assert r.json()["full_name"] == "Asha R."
    assert r.json()["phone"] == RIDER["phone"]  # untouched


def test_update_profile_requires_a_field(user_client):
    register(user_client)
    token = login(user_client).json()["access_token"]
    assert user_client.patch("/users/me", json={}, headers=auth(token)).status_code == 400


def test_password_whitespace_is_preserved_but_other_fields_are_trimmed(user_client):
    r = register(user_client, email="  padded@example.com ", full_name="  Asha Rao  ", password=" spaced pass ")
    assert r.status_code == 201, r.text
    assert r.json()["email"] == "padded@example.com"
    assert r.json()["full_name"] == "Asha Rao"
    # The password is exactly what the user typed, spaces included.
    assert login(user_client, email="padded@example.com", password=" spaced pass ").status_code == 200
    assert login(user_client, email="padded@example.com", password="spaced pass").status_code == 401
