"""
Transactional database writer with dialect support (PostgreSQL / SQLite),
dry-run preview, atomic rollback, and automatic conflict resolution.
"""

from __future__ import annotations
import sqlite3
from typing import Any, Dict, List, Optional, Tuple


class TransactionalWriter:
    """Safely executes or previews database inserts across PostgreSQL and SQLite."""

    def __init__(self, db_connection: Optional[Any] = None, dialect: Optional[str] = None):
        self.connection = db_connection
        if dialect:
            self.dialect = dialect.lower()
        elif db_connection:
            if isinstance(db_connection, sqlite3.Connection):
                self.dialect = "sqlite"
            else:
                self.dialect = "postgresql"
        else:
            self.dialect = "postgresql"

    @classmethod
    def generate_insert_sql(
        cls,
        table_name: str,
        records: List[Dict[str, Any]],
        conflict_col: Optional[str] = None,
        dialect: str = "postgresql",
    ) -> List[Tuple[str, Tuple[Any, ...]]]:
        """
        Generates parameterized SQL INSERT statements.
        dialect: 'postgresql' (%s placeholders) or 'sqlite' (? placeholders).
        conflict_col: optional column for ON CONFLICT DO NOTHING.
        """
        if not records:
            return []

        param_marker = "?" if dialect == "sqlite" else "%s"
        statements: List[Tuple[str, Tuple[Any, ...]]] = []

        for r in records:
            cols = list(r.keys())
            placeholders = ", ".join([param_marker] * len(cols))
            cols_str = ", ".join([f'"{c}"' for c in cols])

            conflict_clause = ""
            if conflict_col and conflict_col in cols:
                conflict_clause = f' ON CONFLICT ("{conflict_col}") DO NOTHING'

            sql = f'INSERT INTO "{table_name}" ({cols_str}) VALUES ({placeholders}){conflict_clause};'
            values = tuple(r[c] for c in cols)
            statements.append((sql, values))

        return statements

    def write_records(
        self,
        table_name: str,
        records: List[Dict[str, Any]],
        dry_run: bool = True,
        conflict_col: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Executes atomic batch write or dry-run preview.
        """
        if not records:
            return {"inserted_count": 0, "dry_run": dry_run, "statements_count": 0}

        statements = self.generate_insert_sql(
            table_name, records, conflict_col=conflict_col, dialect=self.dialect
        )

        if dry_run or not self.connection:
            return {
                "inserted_count": len(records),
                "dry_run": True,
                "statements_count": len(statements),
                "preview_sql": statements[0][0] if statements else "",
            }

        # Actual DB execution in a single atomic transaction
        cursor = self.connection.cursor()
        try:
            for sql, params in statements:
                cursor.execute(sql, params)
            self.connection.commit()
            return {
                "inserted_count": len(records),
                "dry_run": False,
                "statements_count": len(statements),
            }
        except Exception as e:
            self.connection.rollback()
            raise RuntimeError(f"Transaction failed and was rolled back: {e}") from e
        finally:
            cursor.close()
