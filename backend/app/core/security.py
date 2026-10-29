from argon2 import PasswordHasher

# Library defaults: argon2id, 64 MiB of memory, 3 passes, 4 lanes. Time one hash on the deploy
# instance and adjust only if it is far from 50 to 100 ms (docs/security.md).
_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    """Return an argon2id hash with a random salt. CPU heavy, so call it off the event loop."""
    return _hasher.hash(password)
