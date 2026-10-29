import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, EmailStr, StringConstraints


def _trim_and_lowercase(value: object) -> object:
    return value.strip().lower() if isinstance(value, str) else value


# email-validator, which EmailStr uses, already rejects addresses over 254 characters, the same
# limit as the CHECK constraint on users.email.
NormalizedEmail = Annotated[EmailStr, BeforeValidator(_trim_and_lowercase)]

# Length is the only password rule (docs/security.md). It is never trimmed or truncated.
Password = Annotated[str, StringConstraints(min_length=12, max_length=128)]


class RegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: NormalizedEmail
    password: Password


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    role: Literal["user", "admin"]
    created_at: datetime


class RegisterResponse(BaseModel):
    user: UserOut
