import hashlib
import uuid

import jwt
from argon2 import PasswordHasher

from app.core.config import get_settings
from app.core.security import (
    DUMMY_PASSWORD_HASH,
    create_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)

SAMPLE_PHRASE = "correct horse battery"


def test_hash_is_argon2id_and_verifies_against_the_original() -> None:
    hashed = hash_password(SAMPLE_PHRASE)

    assert hashed.startswith("$argon2id$")
    assert PasswordHasher().verify(hashed, SAMPLE_PHRASE)


def test_hash_does_not_contain_the_password() -> None:
    assert SAMPLE_PHRASE not in hash_password(SAMPLE_PHRASE)


def test_same_password_gets_a_different_hash_each_time() -> None:
    assert hash_password(SAMPLE_PHRASE) != hash_password(SAMPLE_PHRASE)


def test_verify_password_accepts_the_right_password_and_rejects_others() -> None:
    hashed = hash_password(SAMPLE_PHRASE)

    assert verify_password(hashed, SAMPLE_PHRASE) is True
    assert verify_password(hashed, "wrong horse battery") is False


def test_dummy_hash_is_a_real_argon2id_hash_that_matches_no_real_password() -> None:
    assert DUMMY_PASSWORD_HASH.startswith("$argon2id$")
    assert verify_password(DUMMY_PASSWORD_HASH, SAMPLE_PHRASE) is False


def test_access_token_has_the_documented_claims_and_lifetime() -> None:
    settings = get_settings()
    user_id = uuid.uuid4()

    token = create_access_token(user_id, "admin")

    claims = jwt.decode(
        token,
        settings.jwt_secret.get_secret_value(),
        algorithms=["HS256"],
        audience=settings.jwt_audience,
        issuer=settings.jwt_issuer,
    )
    assert claims["sub"] == str(user_id)
    assert claims["role"] == "admin"
    assert claims["exp"] - claims["iat"] == settings.access_token_minutes * 60


def test_access_token_uses_the_hs256_algorithm() -> None:
    token = create_access_token(uuid.uuid4(), "user")

    assert jwt.get_unverified_header(token)["alg"] == "HS256"


def test_refresh_tokens_are_long_and_never_repeat() -> None:
    tokens = {generate_refresh_token() for _ in range(50)}

    assert len(tokens) == 50
    assert all(len(token) >= 43 for token in tokens)


def test_refresh_token_hash_is_sha256_hex() -> None:
    token = generate_refresh_token()

    assert hash_refresh_token(token) == hashlib.sha256(token.encode()).hexdigest()
    assert token not in hash_refresh_token(token)
