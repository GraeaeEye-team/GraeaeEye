"""
Public Application Service Interface for Smart Credit Parser Module.
Provides clean facade for host application: upload, mapping, dry-run, commit, history, and report.
Strictly enforces RBAC (ANALYST, UNDERWRITER, ADMIN) from schema.sql.
"""

from __future__ import annotations
import os
import tempfile
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from .schema.models import SchemaGraph, TableMapping, ColumnMapping
from .schema.sql_parser import SQLSchemaParser
from .engine.orchestrator import UniversalDataParser, ParseOptions, ParseResult
from .engine.audit_report import AuditReport
from .extractors.registry import get_extractor_for_file
from .ai.cache import MappingCache


@dataclass
class FileInspectionSummary:
    session_id: str
    filename: str
    file_size_bytes: int
    detected_extractor: str
    headers: List[str]
    sample_rows: List[Dict[str, Any]]
    fast_path_eligible: bool
    suggested_table: str
    available_tables: List[str]


@dataclass
class TableMappingResponse:
    session_id: str
    target_table: str
    column_mappings: List[Dict[str, Any]]
    unmapped_source_columns: List[str]
    unmapped_required_columns: List[str]
    available_target_columns: List[Dict[str, Any]]


@dataclass
class DryRunReportResponse:
    session_id: str
    target_table: str
    total_rows_read: int
    rows_accepted: int
    rows_rejected: int
    validation_issues: List[Dict[str, Any]]
    human_review_required: List[Dict[str, Any]]
    preview_records: List[Dict[str, Any]]
    is_ready_for_commit: bool


@dataclass
class CommitResultResponse:
    session_id: str
    target_table: str
    inserted_count: int
    status: str
    committed_by_user_id: str
    committed_by_role: str
    timestamp: str


@dataclass
class UploadHistoryItem:
    session_id: str
    filename: str
    target_table: str
    status: str
    total_rows: int
    accepted_rows: int
    rejected_rows: int
    created_at: str
    created_by: str
    committed_by: Optional[str] = None


@dataclass
class ParserSession:
    session_id: str
    filename: str
    file_path: Path
    created_at: str
    created_by: str
    user_role: str
    headers: List[str] = field(default_factory=list)
    sample_rows: List[Dict[str, Any]] = field(default_factory=list)
    suggested_table: str = "businesses"
    mapping: Optional[TableMapping] = None
    dry_run_report: Optional[AuditReport] = None
    accepted_records: List[Dict[str, Any]] = field(default_factory=list)
    status: str = "UPLOADED"  # UPLOADED, MAPPED, VALIDATED, COMMITTED, FAILED
    committed_by: Optional[str] = None
    committed_role: Optional[str] = None
    committed_at: Optional[str] = None


