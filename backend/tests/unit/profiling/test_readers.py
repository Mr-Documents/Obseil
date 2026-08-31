"""File format detection, filename safety and the CSV/XLSX readers."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from app.core.errors import DatasetError, UnsupportedMediaTypeError, ValidationError
from app.data.formats import FileFormat, detect_format, sanitize_display_name, validate_magic_bytes
from app.data.readers import get_reader
from app.data.readers.csv_reader import CsvReader, sniff_delimiter
from app.data.readers.excel_reader import ExcelReader
from tests.fixtures import sample_path


class TestFormatDetection:
    @pytest.mark.parametrize(
        ("filename", "expected"),
        [
            ("data.csv", FileFormat.CSV),
            ("DATA.CSV", FileFormat.CSV),
            ("export.tsv", FileFormat.CSV),
            ("book.xlsx", FileFormat.XLSX),
            ("macro.xlsm", FileFormat.XLSX),
        ],
    )
    def test_recognises_supported_extensions(self, filename: str, expected: FileFormat) -> None:
        assert detect_format(filename) is expected

    @pytest.mark.parametrize("filename", ["report.pdf", "archive.zip", "legacy.xls", "noext"])
    def test_rejects_everything_else(self, filename: str) -> None:
        with pytest.raises(UnsupportedMediaTypeError) as excinfo:
            detect_format(filename)
        # The error must say what *is* accepted, or the user is stuck.
        assert ".csv" in excinfo.value.message


class TestFilenameSanitisation:
    def test_strips_directory_components(self) -> None:
        assert sanitize_display_name("../../etc/passwd.csv") == "passwd.csv"
        assert sanitize_display_name(r"C:\Users\me\Desktop\data.csv") == "data.csv"

    def test_removes_traversal_and_separators(self) -> None:
        cleaned = sanitize_display_name("..%2f..%2fsecret.csv")
        assert "/" not in cleaned and "\\" not in cleaned

    def test_keeps_ordinary_names_readable(self) -> None:
        assert sanitize_display_name("Q1 transactions-2026.csv") == "Q1 transactions-2026.csv"

    def test_falls_back_when_nothing_survives(self) -> None:
        assert sanitize_display_name("...") == "dataset"

    def test_truncates_very_long_names(self) -> None:
        result = sanitize_display_name("x" * 400 + ".csv")
        assert len(result) <= 120
        assert result.endswith(".csv")


class TestMagicBytes:
    def test_accepts_a_real_zip_header_for_xlsx(self) -> None:
        validate_magic_bytes(b"PK\x03\x04rest", FileFormat.XLSX)

    def test_rejects_a_csv_renamed_to_xlsx(self) -> None:
        with pytest.raises(ValidationError, match="Excel workbook"):
            validate_magic_bytes(b"a,b,c\n1,2,3", FileFormat.XLSX)

    def test_rejects_an_xlsx_renamed_to_csv(self) -> None:
        with pytest.raises(ValidationError, match="Excel workbook or a ZIP"):
            validate_magic_bytes(b"PK\x03\x04rest", FileFormat.CSV)

    def test_rejects_binary_content_claiming_to_be_csv(self) -> None:
        with pytest.raises(ValidationError, match="binary"):
            validate_magic_bytes(b"\x89PNG\x00\x1a\n", FileFormat.CSV)


class TestDelimiterSniffing:
    @pytest.mark.parametrize(
        ("sample", "expected"),
        [
            ("a,b,c\n1,2,3\n4,5,6", ","),
            ("a;b;c\n1;2;3\n4;5;6", ";"),
            ("a\tb\tc\n1\t2\t3\n4\t5\t6", "\t"),
            ("a|b|c\n1|2|3\n4|5|6", "|"),
        ],
    )
    def test_detects_common_delimiters(self, sample: str, expected: str) -> None:
        assert sniff_delimiter(sample) == expected

    def test_defaults_to_comma_for_a_single_column(self) -> None:
        assert sniff_delimiter("value\n1\n2") == ","


class TestCsvReader:
    reader = CsvReader()

    def test_reads_a_sample_dataset(self) -> None:
        result = self.reader.load(sample_path("clean_transactions.csv"))

        assert result.frame.shape == (600, 10)
        assert result.total_rows == 600
        assert result.sampled is False
        assert result.delimiter == ","

    def test_reads_a_semicolon_file(self, tmp_path: Path) -> None:
        path = tmp_path / "euro.csv"
        path.write_text("name;amount\nada;12,5\nalan;3", encoding="utf-8")

        result = self.reader.load(path)

        assert list(result.frame.columns) == ["name", "amount"]
        assert result.delimiter == ";"

    def test_handles_an_excel_written_bom(self, tmp_path: Path) -> None:
        path = tmp_path / "bom.csv"
        path.write_bytes("\ufeffid,value\n1,2\n".encode())

        result = self.reader.load(path)

        assert list(result.frame.columns) == ["id", "value"], "the BOM must not join the header"
        assert result.encoding == "utf-8-sig"

    def test_falls_back_to_a_legacy_encoding(self, tmp_path: Path) -> None:
        path = tmp_path / "latin.csv"
        path.write_bytes("name,city\nJos\xe9,Malm\xf6\n".encode("cp1252"))

        result = self.reader.load(path)

        assert result.encoding in {"cp1252", "latin-1"}
        assert len(result.frame) == 1

    def test_names_blank_headers_by_position(self, tmp_path: Path) -> None:
        path = tmp_path / "blank.csv"
        path.write_text("id,,value\n1,x,2\n", encoding="utf-8")

        result = self.reader.load(path)

        assert result.frame.columns[1] == "column_2"
        assert any("no header" in note for note in result.notes)

    def test_makes_duplicate_headers_unique(self, tmp_path: Path) -> None:
        path = tmp_path / "dupes.csv"
        path.write_text("id,amount,amount\n1,2,3\n", encoding="utf-8")

        result = self.reader.load(path)

        assert list(result.frame.columns) == ["id", "amount", "amount_1"]
        assert any("duplicate column name" in note for note in result.notes)

    def test_trims_whitespace_from_headers(self, tmp_path: Path) -> None:
        path = tmp_path / "padded.csv"
        path.write_text("  id , amount \n1,2\n", encoding="utf-8")

        result = self.reader.load(path)

        assert list(result.frame.columns) == ["id", "amount"]

    def test_reads_common_null_tokens_as_missing(self, tmp_path: Path) -> None:
        path = tmp_path / "nulls.csv"
        path.write_text("id,value\n1,N/A\n2,null\n3,-\n4,7\n", encoding="utf-8")

        frame = self.reader.load(path).frame

        assert frame["value"].isna().sum() == 3

    def test_rejects_an_empty_file(self, tmp_path: Path) -> None:
        path = tmp_path / "empty.csv"
        path.write_text("", encoding="utf-8")

        with pytest.raises(DatasetError, match="empty"):
            self.reader.load(path)

    def test_rejects_a_header_with_no_rows(self, tmp_path: Path) -> None:
        path = tmp_path / "header-only.csv"
        path.write_text("id,value\n", encoding="utf-8")

        with pytest.raises(DatasetError, match="no data rows"):
            self.reader.load(path)

    def test_samples_a_large_file_and_says_so(self, tmp_path: Path) -> None:
        path = tmp_path / "big.csv"
        pd.DataFrame({"value": range(500)}).to_csv(path, index=False)

        result = self.reader.load(path, max_rows=100)

        assert len(result.frame) == 100
        assert result.total_rows == 500
        assert result.sampled is True


class TestExcelReader:
    reader = ExcelReader()

    def test_reads_a_workbook(self) -> None:
        result = self.reader.load(sample_path("clean_transactions.xlsx"))

        assert result.frame.shape == (600, 10)
        assert result.sheet_name == "transactions"

    def test_matches_the_csv_of_the_same_data(self) -> None:
        from_csv = CsvReader().load(sample_path("clean_transactions.csv")).frame
        from_excel = self.reader.load(sample_path("clean_transactions.xlsx")).frame

        assert list(from_csv.columns) == list(from_excel.columns)
        assert len(from_csv) == len(from_excel)

    def test_rejects_a_file_that_is_not_a_workbook(self, tmp_path: Path) -> None:
        path = tmp_path / "fake.xlsx"
        path.write_text("id,value\n1,2\n", encoding="utf-8")

        with pytest.raises(DatasetError):
            self.reader.load(path)


def test_registry_returns_a_reader_for_every_supported_format() -> None:
    for fmt in FileFormat:
        assert get_reader(fmt) is not None
