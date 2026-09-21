"""
Smart Credit System - Universal AI Data Parser
Anchored dynamically to schema.sql.
"""

from .schema.models import SchemaGraph, TableSchema, ColumnSchema, TableMapping, ColumnMapping
from .schema.sql_parser import SQLSchemaParser
from .engine.orchestrator import UniversalDataParser, ParseOptions, ParseResult
from .engine.audit_report import AuditReport

__version__ = "0.1.0"

__all__ = [
    "SchemaGraph",
    "TableSchema",
    "ColumnSchema",
    "TableMapping",
    "ColumnMapping",
    "SQLSchemaParser",
    "UniversalDataParser",
    "ParseOptions",
    "ParseResult",
    "AuditReport",
]
