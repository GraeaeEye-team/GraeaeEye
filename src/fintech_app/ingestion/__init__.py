"""
Пакет ingestion: Модуль 1 — Интеллектуальный парсер и нормализатор данных.
Извлекает выписки из CSV/XLSX/PDF, нормализует заголовки, категоризирует транзакции,
собирает открытые внешние реестры и сохраняет нормализованные данные через DAL в PostgreSQL.
"""

from .ai_mapper import (
    TransactionCategorizationMapper,
    categorize_transaction,
    fuzzy_map_headers,
    map_columns_with_ai,
    validate_mapping,
)
from .external_intel import ExternalIntelligenceCollector
from .parser import (
    BankStatementParser,
    CreditObligationParser,
    InvoiceParser,
    JudicialRegistryParser,
    clean_amount_string,
    load_file_to_dataframe,
    parse_date_flexible,
)
from .pipeline import IngestionPipeline
from .schemas import (
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
    "InvoiceParser",
    "CreditObligationParser",
    "JudicialRegistryParser",
    "clean_amount_string",
    "parse_date_flexible",
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
