"""
Tests for DataNormalizer: dates, currencies, decimals, booleans, and enums.
"""

import pytest
from smart_credit_parser.pipeline.normalizer import DataNormalizer


def test_date_normalization():
    assert DataNormalizer.normalize_date("2025-08-14") == "2025-08-14"
    assert DataNormalizer.normalize_date("14.08.2025") == "2025-08-14"
    assert DataNormalizer.normalize_date("14/08/2025") == "2025-08-14"
    assert DataNormalizer.normalize_date("2025-08-14T15:30:00Z") == "2025-08-14"
    assert DataNormalizer.normalize_date("") is None
    assert DataNormalizer.normalize_date(None) is None


def test_decimal_normalization():
    # Standard numbers
    assert DataNormalizer.normalize_decimal("1500.50") == 1500.50
    # European format with dot thousand separator and comma decimal
    assert DataNormalizer.normalize_decimal("1.250,50") == 1250.50
    # Currency symbols and spaces
    assert DataNormalizer.normalize_decimal("1 250,50 MDL") == 1250.50
    assert DataNormalizer.normalize_decimal("$4,500.00") == 4500.00
    assert DataNormalizer.normalize_decimal("€ 350.25") == 350.25
    # Negative in parentheses
    assert DataNormalizer.normalize_decimal("(500.00)") == -500.00
    assert DataNormalizer.normalize_decimal("-150.75") == -150.75


def test_boolean_normalization():
    assert DataNormalizer.normalize_boolean("true") is True
    assert DataNormalizer.normalize_boolean("1") is True
    assert DataNormalizer.normalize_boolean("да") is True
    assert DataNormalizer.normalize_boolean("yes") is True
    assert DataNormalizer.normalize_boolean("false") is False
    assert DataNormalizer.normalize_boolean("0") is False
    assert DataNormalizer.normalize_boolean("нет") is False
    assert DataNormalizer.normalize_boolean("no") is False


def test_enum_normalization():
    # Invoices
    assert DataNormalizer.normalize_enum("receivable", "invoice_type") == "RECEIVABLE"
    assert DataNormalizer.normalize_enum("paid_late", "status") == "OVERDUE"
    assert DataNormalizer.normalize_enum("settled", "status") == "SETTLED"

    # Counterparty role
    assert DataNormalizer.normalize_enum("поставщик", "counterparty_role") == "SUPPLIER"
    assert DataNormalizer.normalize_enum("buyer", "counterparty_role") == "CLIENT"

    # Transactions direction
    assert DataNormalizer.normalize_enum("debit", "direction") == "OUTFLOW"
    assert DataNormalizer.normalize_enum("credit", "direction") == "INFLOW"
    assert DataNormalizer.normalize_enum("приход", "direction") == "INFLOW"
