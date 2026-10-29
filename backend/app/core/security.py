import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from app.core.config import get_settings

# Library defaults: argon2id, 64 MiB of memory, 3 passes, 4 lanes. Time one hash on the deploy
# instance and adjust only if it is far from 50 to 100 ms (docs/security.md).
_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    """Return an argon2id hash with a random salt. CPU heavy, so call it off the event loop."""
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    """CPU heavy like hash_password. Only a wrong password returns False; a malformed stored
    hash raises, because that is corrupt data and should not be mistaken for a mismatch."""
    try:
        return _hasher.verify(password_hash, password)
    except VerifyMismatchError:
        return False


# Verified against when the email is unknown, so an unknown email costs as much time as a wrong
# password and response time does not reveal which emails have accounts.
DUMMY_PASSWORD_HASH = hash_password(secrets.token_urlsafe(16))


def create_access_token(user_id: uuid.UUID, role: str) -> str:
    settings = get_settings()
    issued_at = datetime.now(UTC)
    claims = {
        "sub": str(user_id),
        "role": role,
        "iat": issued_at,
        "exp": issued_at + timedelta(minutes=settings.access_token_minutes),
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
    }
    return jwt.encode(claims, settings.jwt_secret.get_secret_value(), algorithm="HS256")


def generate_refresh_token() -> str:
    """An opaque 256-bit random value. It carries no information and is only a lookup key."""
    return secrets.token_urlsafe(32)


def hash_refresh_token(token: str) -> str:
    # Plain SHA-256 is enough here, unlike for passwords: the input is 256 random bits, so it
    # cannot be guessed, and lookups need a fast, repeatable hash.
    return hashlib.sha256(token.encode()).hexdigest()
