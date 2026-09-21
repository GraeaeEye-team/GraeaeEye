"""
Universal Data Parser Orchestrator.
Main entry point coordinating file extraction, AI mapping, fast-path, normalization, validation, and writing.
"""

from __future__ import annotations
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from ..schema.models import SchemaGraph, TableMapping
from ..schema.sql_parser import SQLSchemaParser
from ..schema.validator import SchemaValidator
from ..extractors.registry import get_extractor_for_file
from ..ai.client import BaseLLMClient, get_default_llm_client
from ..ai.cache import MappingCache
from ..ai.mapping_agent import MappingAgent
from .audit_report import AuditReport, RejectedRowInfo
from .transactional_writer import TransactionalWriter


@dataclass
class ParseOptions:
    target_table: Optional[str] = None
    dry_run: bool = True
    chunk_size: int = 1000
    max_file_size_mb: float = 50.0
    bypass_cache: bool = False
    context_keys: Dict[str, Any] = field(default_factory=dict)
    # E.g. {"business_id": "UUID", "counterparty_id": "UUID"} to fill missing foreign keys in flat files
    custom_mapping: Optional[TableMapping] = None


@dataclass
class ParseResult:
    success: bool
    report: AuditReport
    accepted_records: List[Dict[str, Any]]
    mapping: TableMapping


