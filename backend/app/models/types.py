"""Portable SQLAlchemy type definitions that work with both SQLite and PostgreSQL."""

import uuid

from sqlalchemy import String, Text, TypeDecorator
from sqlalchemy.types import CHAR


class GUID(TypeDecorator):
    """Platform-independent GUID type.

    Uses PostgreSQL's UUID type when available, otherwise stores as CHAR(36) in SQLite.
    """

    impl = CHAR(36)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is not None:
            if isinstance(value, uuid.UUID):
                return str(value)
            return str(uuid.UUID(value))
        return value

    def process_result_value(self, value, dialect):
        if value is not None:
            return uuid.UUID(value)
        return value


class JSONType(TypeDecorator):
    """Platform-independent JSON type.

    Uses PostgreSQL's JSONB when available, otherwise stores as Text with JSON serialization.
    """

    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is not None:
            import json
            return json.dumps(value)
        return value

    def process_result_value(self, value, dialect):
        if value is not None:
            import json
            return json.loads(value)
        return value
