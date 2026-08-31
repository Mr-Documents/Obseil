"""Upload intake: validate, size-limit and persist an incoming file.

Kept separate from ``dataset_service`` because it is the security-sensitive
part of the request path and benefits from being small enough to read in one
sitting.
"""

from __future__ import annotations

import hashlib
import logging
import tempfile
import uuid
from dataclasses import dataclass
from typing import IO

from app.core.config import settings
from app.core.errors import PayloadTooLargeError, ValidationError
from app.data.formats import FileFormat, detect_format, sanitize_display_name, validate_magic_bytes
from app.storage import get_storage

logger = logging.getLogger(__name__)

CHUNK_SIZE = 1024 * 1024
#: Enough to cover any magic number we check plus a useful text sample.
MAGIC_BYTES_SAMPLE = 8192


@dataclass(slots=True)
class StoredUpload:
    display_name: str
    original_filename: str
    file_format: FileFormat
    storage_key: str
    size_bytes: int
    checksum_sha256: str


def _storage_key(project_id: str, fmt: FileFormat) -> str:
    """Generate the storage key.

    Derived entirely from server-side values: the user's filename never
    influences where bytes land, which removes path traversal from the threat
    model rather than trying to sanitise it away.
    """
    return f"projects/{project_id}/{uuid.uuid4().hex}.{fmt.value}"


def store_upload(*, project_id: str, filename: str, stream: IO[bytes]) -> StoredUpload:
    """Validate and persist an uploaded file.

    The file is streamed to a temporary file first so that the size limit is
    enforced as the bytes arrive - an oversized upload never reaches permanent
    storage, and a rejected upload leaves nothing behind.
    """
    display_name = sanitize_display_name(filename)
    file_format = detect_format(filename)

    digest = hashlib.sha256()
    size = 0
    head = b""

    with tempfile.TemporaryFile() as buffer:
        while chunk := stream.read(CHUNK_SIZE):
            size += len(chunk)
            if size > settings.max_upload_bytes:
                limit_mb = settings.max_upload_bytes / (1024 * 1024)
                raise PayloadTooLargeError(
                    f"“{display_name}” is larger than the {limit_mb:.0f} MB upload limit.",
                    details={"max_bytes": settings.max_upload_bytes},
                )
            if len(head) < MAGIC_BYTES_SAMPLE:
                head += chunk[: MAGIC_BYTES_SAMPLE - len(head)]
            digest.update(chunk)
            buffer.write(chunk)

        if size == 0:
            raise ValidationError(
                f"“{display_name}” is empty. Upload a file that contains data.",
                code="dataset_empty",
            )

        validate_magic_bytes(head, file_format)

        buffer.seek(0)
        storage_key = _storage_key(project_id, file_format)
        get_storage().save(storage_key, buffer)

    logger.info(
        "Stored upload",
        extra={"project_id": project_id, "storage_key": storage_key, "size_bytes": size},
    )
    return StoredUpload(
        display_name=display_name,
        original_filename=display_name,
        file_format=file_format,
        storage_key=storage_key,
        size_bytes=size,
        checksum_sha256=digest.hexdigest(),
    )
