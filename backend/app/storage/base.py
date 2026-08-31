"""Storage abstraction.

Raw datasets never live in PostgreSQL. They are written through a
:class:`StorageBackend`, which today is the local filesystem and tomorrow could
be S3 or any object store. Callers only ever see an opaque ``key`` string, so
adding a backend means implementing this interface and registering it in
``app.storage.get_storage`` — nothing else in the codebase changes.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import IO


class StorageBackend(ABC):
    """Content-addressed-ish blob storage for uploaded datasets."""

    @abstractmethod
    def save(self, key: str, stream: IO[bytes]) -> int:
        """Persist ``stream`` under ``key``. Returns the number of bytes written."""

    @abstractmethod
    def open(self, key: str) -> IO[bytes]:
        """Open the stored object for reading in binary mode."""

    @abstractmethod
    def delete(self, key: str) -> None:
        """Remove the stored object. Missing objects are not an error."""

    @abstractmethod
    def exists(self, key: str) -> bool:
        """True when an object is stored under ``key``."""

    @abstractmethod
    def local_path(self, key: str) -> Path | None:
        """A real filesystem path, when the backend has one.

        pandas reads a path far more efficiently than a file object, so the
        profiler uses this when available. Object-store backends return
        ``None`` and the caller falls back to :meth:`open`.
        """
