"""
Serializes SchemaGraph into clean, compact descriptions for LLM prompt context.
"""

from __future__ import annotations
from typing import Optional
from ..schema.models import SchemaGraph, TableSchema


class SchemaSerializer:
    """Formats schema objects into markdown/text representation for LLM context."""

    @staticmethod
    def serialize_table(table: TableSchema) -> str:
        lines = [f"Table: `{table.name}`"]
        if table.comment:
            lines.append(f"  Description: {table.comment}")
        lines.append(f"  Primary Key: {', '.join(table.primary_key)}")
        lines.append("  Columns:")

        for col in table.columns.values():
            req_str = "REQUIRED" if col.is_required else ("NULLABLE" if col.is_nullable else "HAS_DEFAULT")
            fk_str = f" -> {col.foreign_key_table}.{col.foreign_key_column}" if col.foreign_key_table else ""
            enum_str = f" [ENUM: {', '.join(col.allowed_values)}]" if col.allowed_values else ""
            range_str = ""
            if col.numeric_min is not None and col.numeric_max is not None:
                range_str = f" [Range: {col.numeric_min} to {col.numeric_max}]"
            elif col.numeric_min is not None:
                range_str = f" [Min: {col.numeric_min}]"

            lines.append(
                f"    - `{col.name}` ({col.data_type}, {req_str}){fk_str}{enum_str}{range_str}"
            )

        return "\n".join(lines)

    @classmethod
    def serialize_schema(cls, schema: SchemaGraph, filter_tables: Optional[list[str]] = None) -> str:
        blocks = []
        for tbl_name, tbl in schema.tables.items():
            if filter_tables and tbl_name not in filter_tables:
                continue
            # Skip internal orchestration tables if mapping client operational data
            if not filter_tables and tbl_name in ("analysis_runs", "analysis_logs", "users", "user_settings"):
                continue
            blocks.append(cls.serialize_table(tbl))
        return "\n\n".join(blocks)
