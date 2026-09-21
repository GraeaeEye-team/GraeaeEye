"""
Audit Report Generator.
Produces structured machine-readable and markdown human-readable summary of parsing execution.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from ..ai.cache import TableMapping


@dataclass
class RejectedRowInfo:
    row_index: int
    raw_data: Dict[str, Any]
    errors: List[str]


@dataclass
class AuditReport:
    file_name: str
    target_table: str
    total_rows_read: int = 0
    rows_accepted: int = 0
    rows_rejected: int = 0
    rejected_details: List[RejectedRowInfo] = field(default_factory=list)
    mapping: Optional[TableMapping] = None
    human_review_required: List[Dict[str, Any]] = field(default_factory=list)
    fast_path_used: bool = False
    dry_run: bool = True
    execution_time_seconds: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "file_name": self.file_name,
            "target_table": self.target_table,
            "total_rows_read": self.total_rows_read,
            "rows_accepted": self.rows_accepted,
            "rows_rejected": self.rows_rejected,
            "fast_path_used": self.fast_path_used,
            "dry_run": self.dry_run,
            "execution_time_seconds": round(self.execution_time_seconds, 3),
            "human_review_required": self.human_review_required,
            "mapping": self.mapping.to_dict() if self.mapping else None,
            "rejected_details": [
                {
                    "row_index": r.row_index,
                    "errors": r.errors,
                    "sample_raw": {k: str(v)[:50] for k, v in list(r.raw_data.items())[:5]},
                }
                for r in self.rejected_details[:50]
            ],
        }

    def to_markdown(self) -> str:
        lines = [
            f"# Отчет разбора данных: `{self.file_name}`",
            "",
            "## Сводка",
            f"- **Целевая таблица БД:** `{self.target_table}`",
            f"- **Всего строк прочитано:** {self.total_rows_read}",
            f"- **Принято строк (валидно):** {self.rows_accepted}",
            f"- **Отклонено строк:** {self.rows_rejected}",
            f"- **Режим выполнения:** {'[DRY-RUN / Предпросмотр]' if self.dry_run else '[ЗАПИСЬ В БД]'}",
            f"- **Fast-Path без вызова ИИ:** {'Да (эталонный формат)' if self.fast_path_used else 'Нет (семантический маппинг)'}",
            f"- **Время выполнения:** {self.execution_time_seconds:.2f} сек.",
            "",
            "## Сопоставление колонок (Schema Mapping)",
        ]

        if self.mapping:
            lines.append("| Колонка источника | Колонка в schema.sql | Уверенность | Обоснование |")
            lines.append("| :--- | :--- | :--- | :--- |")
            for m in self.mapping.column_mappings:
                conf_badge = f"{int(m.confidence * 100)}%"
                lines.append(f"| `{m.source_column}` | `{m.target_column}` | {conf_badge} | {m.reasoning} |")

            if self.mapping.unmapped_source_columns:
                lines.append(f"\n> **Несопоставленные колонки источника:** {', '.join(self.mapping.unmapped_source_columns)}")
            if self.mapping.unmapped_required_columns:
                lines.append(f"\n> ⚠️ **Незаполненные обязательные поля схемы:** {', '.join(self.mapping.unmapped_required_columns)}")

        if self.human_review_required:
            lines.append("\n## Элементы, требующие внимания оператора")
            for item in self.human_review_required:
                lines.append(f"- ⚠️ **{item.get('item', 'Внимание')}:** {item.get('reason')}")

        if self.rejected_details:
            lines.append("\n## Примеры отклоненных строк")
            for r in self.rejected_details[:10]:
                errs_str = "; ".join(r.errors)
                lines.append(f"- **Строка #{r.row_index}:** {errs_str}")

        return "\n".join(lines)
