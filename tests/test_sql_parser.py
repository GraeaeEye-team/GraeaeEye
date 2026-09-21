"""
Tests for dynamic SQL schema parser.
"""

from smart_credit_parser.schema.sql_parser import SQLSchemaParser

from tests.conftest import SCHEMA_PATH


def test_parse_schema_sql_file():
    assert SCHEMA_PATH.exists(), f"schema.sql not found at {SCHEMA_PATH}"
    schema = SQLSchemaParser.parse_file(SCHEMA_PATH)

    # 1. Check all 13 canonical tables are discovered
    expected_tables = {
        "businesses",
        "shareholders",
        "web_reputation",
        "macro_sector_metrics",
        "counterparties",
        "invoices",
        "bank_accounts",
        "transactions",
        "credit_obligations",
        "users",
        "user_settings",
        "analysis_runs",
        "analysis_logs",
    }
    parsed_tables = set(schema.tables.keys())
    assert expected_tables.issubset(
        parsed_tables
    ), f"Missing tables: {expected_tables - parsed_tables}"

    # 2. Check businesses table properties
    biz = schema.get_table("businesses")
    assert biz is not None
    assert biz.columns["business_id"].is_primary_key is True
    assert biz.columns["tax_id"].is_unique is True
    assert biz.columns["tax_id"].is_nullable is False
    assert biz.columns["legal_name"].is_nullable is False
    assert biz.columns["industry_code"].is_nullable is False
    assert biz.columns["registration_date"].is_nullable is False

    # 3. Check ENUM / CHECK constraints on counterparties
    cp = schema.get_table("counterparties")
    assert cp is not None
    role_col = cp.columns["counterparty_role"]
    assert role_col.allowed_values is not None
    assert set(role_col.allowed_values) == {"CLIENT", "SUPPLIER", "MIXED", "BOTH"}

    # 4. Check invoices constraints
    inv = schema.get_table("invoices")
    assert inv is not None
    type_col = inv.columns["invoice_type"]
    assert set(type_col.allowed_values) == {"RECEIVABLE", "PAYABLE"}
    status_col = inv.columns["status"]
    assert set(status_col.allowed_values) == {
        "PAID",
        "SETTLED",
        "OUTSTANDING",
        "OVERDUE",
        "DEFAULTED",
        "DISPUTED",
    }
    assert inv.columns["gross_amount"].numeric_min == 0.0

    # 5. Check foreign keys
    assert any(
        fk.referenced_table == "businesses" and fk.column_name == "business_id"
        for fk in inv.foreign_keys
    )
    assert any(
        fk.referenced_table == "counterparties"
        and fk.column_name == "counterparty_id"
        for fk in inv.foreign_keys
    )

    # 6. Check transactions constraints
    tx = schema.get_table("transactions")
    assert tx is not None
    assert set(tx.columns["direction"].allowed_values) == {"INFLOW", "OUTFLOW"}
    assert "REVENUE" in tx.columns["category"].allowed_values
    assert "IMMEDIATE_CASH" in tx.columns["liquidity_class"].allowed_values

    # 7. Check topological order
    topo = [t.lower() for t in schema.topological_order]
    assert topo.index("businesses") < topo.index("counterparties")
    assert topo.index("businesses") < topo.index("invoices")
    assert topo.index("counterparties") < topo.index("invoices")
    assert topo.index("bank_accounts") < topo.index("transactions")
    assert topo.index("invoices") < topo.index("transactions")
