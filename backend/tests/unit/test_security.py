from argon2 import PasswordHasher

from app.core.security import hash_password

SAMPLE_PHRASE = "correct horse battery"


def test_hash_is_argon2id_and_verifies_against_the_original() -> None:
    hashed = hash_password(SAMPLE_PHRASE)

    assert hashed.startswith("$argon2id$")
    assert PasswordHasher().verify(hashed, SAMPLE_PHRASE)


def test_hash_does_not_contain_the_password() -> None:
    assert SAMPLE_PHRASE not in hash_password(SAMPLE_PHRASE)


def test_same_password_gets_a_different_hash_each_time() -> None:
    assert hash_password(SAMPLE_PHRASE) != hash_password(SAMPLE_PHRASE)
