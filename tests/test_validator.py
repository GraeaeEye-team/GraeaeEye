"""
Tests for SchemaValidator: NOT NULL, CHECK, UNIQUE, and FK validations.
"""

import pytest
from smart_credit_parser.schema.sql_parser import SQLSchemaParser
from smart_credit_parser.schema.validator import SchemaValidator

from tests.conftest import SCHEMA_PATH


@pytest.fixture
def schema_graph():
    return SQLSchemaParser.parse_file(SCHEMA_PATH)


def test_validator_valid_business(schema_graph):
    tbl = schema_graph.get_table("businesses")
    validator = SchemaValidator(tbl)

    record = {
        "tax_id": "1002600001234",
        "legal_name": "AgroTech Moldova SRL",
        "industry_code": "AGRI-01",
        "registration_date": "2018-05-20",
        "total_board_seats": "2",
        "independent_directors_count": "1",
    }
    result = validator.validate_and_normalize(record)
    assert result.is_valid is True
    assert result.data["tax_id"] == "1002600001234"
    assert result.data["total_board_seats"] == 2


def test_validator_missing_required_field(schema_graph):
    tbl = schema_graph.get_table("businesses")
    validator = SchemaValidator(tbl)

    # Missing legal_name
    record = {
        "tax_id": "1002600001234",
        "industry_code": "AGRI-01",
        "registration_date": "2018-05-20",
    }
    result = validator.validate_and_normalize(record)
    assert result.is_valid is False
    assert any("legal_name" in err for err in result.errors)


def test_validator_check_constraint_violation(schema_graph):
    tbl = schema_graph.get_table("invoices")
    validator = SchemaValidator(tbl)

    # Negative amount violates gross_amount >= 0.00
    record = {
        "business_id": "550e8400-e29b-41d4-a716-446655440000",
        "counterparty_id": "660e8400-e29b-41d4-a716-446655440000",
        "invoice_type": "RECEIVABLE",
        "gross_amount": "-500.00",
        "issue_date": "2025-01-10",
        "due_date": "2025-02-10",
        "status": "PAID",
    }
    result = validator.validate_and_normalize(record)
    assert result.is_valid is False
    assert any("gross_amount" in err and "CHECK constraint" in err for err in result.errors)


def test_validator_enum_invalid_value(schema_graph):
    tbl = schema_graph.get_table("invoices")
    validator = SchemaValidator(tbl)

    record = {
        "business_id": "550e8400-e29b-41d4-a716-446655440000",
        "counterparty_id": "660e8400-e29b-41d4-a716-446655440000",
        "invoice_type": "INVALID_TYPE",
        "gross_amount": "500.00",
        "issue_date": "2025-01-10",
        "due_date": "2025-02-10",
        "status": "PAID",
    }
    result = validator.validate_and_normalize(record)
    assert result.is_valid is False
    assert any("invoice_type" in err and "Allowed values" in err for err in result.errors)


def test_validator_unique_constraint(schema_graph):
    tbl = schema_graph.get_table("businesses")
    validator = SchemaValidator(tbl)

    seen = {}
    record = {
        "tax_id": "1002600001234",
        "legal_name": "AgroTech SRL",
        "industry_code": "AGRI-01",
        "registration_date": "2018-05-20",
    }
    r1 = validator.validate_and_normalize(record, seen_uniques=seen)
    assert r1.is_valid is True

    # Second record with identical tax_id
    r2 = validator.validate_and_normalize(record, seen_uniques=seen)
    assert r2.is_valid is False
    assert any("UNIQUE constraint" in err for err in r2.errors)
