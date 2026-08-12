"""Repositories package: base contract + SQLite/Postgres/InMemory backends."""

from __future__ import annotations

from vencertia.repositories.base import (
    EntityNotFoundError,
    EntityStoreMixin,
    PostgresDisabledError,
    Repository,
    StaleWriteError,
)
from vencertia.repositories.memory import InMemoryRepository
from vencertia.repositories.sqlite import SQLiteRepository

__all__ = [
    "EntityNotFoundError",
    "EntityStoreMixin",
    "InMemoryRepository",
    "PostgresDisabledError",
    "Repository",
    "SQLiteRepository",
    "StaleWriteError",
]
