from datetime import datetime, timedelta, timezone

import jwt
import pytest

from shared.security import (
    TokenError,
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)

SECRET = "unit-test-secret-key-that-is-long-enough-123"


def test_password_hash_roundtrip():
    stored = hash_password("correct horse battery", iterations=1000)
    assert stored.startswith("pbkdf2_sha256$1000$")
    assert "correct horse battery" not in stored
    assert verify_password("correct horse battery", stored)


def test_wrong_password_is_rejected():
    stored = hash_password("s3cret-pass", iterations=1000)
    assert not verify_password("s3cret-pasS", stored)


def test_same_password_gets_different_hashes_because_of_salt():
    assert hash_password("same-password", 1000) != hash_password("same-password", 1000)


@pytest.mark.parametrize(
    "garbage",
    ["", "not-a-hash", "md5$1$abc$def", "pbkdf2_sha256$abc$xx$yy", "pbkdf2_sha256$0$AAAA$AAAA",
     "pbkdf2_sha256$1000$!!notbase64!!$AAAA"],
)
def test_malformed_hash_never_raises(garbage):
    assert verify_password("anything", garbage) is False


def _token(**overrides):
    params = dict(user_id="u1", role="rider", email="a@b.com", full_name="A", secret_key=SECRET)
    params.update(overrides)
    return create_access_token(**params)


def test_token_roundtrip():
    claims = decode_access_token(_token(), secret_key=SECRET)
    assert claims["sub"] == "u1"
    assert claims["role"] == "rider"
    assert claims["name"] == "A"


def test_expired_token_is_rejected():
    token = _token(expires_minutes=-1)
    with pytest.raises(TokenError, match="expired"):
        decode_access_token(token, secret_key=SECRET)


def test_token_signed_with_other_secret_is_rejected():
    token = _token(secret_key="another-secret-key-that-is-also-long-enough")
    with pytest.raises(TokenError):
        decode_access_token(token, secret_key=SECRET)


def test_tampered_token_is_rejected():
    header, payload, signature = _token().split(".")
    flipped = signature[:-2] + ("AA" if signature[-2:] != "AA" else "BB")
    with pytest.raises(TokenError):
        decode_access_token(f"{header}.{payload}.{flipped}", secret_key=SECRET)


def test_token_missing_role_is_rejected():
    payload = {"sub": "u1", "exp": datetime.now(timezone.utc) + timedelta(minutes=5)}
    token = jwt.encode(payload, SECRET, algorithm="HS256")
    with pytest.raises(TokenError):
        decode_access_token(token, secret_key=SECRET)
