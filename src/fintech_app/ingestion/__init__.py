"""
Пакет ingestion: Модуль 1 — Интеллектуальный парсер и нормализатор данных.
Извлекает выписки из CSV/XLSX/PDF, нормализует заголовки, категоризирует транзакции,
собирает открытые внешние реестры и сохраняет нормализованные данные через DAL в PostgreSQL.
"""

from fintech_app.ingestion.ai_mapper import (
    TransactionCategorizationMapper,
    categorize_transaction,
    fuzzy_map_headers,
    map_columns_with_ai,
    validate_mapping,
)
from fintech_app.ingestion.external_intel import ExternalIntelligenceCollector
from fintech_app.ingestion.parser import (
    BankStatementParser,
    JudicialRegistryParser,
    clean_amount_string,
    generate_mock_bank_statement_payload,
    generate_mock_transaction_batch,
    load_file_to_dataframe,
    parse_date_flexible,
)
from fintech_app.ingestion.pipeline import IngestionPipeline
from fintech_app.ingestion.schemas import (
    IngestionResult,
    NormalizedTransactionRecord,
    NormalizedTransactionSchema,
    ParsedBankStatementPayload,
    ParsedJudicialRecord,
    RawBankStatementLine,
    StandardizedTransactionBatch,
)

__all__ = [
    "BankStatementParser",
    "JudicialRegistryParser",
    "clean_amount_string",
    "parse_date_flexible",
    "generate_mock_bank_statement_payload",
    "generate_mock_transaction_batch",
    "load_file_to_dataframe",
    "TransactionCategorizationMapper",
    "fuzzy_map_headers",
    "categorize_transaction",
    "map_columns_with_ai",
    "validate_mapping",
    "ExternalIntelligenceCollector",
    "IngestionPipeline",
    "RawBankStatementLine",
    "ParsedBankStatementPayload",
    "ParsedJudicialRecord",
    "NormalizedTransactionRecord",
    "StandardizedTransactionBatch",
    "IngestionResult",
    "NormalizedTransactionSchema",
]
