"""
Dynamic SQL DDL Parser for PostgreSQL schemas (schema.sql).
Extracts tables, columns, constraints, foreign keys, and ENUMs without hardcoding.
"""

from __future__ import annotations
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .models import ColumnSchema, ForeignKeyDef, SchemaGraph, TableSchema
from .dependency_graph import compute_topological_order


class SQLSchemaParser:
    """Parses SQL DDL files and produces a canonical SchemaGraph."""

    @classmethod
    def parse_file(cls, file_path: str | Path) -> SchemaGraph:
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Schema file not found at: {file_path}")
        content = path.read_text(encoding="utf-8")
        return cls.parse_sql(content)

    @classmethod
    def parse_sql(cls, sql_text: str) -> SchemaGraph:
        # 1. Remove comments
        clean_sql = cls._strip_comments(sql_text)

        # 2. Extract CREATE TABLE blocks
        tables: Dict[str, TableSchema] = {}
        table_blocks = cls._extract_table_blocks(clean_sql)

        for table_name, body in table_blocks:
            tbl_schema = cls._parse_table_body(table_name, body)
            tables[table_name] = tbl_schema

        # 3. Compute topological order
        topo_order = compute_topological_order(tables)

        return SchemaGraph(tables=tables, topological_order=topo_order)

    @staticmethod
    def _strip_comments(sql: str) -> str:
        # Strip block comments /* ... */
        sql = re.sub(r"/\*.*?\*/", "", sql, flags=re.DOTALL)
        # Strip line comments -- ...
        sql = re.sub(r"--.*?$", "", sql, flags=re.MULTILINE)
        return sql

    @classmethod
    def _extract_table_blocks(cls, sql: str) -> List[Tuple[str, str]]:
        """Finds all CREATE TABLE statements and extracts table name and body."""
        pattern = re.compile(
            r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([a-zA-Z0-9_\"\.]+)\s*\(",
            re.IGNORECASE,
        )
        results = []
        pos = 0
        while True:
            match = pattern.search(sql, pos)
            if not match:
                break
            raw_tbl_name = match.group(1).replace('"', "").split(".")[-1]
            start_paren = match.end() - 1

            # Match closing parenthesis of CREATE TABLE
            depth = 0
            end_paren = -1
            in_quote = False
            quote_char = ""
            for i in range(start_paren, len(sql)):
                ch = sql[i]
                if ch in ("'", '"'):
                    if not in_quote:
                        in_quote = True
                        quote_char = ch
                    elif quote_char == ch:
                        in_quote = False
                elif not in_quote:
                    if ch == "(":
                        depth += 1
                    elif ch == ")":
                        depth -= 1
                        if depth == 0:
                            end_paren = i
                            break

            if end_paren != -1:
                body = sql[start_paren + 1 : end_paren]
                results.append((raw_tbl_name, body))
                pos = end_paren + 1
            else:
                pos = match.end()

        return results

    @classmethod
    def _split_definitions(cls, body: str) -> List[str]:
        """Splits comma-separated definitions inside CREATE TABLE handling nested parentheses and quotes."""
        items = []
        current = []
        depth = 0
        in_quote = False
        quote_char = ""

        for ch in body:
            if ch in ("'", '"'):
                if not in_quote:
                    in_quote = True
                    quote_char = ch
                elif quote_char == ch:
                    in_quote = False
                current.append(ch)
            elif not in_quote:
                if ch == "(":
                    depth += 1
                    current.append(ch)
                elif ch == ")":
                    depth -= 1
                    current.append(ch)
                elif ch == "," and depth == 0:
                    item_str = "".join(current).strip()
                    if item_str:
                        items.append(item_str)
                    current = []
                else:
                    current.append(ch)
            else:
                current.append(ch)

        last_item = "".join(current).strip()
        if last_item:
            items.append(last_item)

        return items

    @classmethod
    def _parse_table_body(cls, table_name: str, body: str) -> TableSchema:
        definitions = cls._split_definitions(body)
        columns: Dict[str, ColumnSchema] = {}
        primary_key: List[str] = []
        foreign_keys: List[ForeignKeyDef] = []
        unique_constraints: List[List[str]] = []
        check_constraints: List[str] = []

        for defn in definitions:
            line = " ".join(defn.split()).strip()
            upper_line = line.upper()

            # 1. Table-level PRIMARY KEY (col1, col2)
            pk_match = re.match(r"^PRIMARY\s+KEY\s*\((.*?)\)", line, re.IGNORECASE)
            if pk_match:
                pk_cols = [
                    c.strip().replace('"', "") for c in pk_match.group(1).split(",")
                ]
                primary_key.extend(pk_cols)
                continue

            # 2. Table-level FOREIGN KEY (col) REFERENCES ref_tbl(ref_col)
            fk_match = re.match(
                r"^FOREIGN\s+KEY\s*\((.*?)\)\s+REFERENCES\s+([a-zA-Z0-9_]+)\s*\((.*?)\)(?:\s+ON\s+DELETE\s+([A-Z\s]+))?",
                line,
                re.IGNORECASE,
            )
            if fk_match:
                fk_col = fk_match.group(1).strip().replace('"', "")
                ref_tbl = fk_match.group(2).strip().replace('"', "")
                ref_col = fk_match.group(3).strip().replace('"', "")
                on_del = (fk_match.group(4) or "NO ACTION").strip().upper()
                foreign_keys.append(
                    ForeignKeyDef(
                        column_name=fk_col,
                        referenced_table=ref_tbl,
                        referenced_column=ref_col,
                        on_delete=on_del,
                    )
                )
                continue

            # 3. Table-level UNIQUE (col1, ...)
            unq_match = re.match(r"^UNIQUE\s*\((.*?)\)", line, re.IGNORECASE)
            if unq_match:
                unq_cols = [
                    c.strip().replace('"', "") for c in unq_match.group(1).split(",")
                ]
                unique_constraints.append(unq_cols)
                continue

            # 4. Table-level CHECK (...)
            chk_match = re.match(r"^CHECK\s*\((.*)\)$", line, re.IGNORECASE | re.DOTALL)
            if chk_match:
                check_constraints.append(chk_match.group(1).strip())
                continue

            # 5. Column definition
            col = cls._parse_column_definition(line)
            if col:
                columns[col.name] = col
                if col.is_primary_key and col.name not in primary_key:
                    primary_key.append(col.name)
                if col.foreign_key_table and col.foreign_key_column:
                    foreign_keys.append(
                        ForeignKeyDef(
                            column_name=col.name,
                            referenced_table=col.foreign_key_table,
                            referenced_column=col.foreign_key_column,
                            on_delete=col.on_delete or "NO ACTION",
                        )
                    )

        # Mark PK columns
        for pk_col in primary_key:
            if pk_col in columns:
                columns[pk_col].is_primary_key = True

        return TableSchema(
            name=table_name,
            columns=columns,
            primary_key=primary_key,
            foreign_keys=foreign_keys,
            unique_constraints=unique_constraints,
            check_constraints=check_constraints,
        )

    @classmethod
    def _parse_column_definition(cls, line: str) -> Optional[ColumnSchema]:
        """Parses a single column definition string."""
        # Match column name and data type: col_name DATA_TYPE(...)
        match = re.match(
            r'^([a-zA-Z0-9_"]+)\s+([a-zA-Z0-9_]+(?:\s*\([^\)]+\))?(?:\s+WITH\s+TIME\s+ZONE)?)(.*)$',
            line,
            re.IGNORECASE,
        )
        if not match:
            return None

        col_name = match.group(1).strip().replace('"', "")
        raw_type = match.group(2).strip()
        rest = match.group(3).strip()

        # Normalize data type
        clean_type = " ".join(raw_type.split()).upper()

        is_pk = bool(re.search(r"\bPRIMARY\s+KEY\b", rest, re.IGNORECASE))
        is_unique = bool(re.search(r"\bUNIQUE\b", rest, re.IGNORECASE))
        is_nullable = not bool(re.search(r"\bNOT\s+NULL\b", rest, re.IGNORECASE))
        if is_pk:
            is_nullable = False

        # Extract DEFAULT expr
        default_value = None
        def_match = re.search(
            r"\bDEFAULT\s+('(?:''|[^'])*'|\S+)", rest, re.IGNORECASE
        )
        if def_match:
            default_value = def_match.group(1).strip()
            # If default has cast e.g. '{}'::jsonb
            cast_match = re.search(
                r"\bDEFAULT\s+('(?:''|[^'])*'|\S+)::([a-zA-Z0-9_]+)",
                rest,
                re.IGNORECASE,
            )
            if cast_match:
                default_value = f"{cast_match.group(1)}::{cast_match.group(2)}"

        # Extract inline REFERENCES
        fk_table = None
        fk_col = None
        on_delete = None
        ref_match = re.search(
            r"\bREFERENCES\s+([a-zA-Z0-9_]+)\s*\(([a-zA-Z0-9_]+)\)(?:\s+ON\s+DELETE\s+([A-Z\s]+))?",
            rest,
            re.IGNORECASE,
        )
        if ref_match:
            fk_table = ref_match.group(1).strip()
            fk_col = ref_match.group(2).strip()
            on_delete = (ref_match.group(3) or "NO ACTION").strip().upper()

        # Extract inline CHECK expression
        check_expr = None
        allowed_values = None
        num_min = None
        num_max = None

        chk_match = re.search(r"\bCHECK\s*\((.*)\)", rest, re.IGNORECASE)
        if chk_match:
            check_expr = chk_match.group(1).strip()

            # Check for IN ('A', 'B', ...)
            enum_match = re.search(
                rf"{col_name}\s+IN\s*\((.*?)\)", check_expr, re.IGNORECASE
            )
            if not enum_match:
                # Fallback: any IN ('A', 'B')
                enum_match = re.search(r"\bIN\s*\((.*?)\)", check_expr, re.IGNORECASE)
            if enum_match:
                raw_vals = enum_match.group(1)
                allowed_values = [
                    v.strip().strip("'\"")
                    for v in re.findall(r"'(?:''|[^'])*'", raw_vals)
                ]

            # Check for numeric min: col >= 0 or col > 0
            min_match = re.search(
                rf"{col_name}\s*(>=|>)\s*([0-9\.\-]+)", check_expr, re.IGNORECASE
            )
            if min_match:
                try:
                    num_min = float(min_match.group(2))
                except ValueError:
                    pass

            # Check for numeric max: col <= X or col < X
            max_match = re.search(
                rf"{col_name}\s*(<=|<)\s*([0-9\.\-]+)", check_expr, re.IGNORECASE
            )
            if max_match:
                try:
                    num_max = float(max_match.group(2))
                except ValueError:
                    pass

            # Check for BETWEEN min AND max
            between_match = re.search(
                rf"{col_name}\s+BETWEEN\s+([0-9\.\-]+)\s+AND\s+([0-9\.\-]+)",
                check_expr,
                re.IGNORECASE,
            )
            if between_match:
                try:
                    num_min = float(between_match.group(1))
                    num_max = float(between_match.group(2))
                except ValueError:
                    pass

        return ColumnSchema(
            name=col_name,
            data_type=clean_type,
            is_nullable=is_nullable,
            is_primary_key=is_pk,
            is_unique=is_unique,
            default_value=default_value,
            check_expression=check_expr,
            allowed_values=allowed_values,
            numeric_min=num_min,
            numeric_max=num_max,
            foreign_key_table=fk_table,
            foreign_key_column=fk_col,
            on_delete=on_delete,
        )
