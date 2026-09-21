"""
Deterministic Normalizer for dates, currencies, decimals, booleans, and ENUM values.
Converts arbitrary client inputs into PostgreSQL 16 canonical types according to schema.
"""

from __future__ import annotations
import re
from datetime import datetime
from typing import Any, Dict, List, Optional
import uuid

# Common ENUM synonyms mapping
ENUM_SYNONYMS: Dict[str, Dict[str, str]] = {
    "direction": {
        "debit": "OUTFLOW",
        "credit": "INFLOW",
        "in": "INFLOW",
        "out": "OUTFLOW",
        "inflow": "INFLOW",
        "outflow": "OUTFLOW",
        "приход": "INFLOW",
        "расход": "OUTFLOW",
        "intrare": "INFLOW",
        "iesire": "OUTFLOW",
    },
    "invoice_type": {
        "receivable": "RECEIVABLE",
        "payable": "PAYABLE",
        "продажа": "RECEIVABLE",
        "покупка": "PAYABLE",
        "входящий": "PAYABLE",
        "исходящий": "RECEIVABLE",
        "creanta": "RECEIVABLE",
        "datorie": "PAYABLE",
    },
    "status": {
        "paid": "PAID",
        "settled": "SETTLED",
        "paid_late": "OVERDUE",
        "overdue": "OVERDUE",
        "outstanding": "OUTSTANDING",
        "defaulted": "DEFAULTED",
        "disputed": "DISPUTED",
        "оплачен": "PAID",
        "просрочен": "OVERDUE",
        "не_оплачен": "OUTSTANDING",
        "platit": "PAID",
        "restant": "OVERDUE",
    },
    "counterparty_role": {
        "client": "CLIENT",
        "customer": "CLIENT",
        "buyer": "CLIENT",
        "клиент": "CLIENT",
        "покупатель": "CLIENT",
        "supplier": "SUPPLIER",
        "vendor": "SUPPLIER",
        "поставщик": "SUPPLIER",
        "furnizor": "SUPPLIER",
        "both": "BOTH",
        "mixed": "MIXED",
    },
    "facility_type": {
        "loan": "TERM_LOAN",
        "term_loan": "TERM_LOAN",
        "credit": "TERM_LOAN",
        "credit_line": "CREDIT_LINE",
        "line_of_credit": "LINE_OF_CREDIT",
        "overdraft": "OVERDRAFT",
        "leasing": "LEASING",
        "factoring": "FACTORING",
        "лизинг": "LEASING",
        "кредит": "TERM_LOAN",
    },
    "category": {
        "revenue": "REVENUE",
        "client_revenue": "CLIENT_REVENUE",
        "operating_expense": "OPERATING_EXPENSE",
        "supplier_payment": "SUPPLIER_PAYMENT",
        "payroll": "PAYROLL",
        "salary": "PAYROLL",
        "зарплата": "PAYROLL",
        "tax": "TAX",
        "taxes": "TAX",
        "налоги": "TAX",
        "debt_service": "DEBT_SERVICE",
        "credit_repayment": "CREDIT_REPAYMENT",
        "interest_fee": "INTEREST_FEE",
        "dividend": "DIVIDEND",
        "other": "OTHER",
    },
    "liquidity_class": {
        "immediate_cash": "IMMEDIATE_CASH",
        "cash": "IMMEDIATE_CASH",
        "restricted_escrow": "RESTRICTED_ESCROW",
        "term_deposit": "TERM_DEPOSIT",
        "short_term_receivable": "SHORT_TERM_RECEIVABLE",
        "tied_capital": "TIED_CAPITAL",
    }
}