class ParserModuleService:
    """
    Public Service Interface for the Parser Module.
    The rest of the host web application depends ONLY on this class.
    """

    ALLOWED_WRITE_ROLES = {"UNDERWRITER", "ADMIN"}
    ALLOWED_READ_ROLES = {"ANALYST", "UNDERWRITER", "ADMIN"}

    def __init__(
        self,
        schema_path: Optional[str | Path] = None,
        db_connection: Optional[Any] = None,
        temp_storage_dir: Optional[Path] = None,
    ):
        if schema_path:
            schema_file = Path(schema_path)
        else:
            default_root = Path(__file__).resolve().parent.parent / "schema.sql"
            schema_file = Path(
                os.getenv(
                    "SCHEMA_PATH",
                    str(default_root) if default_root.exists() else r"c:\Users\skv1d\Downloads\schema.sql"
                )
            )
        self.schema: SchemaGraph = SQLSchemaParser.parse_file(schema_file)
        self.db_connection = db_connection
        self.temp_dir = temp_storage_dir or Path(tempfile.gettempdir()) / "smart_credit_uploads"
        self.temp_dir.mkdir(parents=True, exist_ok=True)

        self.parser = UniversalDataParser(
            schema=self.schema,
            db_connection=self.db_connection,
        )
        self.sessions: Dict[str, ParserSession] = {}

    def upload_and_inspect(
        self,
        file_bytes: bytes,
        filename: str,
        user_id: str = "analyst_1",
        user_role: str = "ANALYST",
    ) -> FileInspectionSummary:
        """
        Шаг 1: Прием файла, временное сохранение, определение формата и структуры.
        """
        user_role = user_role.upper()
        if user_role not in self.ALLOWED_READ_ROLES:
            raise PermissionError(f"Role '{user_role}' is not authorized to upload files.")

        session_id = str(uuid.uuid4())
        dest_path = self.temp_dir / f"{session_id}_{filename}"
        dest_path.write_bytes(file_bytes)

        extractor = get_extractor_for_file(dest_path)
        headers, sample_rows = extractor.get_sample(dest_path, max_rows=10)

        # Candidate tables from schema (excluding internal orchestration)
        available_tables = [
            t for t in self.schema.tables.keys()
            if t not in ("analysis_runs", "analysis_logs", "users", "user_settings")
        ]

        # Check fast-path
        from .pipeline.fast_path import FastPathDetector
        fast_path = FastPathDetector.detect_canonical_table(headers, self.schema)
        if fast_path:
            suggested_table = fast_path.target_table
            initial_mapping = fast_path
        else:
            initial_mapping = self.parser.agent.determine_mapping(headers, sample_rows)
            suggested_table = initial_mapping.target_table

        session = ParserSession(
            session_id=session_id,
            filename=filename,
            file_path=dest_path,
            created_at=time.strftime("%Y-%m-%d %H:%M:%S"),
            created_by=user_id,
            user_role=user_role,
            headers=headers,
            sample_rows=sample_rows,
            suggested_table=suggested_table,
            mapping=initial_mapping,
            status="UPLOADED",
        )
        self.sessions[session_id] = session

        return FileInspectionSummary(
            session_id=session_id,
            filename=filename,
            file_size_bytes=len(file_bytes),
            detected_extractor=extractor.__class__.__name__,
            headers=headers,
            sample_rows=sample_rows[:5],
            fast_path_eligible=fast_path is not None,
            suggested_table=suggested_table,
            available_tables=available_tables,
        )

    def get_mapping(
        self,
        session_id: str,
        target_table_hint: Optional[str] = None,
    ) -> TableMappingResponse:
        """
        Шаг 2: Вычисление или возврат семантического маппинга колонок ИИ.
        """
        session = self._get_session(session_id)
        target_table = target_table_hint or session.suggested_table

        if not session.mapping or session.mapping.target_table != target_table:
            session.mapping = self.parser.agent.determine_mapping(
                headers=session.headers,
                sample_rows=session.sample_rows,
                target_table_hint=target_table,
            )
            session.suggested_table = target_table

        tbl_schema = self.schema.get_table(target_table)
        available_cols = [
            {
                "name": c.name,
                "data_type": c.data_type,
                "is_required": c.is_required,
                "allowed_values": c.allowed_values,
            }
            for c in (tbl_schema.columns.values() if tbl_schema else [])
        ]

        return TableMappingResponse(
            session_id=session_id,
            target_table=target_table,
            column_mappings=[
                {
                    "source_column": cm.source_column,
                    "target_column": cm.target_column,
                    "confidence": cm.confidence,
                    "reasoning": cm.reasoning,
                }
                for cm in session.mapping.column_mappings
            ],
            unmapped_source_columns=session.mapping.unmapped_source_columns,
            unmapped_required_columns=session.mapping.unmapped_required_columns,
            available_target_columns=available_cols,
        )

    def update_mapping(
        self,
        session_id: str,
        target_table: str,
        custom_mappings: Dict[str, str],  # source_col -> target_col (or "" to ignore)
        save_to_cache: bool = True,
    ) -> TableMappingResponse:
        """
        Шаг 2 (редактирование): ручное переназначение колонок человеком с кэшированием.
        """
        session = self._get_session(session_id)
        tbl_schema = self.schema.get_table(target_table)
        if not tbl_schema:
            raise ValueError(f"Table '{target_table}' not found in schema.")

        # Check for duplicate target column assignments
        tgt_to_src: Dict[str, List[str]] = {}
        for src, tgt in custom_mappings.items():
            t_clean = (tgt or "").strip()
            if t_clean and t_clean != "IGNORE":
                tgt_to_src.setdefault(t_clean.lower(), []).append(src)

        duplicates = {t: s for t, s in tgt_to_src.items() if len(s) > 1}
        if duplicates:
            msg_parts = [
                f"колонка таблицы '{t}' назначена одновременно для [{', '.join(s)}]"
                for t, s in duplicates.items()
            ]
            raise ValueError(
                f"Коллизия сопоставления: {'; '.join(msg_parts)}. Две разные колонки файла не могут записываться в одно поле таблицы. Для лишней колонки выберите 'Не загружать (Игнорировать)'."
            )

        col_mappings: List[ColumnMapping] = []
        unmapped_src: List[str] = []

        for src in session.headers:
            tgt = custom_mappings.get(src, "").strip()
            if tgt and tgt != "IGNORE" and tbl_schema.get_column(tgt):
                col_mappings.append(
                    ColumnMapping(
                        source_column=src,
                        target_column=tgt,
                        confidence=1.0,
                        reasoning="Operator manual confirmation",
                    )
                )
            else:
                unmapped_src.append(src)

        mapped_targets = {cm.target_column.lower() for cm in col_mappings}
        unmapped_req = [
            rc for rc in tbl_schema.required_columns() if rc.lower() not in mapped_targets
        ]

        new_mapping = TableMapping(
            target_table=target_table,
            column_mappings=col_mappings,
            unmapped_source_columns=unmapped_src,
            unmapped_required_columns=unmapped_req,
        )

        session.mapping = new_mapping
        session.suggested_table = target_table
        session.status = "MAPPED"

        if save_to_cache:
            sig = MappingCache.compute_signature(session.headers, target_table)
            self.parser.cache.put(sig, new_mapping)

        return self.get_mapping(session_id, target_table_hint=target_table)

    def run_dry_run(
        self,
        session_id: str,
        context_keys: Optional[Dict[str, Any]] = None,
    ) -> DryRunReportResponse:
        """
        Шаг 3: Выполнение предпросмотра (Dry-Run) с детерминированной валидацией.
        БД гарантированно не модифицируется.
        """
        session = self._get_session(session_id)

        # Prepare context keys (e.g. inject default UUIDs for required foreign keys if missing in flat file)
        effective_context = dict(context_keys or {})
        tbl_schema = self.schema.get_table(session.suggested_table)
        mapped_target_cols = {
            cm.target_column.lower() for cm in (session.mapping.column_mappings if session.mapping else [])
        }
        if tbl_schema:
            for col_name, col in tbl_schema.columns.items():
                if col.foreign_key_table and col.is_required and col_name.lower() not in mapped_target_cols and col_name not in effective_context:
                    # Provide standard UUID for standalone demo context (e.g. borrower or counterparty)
                    effective_context[col_name] = f"00000000-0000-0000-0000-{len(effective_context)+1:012d}"

        opts = ParseOptions(
            target_table=session.suggested_table,
            dry_run=True,
            context_keys=effective_context,
            custom_mapping=session.mapping,
        )

        result: ParseResult = self.parser.parse_file(session.file_path, options=opts)
        session.dry_run_report = result.report
        session.accepted_records = result.accepted_records
        session.status = "VALIDATED"

        issues = [
            {
                "row_index": r.row_index,
                "errors": r.errors,
                "sample": r.raw_data,
            }
            for r in result.report.rejected_details[:50]
        ]

        return DryRunReportResponse(
            session_id=session_id,
            target_table=result.report.target_table,
            total_rows_read=result.report.total_rows_read,
            rows_accepted=result.report.rows_accepted,
            rows_rejected=result.report.rows_rejected,
            validation_issues=issues,
            human_review_required=result.report.human_review_required,
            preview_records=result.accepted_records[:10],
            is_ready_for_commit=(result.report.rows_accepted > 0),
        )

    def confirm_and_write(
        self,
        session_id: str,
        user_id: str,
        user_role: str,
    ) -> CommitResultResponse:
        """
        Шаг 4: Атомарная транзакционная запись в БД.
        Доступно строго UNDERWRITER и ADMIN.
        """
        user_role = user_role.upper()
        if user_role not in self.ALLOWED_WRITE_ROLES:
            raise PermissionError(
                f"Role '{user_role}' is not authorized to confirm and write to database. "
                f"Requires one of {self.ALLOWED_WRITE_ROLES}."
            )

        session = self._get_session(session_id)
        if not session.accepted_records:
            raise ValueError("No validated records to commit. Please run dry-run first.")

        # Determine conflict column
        tbl_schema = self.schema.get_table(session.suggested_table)
        conflict_col = None
        if session.accepted_records and tbl_schema:
            first_keys = set(session.accepted_records[0].keys())
            for uq_list in tbl_schema.unique_constraints:
                if len(uq_list) == 1 and uq_list[0] in first_keys:
                    conflict_col = uq_list[0]
                    break
            if not conflict_col:
                for c in tbl_schema.columns.values():
                    if c.is_unique and c.name in first_keys:
                        conflict_col = c.name
                        break
            if not conflict_col:
                for pk in tbl_schema.primary_key:
                    if pk in first_keys:
                        conflict_col = pk
                        break

        # Execute live transaction
        write_res = self.parser.writer.write_records(
            table_name=session.suggested_table,
            records=session.accepted_records,
            dry_run=False,
            conflict_col=conflict_col,
        )

        now_str = time.strftime("%Y-%m-%d %H:%M:%S")
        session.status = "COMMITTED"
        session.committed_by = user_id
        session.committed_role = user_role
        session.committed_at = now_str

        return CommitResultResponse(
            session_id=session_id,
            target_table=session.suggested_table,
            inserted_count=write_res.get("inserted_count", len(session.accepted_records)),
            status="COMMITTED",
            committed_by_user_id=user_id,
            committed_by_role=user_role,
            timestamp=now_str,
        )

    def get_history(self, limit: int = 50) -> List[UploadHistoryItem]:
        """Возвращает историю сессий загрузки."""
        history = []
        for s in reversed(list(self.sessions.values())):
            history.append(
                UploadHistoryItem(
                    session_id=s.session_id,
                    filename=s.filename,
                    target_table=s.suggested_table,
                    status=s.status,
                    total_rows=s.dry_run_report.total_rows_read if s.dry_run_report else len(s.sample_rows),
                    accepted_rows=s.dry_run_report.rows_accepted if s.dry_run_report else 0,
                    rejected_rows=s.dry_run_report.rows_rejected if s.dry_run_report else 0,
                    created_at=s.created_at,
                    created_by=s.created_by,
                    committed_by=s.committed_by,
                )
            )
            if len(history) >= limit:
                break
        return history

    def download_report(self, session_id: str, format_type: str = "markdown") -> str:
        """Экспорт финального аудиторского отчета."""
        session = self._get_session(session_id)
        if session.dry_run_report:
            if format_type.lower() == "markdown":
                return session.dry_run_report.to_markdown()
            import json
            return json.dumps(session.dry_run_report.to_dict(), ensure_ascii=False, indent=2)
        return "# Отчет недоступен. Запустите предварительную проверку (Dry-Run)."

    def _get_session(self, session_id: str) -> ParserSession:
        session = self.sessions.get(session_id)
        if not session:
            raise KeyError(f"Session '{session_id}' not found.")
        return session
