"""
End-to-End Tests for UniversalDataParser across multiple formats, languages, edge cases, and sponsor pack.
"""

import json
from pathlib import Path
import os
import zipfile
import pytest
import openpyxl

from smart_credit_parser import (
    UniversalDataParser,
    ParseOptions,
)

from tests.conftest import SCHEMA_PATH

SPONSOR_ZIP = Path(os.getenv("SPONSOR_ZIP", r"c:\Users\skv1d\Downloads\Telegram Desktop\sponsor_pack.zip"))
SPONSOR_SAMPLE = Path(__file__).resolve().parent.parent / "samples" / "5_sponsor_pack_sample.csv"


@pytest.fixture
def parser():
    return UniversalDataParser(schema_path=SCHEMA_PATH)


def test_e2e_canonical_csv_fast_path(tmp_path: Path, parser):
    """Test standard format file: fast path used, 0 LLM calls, perfect parse."""
    csv_file = tmp_path / "canonical_businesses.csv"
    csv_file.write_text(
        "business_id,tax_id,legal_name,industry_code,registration_date,total_board_seats\n"
        "550e8400-e29b-41d4-a716-446655440001,1002600001001,AgroStandard SRL,A-01,2020-01-15,3\n"
        "550e8400-e29b-41d4-a716-446655440002,1002600001002,TechStandard SRL,J-62,2021-06-20,1\n",
        encoding="utf-8",
    )

    result = parser.parse_file(csv_file)
    assert result.success is True
    assert result.report.fast_path_used is True
    assert result.report.rows_accepted == 2
    assert result.report.rows_rejected == 0
    assert result.accepted_records[0]["tax_id"] == "1002600001001"
    assert result.accepted_records[0]["total_board_seats"] == 3


def test_e2e_arbitrary_russian_csv(tmp_path: Path, parser):
    """Test arbitrary format in Russian with non-standard dates and European numbers."""
    csv_file = tmp_path / "russian_companies.csv"
    content = (
        "ИНН;Название компании;Отрасль;Дата регистрации;Мест в совете\n"
        "1002600009991;МолдТехЭкспорт SRL;IT;15.05.2019;2\n"
        "1002600009992;ВинЗавод Плюс SA;Wine;22/11/2015;5\n"
    )
    csv_file.write_bytes(content.encode("cp1251"))

    result = parser.parse_file(csv_file, options=ParseOptions(target_table="businesses"))
    assert result.success is True
    assert result.report.target_table == "businesses"
    assert result.report.rows_accepted == 2
    assert result.accepted_records[0]["registration_date"] == "2019-05-15"
    assert result.accepted_records[1]["registration_date"] == "2015-11-22"


def test_e2e_romanian_excel_invoices(tmp_path: Path, parser):
    """Test Romanian invoices in Excel with European currency and statuses."""
    xlsx_file = tmp_path / "facturi.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Tip factura", "Suma", "Data emiterii", "Data scadenta", "Statut"])
    ws.append(["creanta", "15 450,50 MDL", "10.01.2025", "10.02.2025", "platit"])
    ws.append(["datorie", "8 200,00", "15.01.2025", "15.02.2025", "restant"])
    wb.save(xlsx_file)

    # Provide context keys for foreign keys missing in flat invoice sheet
    opts = ParseOptions(
        target_table="invoices",
        context_keys={
            "business_id": "550e8400-e29b-41d4-a716-446655440000",
            "counterparty_id": "660e8400-e29b-41d4-a716-446655440000",
        },
    )
    result = parser.parse_file(xlsx_file, options=opts)
    assert result.success is True
    assert result.report.rows_accepted == 2
    assert result.accepted_records[0]["invoice_type"] == "RECEIVABLE"
    assert result.accepted_records[0]["gross_amount"] == 15450.50
    assert result.accepted_records[0]["status"] == "PAID"
    assert result.accepted_records[1]["invoice_type"] == "PAYABLE"
    assert result.accepted_records[1]["status"] == "OVERDUE"