class UniversalDataParser:
    """Universal AI-driven data parser anchored to schema.sql."""

    def __init__(
        self,
        schema: Optional[SchemaGraph] = None,
        schema_path: Optional[str | Path] = None,
        llm_client: Optional[BaseLLMClient] = None,
        cache: Optional[MappingCache] = None,
        db_connection: Optional[Any] = None,
    ):
        if schema:
            self.schema = schema
        elif schema_path:
            self.schema = SQLSchemaParser.parse_file(schema_path)
        else:
            env_path = os.getenv("SCHEMA_PATH")
            root_path = Path(__file__).resolve().parent.parent.parent / "schema.sql"
            default_path = (
                Path(env_path) if env_path else (root_path if root_path.exists() else Path(r"c:\Users\skv1d\Downloads\schema.sql"))
            )
            if default_path.exists():
                self.schema = SQLSchemaParser.parse_file(default_path)
            else:
                raise ValueError(f"No schema provided, and schema.sql was not found at: {default_path}")

        self.llm_client = llm_client or get_default_llm_client()
        self.cache = cache or MappingCache()
        self.writer = TransactionalWriter(db_connection)
        self.agent = MappingAgent(self.schema, self.llm_client, self.cache)

    def parse_file(
        self, file_path: str | Path, options: Optional[ParseOptions] = None
    ) -> ParseResult:
        """Parses an arbitrary file and brings records to canonical database schema."""
        start_time = time.time()
        opts = options or ParseOptions()
        path = Path(file_path)

        # 1. Validation of file existence and size
        if not path.exists():
            raise FileNotFoundError(f"Source file does not exist: {file_path}")

        file_size_mb = path.stat().st_size / (1024 * 1024)
        if file_size_mb > opts.max_file_size_mb:
            raise ValueError(
                f"File size {file_size_mb:.2f} MB exceeds limit of {opts.max_file_size_mb} MB."
            )

        # 2. Select extractor and sample data
        extractor = get_extractor_for_file(path)
        headers, sample_rows = extractor.get_sample(path, max_rows=20)

        if not headers or not sample_rows:
            report = AuditReport(
                file_name=path.name,
                target_table=opts.target_table or "unknown",
                dry_run=opts.dry_run,
                human_review_required=[
                    {"item": "Empty File", "reason": "No readable records or columns found in file."}
                ],
            )
            return ParseResult(
                success=False,
                report=report,
                accepted_records=[],
                mapping=TableMapping(
                    target_table=opts.target_table or "unknown",
                    column_mappings=[],
                    unmapped_source_columns=[],
                    unmapped_required_columns=[],
                ),
            )

        # 3. Determine Table and Column Mapping
        if opts.custom_mapping:
            mapping = opts.custom_mapping
        else:
            mapping = self.agent.determine_mapping(
                headers=headers,
                sample_rows=sample_rows,
                target_table_hint=opts.target_table,
                bypass_cache=opts.bypass_cache,
            )

        target_table_name = mapping.target_table
        table_schema = self.schema.get_table(target_table_name)
        if not table_schema:
            raise ValueError(f"Target table '{target_table_name}' not found in canonical schema.")

        # 4. Initialize Validator & Audit Report
        validator = SchemaValidator(table_schema)
        fast_path_used = any("Fast-path" in m.reasoning for m in mapping.column_mappings)

        report = AuditReport(
            file_name=path.name,
            target_table=target_table_name,
            mapping=mapping,
            fast_path_used=fast_path_used,
            dry_run=opts.dry_run,
        )

        # Check for low confidence mappings
        for cm in mapping.column_mappings:
            if cm.confidence < 0.7:
                report.human_review_required.append({
                    "item": f"Column '{cm.source_column}' -> '{cm.target_column}'",
                    "reason": f"Low confidence ({int(cm.confidence * 100)}%): {cm.reasoning}",
                })

        missing_req = [
            c for c in mapping.unmapped_required_columns
            if c.lower() not in {k.lower() for k in opts.context_keys.keys()}
        ]
        if missing_req:
            report.human_review_required.append({
                "item": "Missing Required Schema Columns",
                "reason": f"Columns not present in file or context: {', '.join(missing_req)}",
            })

        # Pre-build lookup for mapping
        col_map_dict = {
            cm.source_column.lower(): cm.target_column for cm in mapping.column_mappings
        }

        # Tracking sets for batch validation
        seen_uniques: Dict[str, Set[str]] = {}
        accepted_records: List[Dict[str, Any]] = []
        rejected_details: List[RejectedRowInfo] = []

        total_rows = 0
        accepted_count = 0
        rejected_count = 0

        # 5. Process Stream in Chunks
        for chunk in extractor.extract_chunks(path, chunk_size=opts.chunk_size):
            for row in chunk:
                total_rows += 1
                mapped_row: Dict[str, Any] = {}

                # Apply column mapping
                for k, v in row.items():
                    target_col = col_map_dict.get(k.lower())
                    if target_col:
                        mapped_row[target_col] = v

                # Inject context keys (e.g. business_id or counterparty_id if provided)
                for ck, cv in opts.context_keys.items():
                    if ck not in mapped_row or not mapped_row[ck]:
                        mapped_row[ck] = cv

                # Validate & Normalize
                val_result = validator.validate_and_normalize(
                    mapped_row, seen_uniques=seen_uniques
                )

                if val_result.is_valid:
                    accepted_records.append(val_result.data)
                    accepted_count += 1
                else:
                    rejected_count += 1
                    if len(rejected_details) < 100:  # limit stored error details
                        rejected_details.append(
                            RejectedRowInfo(
                                row_index=total_rows,
                                raw_data=row,
                                errors=val_result.errors,
                            )
                        )

        # 6. Database Write (or Dry-Run Preview)
        conflict_col = None
        if accepted_records:
            first_keys = set(accepted_records[0].keys())
            # 1. Unique constraint columns
            for uq_list in table_schema.unique_constraints:
                if len(uq_list) == 1 and uq_list[0] in first_keys:
                    conflict_col = uq_list[0]
                    break
            # 2. Columns marked is_unique
            if not conflict_col:
                for c in table_schema.columns.values():
                    if c.is_unique and c.name in first_keys:
                        conflict_col = c.name
                        break
            # 3. Primary key if provided in records
            if not conflict_col:
                for pk in table_schema.primary_key:
                    if pk in first_keys:
                        conflict_col = pk
                        break

        self.writer.write_records(
            table_name=target_table_name,
            records=accepted_records,
            dry_run=opts.dry_run,
            conflict_col=conflict_col,
        )

        # 7. Finalize Report
        report.total_rows_read = total_rows
        report.rows_accepted = accepted_count
        report.rows_rejected = rejected_count
        report.rejected_details = rejected_details
        report.execution_time_seconds = time.time() - start_time

        return ParseResult(
            success=(accepted_count > 0 or total_rows == 0),
            report=report,
            accepted_records=accepted_records,
            mapping=mapping,
        )