class DataNormalizer:
    """Normalizes raw string values into canonical database types."""

    @staticmethod
    def normalize_date(value: Any) -> Optional[str]:
        """Normalizes date string into YYYY-MM-DD."""
        if value is None:
            return None
        val_str = str(value).strip()
        if not val_str:
            return None

        # Already YYYY-MM-DD
        if re.match(r"^\d{4}-\d{2}-\d{2}$", val_str):
            return val_str

        # ISO timestamp YYYY-MM-DDTHH:MM:SS
        iso_m = re.match(r"^(\d{4}-\d{2}-\d{2})[T\s]", val_str)
        if iso_m:
            return iso_m.group(1)

        # European DD.MM.YYYY or DD/MM/YYYY or DD-MM-YYYY
        eu_m = re.match(r"^(\d{1,2})[\./\-](\d{1,2})[\./\-](\d{4})$", val_str)
        if eu_m:
            d, m, y = eu_m.groups()
            return f"{int(y):04d}-{int(m):02d}-{int(d):02d}"

        # US MM/DD/YYYY
        # Try parsing via datetime heuristics
        for fmt in ("%d.%m.%Y", "%d/%m/%Y", "%m/%d/%Y", "%Y/%m/%d", "%d-%m-%Y"):
            try:
                dt = datetime.strptime(val_str, fmt)
                return dt.strftime("%Y-%m-%d")
            except ValueError:
                continue

        return val_str

    @staticmethod
    def normalize_timestamp(value: Any) -> Optional[str]:
        """Normalizes timestamp into ISO 8601 string with timezone."""
        if value is None:
            return None
        val_str = str(value).strip()
        if not val_str:
            return None

        # Check if already ISO format
        if re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", val_str):
            if not val_str.endswith("Z") and "+" not in val_str and "-" not in val_str[10:]:
                return f"{val_str}+00:00"
            return val_str

        # Date only: append midnight UTC
        date_only = DataNormalizer.normalize_date(val_str)
        if date_only and re.match(r"^\d{4}-\d{2}-\d{2}$", date_only):
            return f"{date_only}T00:00:00+00:00"

        return val_str

    @staticmethod
    def normalize_decimal(value: Any) -> Optional[float]:
        """Parses float/decimal from arbitrary currency string or number."""
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return float(value)

        val_str = str(value).strip()
        if not val_str:
            return None

        # Negative number in parentheses e.g. (100.50) -> -100.50
        is_negative = False
        if val_str.startswith("(") and val_str.endswith(")"):
            is_negative = True
            val_str = val_str[1:-1].strip()
        elif val_str.startswith("-"):
            is_negative = True
            val_str = val_str[1:].strip()

        # Remove currency words/symbols
        clean = re.sub(r"[^\d\.,]", "", val_str)
        if not clean:
            return None

        # Handle European 1.250,50 vs US 1,250.50
        if "," in clean and "." in clean:
            if clean.rfind(",") > clean.rfind("."):
                # 1.250,50 -> 1250.50
                clean = clean.replace(".", "").replace(",", ".")
            else:
                # 1,250.50 -> 1250.50
                clean = clean.replace(",", "")
        elif "," in clean and "." not in clean:
            # Check if comma is decimal or thousands separator
            parts = clean.split(",")
            if len(parts) == 2 and len(parts[1]) <= 2:
                # 1250,50 -> 1250.50
                clean = clean.replace(",", ".")
            else:
                # 1,250 -> 1250
                clean = clean.replace(",", "")

        try:
            num = float(clean)
            return -num if is_negative else num
        except ValueError:
            return None

    @staticmethod
    def normalize_int(value: Any) -> Optional[int]:
        dec = DataNormalizer.normalize_decimal(value)
        return int(round(dec)) if dec is not None else None

    @staticmethod
    def normalize_boolean(value: Any) -> Optional[bool]:
        if value is None:
            return None
        if isinstance(value, bool):
            return value
        val_str = str(value).strip().lower()
        if val_str in ("true", "t", "1", "yes", "y", "да", "д", "da"):
            return True
        if val_str in ("false", "f", "0", "no", "n", "нет", "н", "nu"):
            return False
        return None

    @staticmethod
    def normalize_enum(value: Any, column_name: str, allowed_values: Optional[List[str]] = None) -> Optional[str]:
        if value is None:
            return None
        val_str = str(value).strip()
        if not val_str:
            return None

        val_lower = val_str.lower().replace("-", "_").replace(" ", "_")

        # 1. Check known synonym dictionaries
        col_key = column_name.lower()
        if col_key in ENUM_SYNONYMS and val_lower in ENUM_SYNONYMS[col_key]:
            return ENUM_SYNONYMS[col_key][val_lower]

        # 2. Match directly against allowed values (case-insensitive)
        if allowed_values:
            for av in allowed_values:
                if av.lower() == val_lower:
                    return av

            # Try prefix / substring match
            for av in allowed_values:
                if av.lower() in val_lower or val_lower in av.lower():
                    return av

        return val_str.upper()

    @staticmethod
    def normalize_uuid(value: Any) -> Optional[str]:
        if value is None:
            return None
        val_str = str(value).strip()
        if not val_str:
            return None
        try:
            return str(uuid.UUID(val_str))
        except ValueError:
            # Deterministic UUID from non-empty string
            return str(uuid.uuid5(uuid.NAMESPACE_DNS, val_str))

    @classmethod
    def normalize_value(cls, value: Any, data_type: str, column_name: str, allowed_values: Optional[List[str]] = None) -> Any:
        dtype = data_type.upper()
        if "UUID" in dtype:
            return cls.normalize_uuid(value)
        if "INT" in dtype or "SERIAL" in dtype:
            return cls.normalize_int(value)
        if "DECIMAL" in dtype or "NUMERIC" in dtype or "FLOAT" in dtype:
            return cls.normalize_decimal(value)
        if "BOOL" in dtype:
            return cls.normalize_boolean(value)
        if "TIMESTAMP" in dtype:
            return cls.normalize_timestamp(value)
        if "DATE" in dtype:
            return cls.normalize_date(value)
        if allowed_values:
            return cls.normalize_enum(value, column_name, allowed_values)

        # String / text
        return str(value).strip() if value is not None else None
