import uuid
from datetime import datetime
from typing import Any, ClassVar

from sqlalchemy import DateTime, MetaData, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# These patterns reproduce the names PostgreSQL gives unnamed constraints, so a hand-written
# migration and the models agree on every name. Check constraints are always named explicitly.
NAMING_CONVENTION = {
    "pk": "%(table_name)s_pkey",
    "fk": "%(table_name)s_%(column_0_name)s_fkey",
    "uq": "%(table_name)s_%(column_0_name)s_key",
    "ck": "%(table_name)s_%(constraint_name)s_check",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)

    type_annotation_map: ClassVar[dict[Any, Any]] = {
        datetime: DateTime(timezone=True),
        str: Text,
        uuid.UUID: UUID(as_uuid=True),
    }


class CreatedAtMixin:
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class UpdatedAtMixin:
    # Set by the application on every UPDATE, not by a trigger, so the behavior is visible in code.
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())
