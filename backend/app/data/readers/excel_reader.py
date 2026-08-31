"""XLSX reader.

Only the first worksheet is analysed in the MVP: a dataset is one table, and
silently concatenating sheets with different schemas would produce a profile
that describes nothing. The sheet name is recorded so the UI can say which one
was used.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from app.core.errors import DatasetError
from app.data.readers.base import DatasetReader, LoadResult, normalize_columns, validate_frame
from app.data.readers.csv_reader import NA_VALUES

logger = logging.getLogger(__name__)


class ExcelReader(DatasetReader):
    def load(self, path: Path, *, max_rows: int | None = None) -> LoadResult:
        try:
            workbook = pd.ExcelFile(path, engine="openpyxl")
        except ValueError as exc:
            raise DatasetError(
                "The workbook could not be opened. Only .xlsx and .xlsm files are supported "
                "- re-save an older .xls file in the newer format.",
                code="dataset_parse_error",
            ) from exc
        except Exception as exc:  # openpyxl raises a wide variety of types
            logger.exception("Unexpected failure opening workbook at %s", path)
            raise DatasetError(
                "The Excel file could not be read. It may be corrupted or password protected.",
                code="dataset_parse_error",
            ) from exc

        with workbook:
            if not workbook.sheet_names:
                raise DatasetError("The workbook has no worksheets.", code="dataset_empty")

            sheet_name = str(workbook.sheet_names[0])
            try:
                frame = workbook.parse(sheet_name=sheet_name, nrows=max_rows, na_values=NA_VALUES)
                total_rows = len(frame) if max_rows is None else len(workbook.parse(sheet_name))
            except Exception as exc:  # parser failures vary wildly by file
                logger.exception("Unexpected failure parsing worksheet %s", sheet_name)
                raise DatasetError(
                    f"Worksheet “{sheet_name}” could not be parsed.",
                    code="dataset_parse_error",
                ) from exc

        notes = normalize_columns(frame)
        validate_frame(frame, source=f"worksheet “{sheet_name}”")

        if len(workbook.sheet_names) > 1:
            notes.append(
                f"The workbook has {len(workbook.sheet_names)} sheets; "
                f"only “{sheet_name}” was analysed."
            )

        return LoadResult(
            frame=frame,
            total_rows=total_rows,
            sampled=max_rows is not None and total_rows > len(frame),
            sheet_name=sheet_name,
            notes=notes,
        )
