"""Reader registry.

Register a new format here and in ``app.data.formats.EXTENSION_MAP``; nothing
else in the pipeline needs to know it exists.
"""

from __future__ import annotations

from app.data.formats import FileFormat
from app.data.readers.base import DatasetReader, LoadResult
from app.data.readers.csv_reader import CsvReader
from app.data.readers.excel_reader import ExcelReader

READERS: dict[FileFormat, DatasetReader] = {
    FileFormat.CSV: CsvReader(),
    FileFormat.XLSX: ExcelReader(),
}

__all__ = ["READERS", "DatasetReader", "LoadResult", "get_reader"]


def get_reader(fmt: FileFormat) -> DatasetReader:
    reader = READERS.get(fmt)
    if reader is None:  # pragma: no cover - guarded by detect_format
        raise ValueError(f"No reader registered for format {fmt}")
    return reader
