"""
Fast-path canonical detector.
Bypasses LLM completely when input headers already match canonical schema.sql columns.
"""

from __future__ import annotations
from typing import List, Optional
from ..schema.models import SchemaGraph, ColumnMapping, TableMapping


class FastPathDetector:
    """Evaluates whether incoming tabular headers already conform to canonical schema."""

    @classmethod
    def detect_canonical_table(
        cls,
        headers: List[str],
        schema: SchemaGraph,
        target_table_hint: Optional[str] = None,
    ) -> Optional[TableMapping]:
        """
        If incoming headers match a canonical table's required and existing columns,
        returns TableMapping with 1.0 confidence without calling the LLM.
        """
        header_map = {h.strip().lower(): h.strip() for h in headers}

        candidate_tables = (
            [schema.get_table(target_table_hint)]
            if target_table_hint and schema.get_table(target_table_hint)
            else list(schema.tables.values())
        )

        for table in candidate_tables:
            if table is None:
                continue

            table_cols_lower = {c.name.lower(): c for c in table.columns.values()}

            # Columns in input that match table columns
            matched_cols = []
            unmapped_src = []
            for h_clean, raw_h in header_map.items():
                if h_clean in table_cols_lower:
                    matched_cols.append((raw_h, table_cols_lower[h_clean].name))
                else:
                    unmapped_src.append(raw_h)

            # Fast-path is ONLY for files already in canonical format.
            # All core required columns must match canonical names!
            core_req_cols = [
                c.name for c in table.columns.values()
                if c.is_required and not c.foreign_key_table and not c.is_primary_key
            ]
            core_matched = [rc for rc in core_req_cols if rc.lower() in header_map]

            if len(core_matched) < len(core_req_cols):
                # Missing core required columns in canonical format -> need AI mapping!
                continue

            # Also require at least 3 matching columns or all table columns
            if len(matched_cols) < max(2, len(core_req_cols)):
                continue

            mappings = [
                ColumnMapping(
                    source_column=src,
                    target_column=tgt,
                    confidence=1.0,
                    reasoning="Fast-path canonical column match (0 LLM calls)",
                )
                for src, tgt in matched_cols
            ]
            mapped_tgts = {tgt.lower() for _, tgt in matched_cols}
            unmapped_req = [
                c.name for c in table.columns.values()
                if c.is_required and c.name.lower() not in mapped_tgts
            ]
            return TableMapping(
                target_table=table.name,
                column_mappings=mappings,
                unmapped_source_columns=unmapped_src,
                unmapped_required_columns=unmapped_req,
            )

        return None
