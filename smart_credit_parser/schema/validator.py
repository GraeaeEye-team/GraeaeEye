"""
Deterministic Schema Validator.
Validates records against TableSchema definitions derived from schema.sql.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set
from .models import TableSchema
from ..pipeline.normalizer import DataNormalizer


@dataclass
class ValidationResult:
    is_valid: bool
    data: Dict[str, Any]
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


class SchemaValidator:
    """Validates records strictly against canonical TableSchema rules."""

    def __init__(self, table_schema: TableSchema):
        self.schema = table_schema

    def validate_and_normalize(
        self,
        raw_record: Dict[str, Any],
        known_pks: Optional[Dict[str, Set[str]]] = None,
        seen_uniques: Optional[Dict[str, Set[str]]] = None,
    ) -> ValidationResult:
        """
        Normalizes and validates a single record dictionary.
        known_pks: optional dict of table_name -> set of valid IDs for foreign key validation.
        seen_uniques: optional dict of col_name -> set of already seen values in batch for unique validation.
        """
        errors: List[str] = []
        warnings: List[str] = []
        clean_record: Dict[str, Any] = {}

        # 1. Process and normalize each column in schema
        for col_name, col in self.schema.columns.items():
            # Lookup value in raw_record (case-insensitive)
            raw_val = None
            for rk, rv in raw_record.items():
                if rk.lower() == col_name.lower():
                    raw_val = rv
                    break

            # Handle missing or empty values
            if raw_val is None or (isinstance(raw_val, str) and raw_val.strip() == ""):
                if col.is_required:
                    errors.append(f"Required column '{col_name}' is missing or empty.")
                    continue
                elif col.default_value is not None:
                    # Let default handle it or apply simple literal defaults
                    if col.default_value.startswith("'") and col.default_value.endswith("'"):
                        clean_record[col_name] = col.default_value.strip("'")
                    elif col.default_value.isdigit():
                        clean_record[col_name] = int(col.default_value)
                    else:
                        clean_record[col_name] = None
                    continue
                else:
                    clean_record[col_name] = None
                    continue

            # 2. Normalize value to target type
            try:
                norm_val = DataNormalizer.normalize_value(
                    raw_val,
                    data_type=col.data_type,
                    column_name=col_name,
                    allowed_values=col.allowed_values,
                )
            except Exception as e:
                errors.append(f"Failed to normalize column '{col_name}' with value '{raw_val}': {e}")
                continue

            # 3. Check NOT NULL constraint
            if not col.is_nullable and norm_val is None:
                errors.append(f"Column '{col_name}' cannot be NULL (received: '{raw_val}').")
                continue

            # 4. Check ENUM / allowed_values
            if col.allowed_values is not None and norm_val is not None:
                if norm_val not in col.allowed_values:
                    errors.append(
                        f"Column '{col_name}' value '{norm_val}' is invalid. "
                        f"Allowed values: {col.allowed_values}"
                    )
                    continue

            # 5. Check numeric ranges / CHECK constraints
            if isinstance(norm_val, (int, float)):
                if col.numeric_min is not None and norm_val < col.numeric_min:
                    errors.append(
                        f"Column '{col_name}' value {norm_val} violates CHECK constraint (min {col.numeric_min})."
                    )
                    continue
                if col.numeric_max is not None and norm_val > col.numeric_max:
                    errors.append(
                        f"Column '{col_name}' value {norm_val} violates CHECK constraint (max {col.numeric_max})."
                    )
                    continue

            # 6. Check unique constraint
            if col.is_unique and norm_val is not None and seen_uniques is not None:
                seen_set = seen_uniques.setdefault(col_name, set())
                str_key = str(norm_val)
                if str_key in seen_set:
                    errors.append(
                        f"Column '{col_name}' value '{norm_val}' violates UNIQUE constraint (duplicate)."
                    )
                    continue
                seen_set.add(str_key)

            # 7. Check foreign keys
            if col.foreign_key_table and norm_val is not None and known_pks is not None:
                ref_tbl = col.foreign_key_table.lower()
                if ref_tbl in known_pks:
                    if str(norm_val) not in known_pks[ref_tbl]:
                        errors.append(
                            f"Foreign key violation: '{col_name}' value '{norm_val}' "
                            f"does not exist in referenced table '{col.foreign_key_table}'."
                        )
                        continue

            clean_record[col_name] = norm_val

        return ValidationResult(
            is_valid=len(errors) == 0,
            data=clean_record,
            errors=errors,
            warnings=warnings,
        )
