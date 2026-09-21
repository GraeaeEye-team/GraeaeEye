"""
Tests for AI MappingAgent, Heuristic fallback, Mock LLM retries, and caching.
"""

from pathlib import Path
import pytest
from smart_credit_parser.schema.sql_parser import SQLSchemaParser
from smart_credit_parser.ai import MappingAgent, MappingCache, MockLLMClient, HeuristicLLMClient

from tests.conftest import SCHEMA_PATH


@pytest.fixture
def schema():
    return SQLSchemaParser.parse_file(SCHEMA_PATH)


def test_heuristic_multilingual_mapping_russian(schema):
    agent = MappingAgent(schema=schema, llm_client=HeuristicLLMClient())
    headers = ["ИНН", "Название компании", "Отрасль", "Дата регистрации"]
    sample_rows = [
        {"ИНН": "1002600001234", "Название компании": "АгроТрейд SRL", "Отрасль": "AGRI-01", "Дата регистрации": "2018-05-20"}
    ]

    mapping = agent.determine_mapping(headers, sample_rows, target_table_hint="businesses")
    assert mapping.target_table == "businesses"

    target_cols = {m.target_column for m in mapping.column_mappings}
    assert "tax_id" in target_cols
    assert "legal_name" in target_cols
    assert "industry_code" in target_cols
    assert "registration_date" in target_cols


def test_heuristic_multilingual_mapping_romanian_invoices(schema):
    agent = MappingAgent(schema=schema, llm_client=HeuristicLLMClient())
    headers = ["Tip factura", "Suma", "Data emiterii", "Data scadenta", "Statut"]
    sample_rows = [
        {"Tip factura": "creanta", "Suma": "15200.00", "Data emiterii": "2025-01-10", "Data scadenta": "2025-02-10", "Statut": "platit"}
    ]

    mapping = agent.determine_mapping(headers, sample_rows, target_table_hint="invoices")
    assert mapping.target_table == "invoices"

    target_cols = {m.target_column for m in mapping.column_mappings}
    assert "invoice_type" in target_cols
    assert "gross_amount" in target_cols
    assert "issue_date" in target_cols
    assert "due_date" in target_cols
    assert "status" in target_cols


def test_mapping_cache_avoids_llm_call(schema):
    mock = MockLLMClient()
    cache = MappingCache()
    agent = MappingAgent(schema=schema, llm_client=mock, cache=cache)

    headers = ["ИНН", "Название"]
    sample_rows = [{"ИНН": "1001", "Название": "Тест"}]

    # Seed mock response
    mock.responses = ['{"target_table": "businesses", "mappings": [{"source_column": "ИНН", "target_column": "tax_id", "confidence": 0.95}], "unmapped_source_columns": [], "unmapped_required_columns": []}']

    # First call uses mock
    m1 = agent.determine_mapping(headers, sample_rows, target_table_hint="businesses")
    assert mock.calls_count == 1
    assert m1.target_table == "businesses"

    # Second call hits cache, mock calls remains 1
    m2 = agent.determine_mapping(headers, sample_rows, target_table_hint="businesses")
    assert mock.calls_count == 1
    assert m2.target_table == "businesses"


def test_mapping_retry_on_invalid_json(schema):
    mock = MockLLMClient()
    agent = MappingAgent(schema=schema, llm_client=mock)

    headers = ["tax_code", "company"]
    sample_rows = [{"tax_code": "1001", "company": "Test"}]

    # First response is invalid json, second is valid
    mock.responses = [
        "INVALID JSON NOT A DICT",
        '{"target_table": "businesses", "mappings": [{"source_column": "tax_code", "target_column": "tax_id", "confidence": 0.9}], "unmapped_source_columns": [], "unmapped_required_columns": []}'
    ]

    mapping = agent.determine_mapping(headers, sample_rows, target_table_hint="businesses")
    assert mock.calls_count == 2
    assert mapping.target_table == "businesses"
    assert mapping.column_mappings[0].target_column == "tax_id"
