"""Storage backend selection."""

from __future__ import annotations

from functools import lru_cache

from app.core.config import settings
from app.storage.base import StorageBackend
from app.storage.local import LocalFileStorage

__all__ = ["LocalFileStorage", "StorageBackend", "get_storage"]


@lru_cache
def get_storage() -> StorageBackend:
    """Return the configured storage backend.

    Adding S3 means adding a branch here and a module beside ``local.py``.
    """
    if settings.storage_backend == "local":
        return LocalFileStorage(settings.storage_dir)
    raise ValueError(f"Unsupported storage backend: {settings.storage_backend}")
