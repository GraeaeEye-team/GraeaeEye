"""
Tests for FastPath canonical detector (0 LLM calls for standard format).
"""

import pytest
from smart_credit_parser.schema.sql_parser import SQLSchemaParser
from smart_credit_parser.pipeline.fast_path import FastPathDetector

from tests.conftest import SCHEMA_PATH


@pytest.fixture
def schema():
    return SQLSchemaParser.parse_file(SCHEMA_PATH)


def test_fast_path_exact_businesses(schema):
    headers = [
        "business_id",
        "tax_id",
        "legal_name",
        "industry_code",
        "registration_date",
        "total_board_seats",
    ]
    mapping = FastPathDetector.detect_canonical_table(headers, schema)
    assert mapping is not None
    assert mapping.target_table == "businesses"
    assert len(mapping.column_mappings) >= 5
    assert all(m.confidence == 1.0 for m in mapping.column_mappings)
    assert len(mapping.unmapped_required_columns) == 0


def test_fast_path_case_insensitive_invoices(schema):
    headers = [
        "INVOICE_TYPE",
        "GROSS_AMOUNT",
        "ISSUE_DATE",
        "DUE_DATE",
        "STATUS",
        "EXTRA_COLUMN",
    ]
    mapping = FastPathDetector.detect_canonical_table(headers, schema, target_table_hint="invoices")
    assert mapping is not None
    assert mapping.target_table == "invoices"
    assert "EXTRA_COLUMN" in mapping.unmapped_source_columns


def test_fast_path_not_triggered_for_arbitrary_format(schema):
    headers = ["Фискальный_Код", "Название_Организации", "Сумма_Сделки"]
    mapping = FastPathDetector.detect_canonical_table(headers, schema)
    # Should be None because Russian names do not match canonical columns
    assert mapping is None