def test_e2e_json_transactions(tmp_path: Path, parser):
    """Test JSON bank transactions with debit/credit and various timestamp formats."""
    json_file = tmp_path / "transactions.json"
    data = [
        {
            "transaction_date": "2025-03-01T14:20:00Z",
            "valoare_tranzactie": "4500.00",
            "direction": "credit",
            "category": "revenue",
            "liquidity_class": "cash",
        },
        {
            "transaction_date": "2025-03-02 09:15:00",
            "valoare_tranzactie": "1200.50",
            "direction": "debit",
            "category": "payroll",
            "liquidity_class": "immediate_cash",
        },
    ]
    json_file.write_text(json.dumps(data), encoding="utf-8")

    opts = ParseOptions(
        target_table="transactions",
        context_keys={
            "business_id": "550e8400-e29b-41d4-a716-446655440000",
            "account_id": "770e8400-e29b-41d4-a716-446655440000",
        },
    )
    result = parser.parse_file(json_file, options=opts)
    assert result.success is True
    assert result.report.rows_accepted == 2
    assert result.accepted_records[0]["direction"] == "INFLOW"
    assert result.accepted_records[0]["category"] == "REVENUE"
    assert result.accepted_records[1]["direction"] == "OUTFLOW"
    assert result.accepted_records[1]["category"] == "PAYROLL"


def test_e2e_empty_and_corrupt_file(tmp_path: Path, parser):
    """Test that empty or unparseable files fail gracefully with diagnostic error message."""
    empty_file = tmp_path / "empty.csv"
    empty_file.write_text("", encoding="utf-8")

    result = parser.parse_file(empty_file)
    assert result.success is False
    assert result.report.rows_accepted == 0
    assert any("Empty File" in item.get("item", "") for item in result.report.human_review_required)


def test_e2e_constraint_violations_and_duplicates(tmp_path: Path, parser):
    """Test that rows violating CHECK or UNIQUE constraints are rejected and reported."""
    csv_file = tmp_path / "invalid_companies.csv"
    csv_file.write_text(
        "tax_id,legal_name,industry_code,registration_date,total_board_seats\n"
        "1002600005555,Valid Firm 1,IT,2020-01-01,2\n"
        "1002600005555,Duplicate Tax ID Firm,IT,2020-01-01,2\n"  # Duplicate tax_id
        "1002600005556,Invalid Seats Firm,IT,2020-01-01,0\n",     # Violates total_board_seats >= 1
        encoding="utf-8",
    )

    result = parser.parse_file(csv_file)
    assert result.report.rows_accepted == 1
    assert result.report.rows_rejected == 2
    assert len(result.report.rejected_details) == 2
    assert any("UNIQUE" in err for err in result.report.rejected_details[0].errors)
    assert any("CHECK" in err for err in result.report.rejected_details[1].errors)


def test_e2e_sponsor_pack_benchmark(tmp_path: Path, parser):
    """Test data sample from sponsor_pack (businesses.csv)."""
    if SPONSOR_ZIP.exists():
        with zipfile.ZipFile(SPONSOR_ZIP) as z:
            with z.open("sponsor_pack/businesses.csv") as f:
                lines = [f.readline() for _ in range(15)]
            sample_path = tmp_path / "sponsor_businesses.csv"
            sample_path.write_bytes(b"".join(lines))
    elif SPONSOR_SAMPLE.exists():
        sample_path = SPONSOR_SAMPLE
    else:
        pytest.skip("Neither sponsor_pack.zip nor samples/5_sponsor_pack_sample.csv was found.")

    result = parser.parse_file(
        sample_path,
        options=ParseOptions(
            target_table="businesses",
            context_keys={"registration_date": "2020-01-01", "total_board_seats": 1},
        ),
    )
    assert result.success is True
    assert result.report.rows_accepted > 0
    # Legal name should be parsed from sponsor pack
    assert "legal_name" in result.accepted_records[0]
    assert len(result.accepted_records[0]["legal_name"]) > 0
