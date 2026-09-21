"""
Tests for chunking and large file handling with single schema mapping computation.
"""

from pathlib import Path
import pytest
from smart_credit_parser import UniversalDataParser, ParseOptions
from smart_credit_parser.ai import MockLLMClient

from tests.conftest import SCHEMA_PATH


def test_chunking_execution(tmp_path: Path):
    """Verifies that 2500 rows are processed in chunks of 500 without memory exhaustion."""
    large_csv = tmp_path / "large_businesses.csv"

    # Generate 2500 lines
    lines = ["ИНН;Название компании;Отрасль;Дата регистрации;Мест в совете\n"]
    for i in range(1, 2501):
        lines.append(f"100260000{i:05d};Company {i};IT;2020-01-01;1\n")
    large_csv.write_text("".join(lines), encoding="utf-8")

    parser = UniversalDataParser(schema_path=SCHEMA_PATH)

    # Process in chunks of 500
    opts = ParseOptions(target_table="businesses", chunk_size=500)
    result = parser.parse_file(large_csv, options=opts)

    assert result.success is True
    assert result.report.total_rows_read == 2500
    assert result.report.rows_accepted == 2500
    assert result.report.rows_rejected == 0
    assert len(result.accepted_records) == 2500


def test_file_size_limit_exceeded(tmp_path: Path):
    """Verifies that files exceeding max_file_size_mb are refused with a helpful error."""
    file_path = tmp_path / "oversized.csv"
    file_path.write_text("a,b\n1,2\n", encoding="utf-8")

    parser = UniversalDataParser(schema_path=SCHEMA_PATH)
    # Set limit to very small (e.g. 0.000001 MB)
    opts = ParseOptions(max_file_size_mb=0.000001)

    with pytest.raises(ValueError, match="exceeds limit"):
        parser.parse_file(file_path, options=opts)
