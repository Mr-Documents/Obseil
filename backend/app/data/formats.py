"""Supported dataset formats and upload validation.

Adding a format means adding a member here plus a reader in
``app.data.readers`` — see CONTRIBUTING.md.
"""

from __future__ import annotations

import re
import unicodedata
from enum import StrEnum
from pathlib import PurePosixPath

from app.core.errors import UnsupportedMediaTypeError, ValidationError


class FileFormat(StrEnum):
    CSV = "csv"
    XLSX = "xlsx"


#: Extension -> format. The extension is a hint only; the reader is the
#: authority, because a file's name says nothing about its contents.
EXTENSION_MAP: dict[str, FileFormat] = {
    ".csv": FileFormat.CSV,
    ".tsv": FileFormat.CSV,
    ".txt": FileFormat.CSV,
    ".xlsx": FileFormat.XLSX,
    ".xlsm": FileFormat.XLSX,
}

SUPPORTED_EXTENSIONS = tuple(sorted(EXTENSION_MAP))

#: XLSX files are ZIP archives; CSV has no magic number worth checking.
_ZIP_MAGIC = b"PK\x03\x04"

_UNSAFE_CHARS = re.compile(r"[^\w.\- ]+", re.UNICODE)
_COLLAPSE_SEPARATORS = re.compile(r"[-\s]+")
MAX_DISPLAY_NAME_LENGTH = 120


def detect_format(filename: str) -> FileFormat:
    """Infer the format from the filename's extension.

    Raises ``UnsupportedMediaTypeError`` with the list of formats we do accept,
    because "unsupported file type" without that list is a dead end for users.
    """
    suffix = PurePosixPath(filename.replace("\\", "/")).suffix.lower()
    fmt = EXTENSION_MAP.get(suffix)
    if fmt is None:
        raise UnsupportedMediaTypeError(
            f"Obseil supports {', '.join(SUPPORTED_EXTENSIONS)} files. "
            f"“{sanitize_display_name(filename)}” is not one of them.",
            details={"supported_extensions": list(SUPPORTED_EXTENSIONS)},
        )
    return fmt


def sanitize_display_name(filename: str) -> str:
    """Reduce an uploaded filename to something safe to store and display.

    The result is never used as a path — storage keys are generated — but it is
    rendered in the UI and embedded in exported reports, so directory
    components, control characters and unicode tricks are stripped here.
    """
    # Take the basename under both separators: a Windows client sends "C:\a\b.csv".
    base = PurePosixPath(filename.replace("\\", "/")).name
    base = unicodedata.normalize("NFKC", base)
    base = "".join(char for char in base if char.isprintable())
    base = _UNSAFE_CHARS.sub("_", base).strip(" .")
    base = _COLLAPSE_SEPARATORS.sub(lambda match: match.group(0)[0], base)

    if not base:
        return "dataset"
    if len(base) > MAX_DISPLAY_NAME_LENGTH:
        stem, _, suffix = base.rpartition(".")
        keep = MAX_DISPLAY_NAME_LENGTH - len(suffix) - 1
        base = f"{stem[:keep]}.{suffix}" if stem and keep > 0 else base[:MAX_DISPLAY_NAME_LENGTH]
    return base


def validate_magic_bytes(head: bytes, fmt: FileFormat) -> None:
    """Cheap sanity check that the bytes match the claimed format.

    Catches the common cases — a renamed ``.xlsx``, a PDF or an image dropped
    into the upload zone — before pandas produces a cryptic parser error.
    """
    if fmt is FileFormat.XLSX:
        if not head.startswith(_ZIP_MAGIC):
            raise ValidationError(
                "That does not look like an Excel workbook. If it is really a CSV, "
                "rename it with a .csv extension and upload it again.",
                code="format_mismatch",
            )
        return

    # CSV: reject binary content. A NUL byte in the first block is the clearest
    # signal that this is not text at all.
    if b"\x00" in head:
        raise ValidationError(
            "That file appears to be binary, not a CSV. Check that you exported "
            "it as text with comma or tab separators.",
            code="format_mismatch",
        )
    if head.startswith(_ZIP_MAGIC):
        raise ValidationError(
            "That looks like an Excel workbook or a ZIP archive, not a CSV. "
            "Rename it with a .xlsx extension, or export it as CSV.",
            code="format_mismatch",
        )
