"""
Canonical schema representation and data structures extracted from schema.sql.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any


@dataclass
class ColumnMapping:
    source_column: str
    target_column: str
    confidence: float
    reasoning: str


@dataclass
class TableMapping:
    target_table: str
    column_mappings: List[ColumnMapping]
    unmapped_source_columns: List[str]
    unmapped_required_columns: List[str]


@dataclass
class ColumnSchema:
    name: str
    data_type: str  # UUID, VARCHAR(N), INT, DECIMAL(P,S), DATE, TIMESTAMP, BOOLEAN, JSONB, TEXT
    is_nullable: bool = True
    is_primary_key: bool = False
    is_unique: bool = False
    default_value: Optional[str] = None
    check_expression: Optional[str] = None
    allowed_values: Optional[List[str]] = None  # From CHECK (col IN (...))
    numeric_min: Optional[float] = None
    numeric_max: Optional[float] = None
    foreign_key_table: Optional[str] = None
    foreign_key_column: Optional[str] = None
    on_delete: Optional[str] = None
    description: Optional[str] = None

    @property
    def is_required(self) -> bool:
        """Field is required if NOT NULL and has no default value."""
        return not self.is_nullable and self.default_value is None and not self.is_primary_key


@dataclass
class ForeignKeyDef:
    column_name: str
    referenced_table: str
    referenced_column: str
    on_delete: str = "NO ACTION"


@dataclass
class TableSchema:
    name: str
    columns: Dict[str, ColumnSchema] = field(default_factory=dict)
    primary_key: List[str] = field(default_factory=list)
    foreign_keys: List[ForeignKeyDef] = field(default_factory=list)
    unique_constraints: List[List[str]] = field(default_factory=list)
    check_constraints: List[str] = field(default_factory=list)
    comment: Optional[str] = None

    def required_columns(self) -> List[str]:
        """Returns names of columns that MUST be provided by the caller."""
        return [c.name for c in self.columns.values() if c.is_required]

    def get_column(self, col_name: str) -> Optional[ColumnSchema]:
        """Lookup column case-insensitively."""
        col_lower = col_name.lower()
        for k, v in self.columns.items():
            if k.lower() == col_lower:
                return v
        return None


@dataclass
class SchemaGraph:
    tables: Dict[str, TableSchema] = field(default_factory=dict)
    topological_order: List[str] = field(default_factory=list)

    def get_table(self, table_name: str) -> Optional[TableSchema]:
        """Lookup table case-insensitively."""
        tbl_lower = table_name.lower()
        for k, v in self.tables.items():
            if k.lower() == tbl_lower:
                return v
        return None

    def to_summary_dict(self) -> Dict[str, Any]:
        """Export schema summary suitable for serialization and LLM prompt context."""
        summary = {}
        for tbl_name, tbl in self.tables.items():
            summary[tbl_name] = {
                "primary_key": tbl.primary_key,
                "required_columns": tbl.required_columns(),
                "columns": {
                    col.name: {
                        "type": col.data_type,
                        "required": col.is_required,
                        "nullable": col.is_nullable,
                        "default": col.default_value,
                        "allowed_values": col.allowed_values,
                        "min": col.numeric_min,
                        "max": col.numeric_max,
                        "references": f"{col.foreign_key_table}.{col.foreign_key_column}"
                        if col.foreign_key_table
                        else None,
                    }
                    for col in tbl.columns.values()
                },
                "foreign_keys": [
                    {
                        "col": fk.column_name,
                        "ref_table": fk.referenced_table,
                        "ref_col": fk.referenced_column,
                    }
                    for fk in tbl.foreign_keys
                ],
            }
        return summary
