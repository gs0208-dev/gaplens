"""Builds access tokens by hand, so tests can make expired, forged and unsigned ones."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt

from app.core.config import get_settings

# Pass this as a claim value to leave that claim out of the token.
MISSING = object()


def _claims(overrides: dict[str, Any]) -> dict[str, Any]:
    settings = get_settings()
    now = datetime.now(UTC)
    claims: dict[str, Any] = {
        "sub": str(uuid.uuid4()),
        "role": "user",
        "iat": now,
        "exp": now + timedelta(minutes=15),
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
    }
    claims.update(overrides)
    return {name: value for name, value in claims.items() if value is not MISSING}


def make_token(*, key: str | None = None, algorithm: str = "HS256", **claim_overrides: Any) -> str:
    """A token signed with the app's real secret unless another key or algorithm is given."""
    signing_key = key if key is not None else get_settings().jwt_secret.get_secret_value()
    return jwt.encode(_claims(claim_overrides), signing_key, algorithm=algorithm)


def make_unsigned_token(**claim_overrides: Any) -> str:
    """A token with `alg: none`, which carries no signature at all."""
    return jwt.encode(_claims(claim_overrides), key=None, algorithm="none")
