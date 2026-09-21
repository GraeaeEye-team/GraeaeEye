"""
Deep test suite for financial document parsers (InvoiceParser, CreditObligationParser, BankStatementParser).
Validates multi-language support (RO/MD/RU), diacritics, number formats, dynamic opening balances,
and strict fail-fast exception handling without synthetic dummy data.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
import io
import os
import sys
from uuid import uuid4

import openpyxl
import pytest

sys.path.insert(0, os.path.abspath("src"))

from fintech_app.core.exceptions import ParsingError
from fintech_app.ingestion.parser import (
    BankStatementParser,
    CreditObligationParser,
    InvoiceParser,
)


def create_xlsx_bytes(headers: list[str], rows: list[list[object]]) -> bytes:
    """Helper to construct in-memory XLSX bytes for zero-mock parser testing."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    ws.append(headers)
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# =============================================================================
# 1. MULTI-LANGUAGE INVOICE PARSING (MD / RO / RU & DIACRITICS)
# =============================================================================


@pytest.mark.parametrize(
    "invoice_csv, expected_records",
    [
        (
            # Romanian with standard diacritics (ș, ț, ă, î, â)
            (
                "număr_factură,dată_emitere,termen_plată,sumă_totală,direcție,status,cui_furnizor\n"
                "FAC-2025-01,2025-03-01,2025-03-31,12500.50,INTRARE,ACHITAT,1002345678\n"
                "FAC-2025-02,2025-03-05,2025-04-05,9800.75,IESIRE,EXPIRAT,1009876543\n"
                "FAC-2025-03,2025-03-10,2025-04-10,4321.00,IESIRE,EMIS,1001112223\n"
            ),
            [
                {
                    "counterparty": "1002345678",
                    "gross_amount": Decimal("12500.50"),
                    "invoice_type": "PAYABLE",
                    "status": "SETTLED",
                    "due_date": date(2025, 3, 31),
                },
                {
                    "counterparty": "1009876543",
                    "gross_amount": Decimal("9800.75"),
                    "invoice_type": "RECEIVABLE",
                    "status": "OVERDUE",
                    "due_date": date(2025, 4, 5),
                },
                {
                    "counterparty": "1001112223",
                    "gross_amount": Decimal("4321.00"),
                    "invoice_type": "RECEIVABLE",
                    "status": "OUTSTANDING",
                    "due_date": date(2025, 4, 10),
                },
            ],
        ),
        (
            # Russian with Cyrillic column headers and localized statuses/directions
            (
                "номер_счета;дата_выставления;срок_оплаты;сумма;направление;статус;инн_контрагента\n"
                "СЧ-101;2025-01-15;2025-02-15;45 000,50;ВХОДЯЩИЙ;ОПЛАЧЕН;1234567890\n"
                "СЧ-102;2025-01-20;2025-02-20;18 200,00;ИСХОДЯЩИЙ;ПРОСРОЧЕН;9876543210\n"
            ),
            [
                {
                    "counterparty": "1234567890",
                    "gross_amount": Decimal("45000.50"),
                    "invoice_type": "PAYABLE",
                    "status": "SETTLED",
                    "due_date": date(2025, 2, 15),
                },
                {
                    "counterparty": "9876543210",
                    "gross_amount": Decimal("18200.00"),
                    "invoice_type": "RECEIVABLE",
                    "status": "OVERDUE",
                    "due_date": date(2025, 2, 20),
                },
            ],
        ),
    ],
)
def test_invoice_parser_multilingual_csv(invoice_csv: str, expected_records: list[dict[str, object]]):
    """Verifies that InvoiceParser correctly resolves RO/MD/RU diacritics, statuses, directions, and Decimal amounts."""
    parser = InvoiceParser()
    records = parser.parse_csv(invoice_csv.encode("utf-8"))

    assert len(records) == len(expected_records)
    for parsed, expected in zip(records, expected_records, strict=True):
        assert parsed.counterparty_name == expected["counterparty"]
        assert isinstance(parsed.gross_amount, Decimal)
        assert parsed.gross_amount == expected["gross_amount"]
        assert parsed.invoice_type == expected["invoice_type"]
        assert parsed.status == expected["status"]
        assert parsed.due_date == expected["due_date"]


def test_invoice_parser_xlsx():
    """Verifies XLSX parsing of invoice records with openpyxl binary stream."""
    parser = InvoiceParser()
    headers = ["numar_factura", "cui_client", "data_emiterii", "termen_plata", "suma_totala", "directie", "status"]
    rows = [
        ["INV-900", "100999001", "2025-02-01", "2025-03-01", "34500.25", "IESIRE", "ACHITAT"],
        ["INV-901", "100999002", "2025-02-10", "2025-03-10", "12100.00", "INTRARE", "EXPIRAT"],
    ]
    xlsx_bytes = create_xlsx_bytes(headers, rows)
    records = parser.parse_xlsx(xlsx_bytes)

    assert len(records) == 2
    assert records[0].counterparty_name == "100999001"
    assert records[0].gross_amount == Decimal("34500.25")
    assert records[0].invoice_type == "RECEIVABLE"
    assert records[0].status == "SETTLED"

    assert records[1].counterparty_name == "100999002"
    assert records[1].gross_amount == Decimal("12100.00")
    assert records[1].invoice_type == "PAYABLE"
    assert records[1].status == "OVERDUE"


# =============================================================================
# 2. CREDIT OBLIGATIONS EDGE CASES
# =============================================================================


def test_credit_obligation_edge_cases_csv():
    """
    Tests CreditObligationParser with spaced facility types ('КРЕДИТНАЯ ЛИНИЯ', 'LINIE CREDIT'),
    various past due ranges (0, 15, 45, 90+ days), interest rate strings ('14.5%', '0.145'),
    currencies, and zero/null collateral values.
    """
    parser = CreditObligationParser()
    csv_content = (
        "кредитор;вид_кредита;сумма_кредита;остаток_долга;ежемесячный_платеж;просрочка_дней;просрочка_90;дефолты;ставка;валюта;залог\n"
        "Banca de Economii;КРЕДИТНАЯ ЛИНИЯ;1 000 000,00;650 000,00;25 000,00;15;0;0;14.5%;MDL;0.00\n"
        "Moldindconbank;OVERDRAFT;200 000,00;180 000,00;10 000,00;45;0;0;0.125;EUR;None\n"
        "maib;LINIE CREDIT;500 000,00;500 000,00;15 000,00;0;2;1;11.0%;USD;500000.00\n"
        "Victoriabank;TERM_LOAN;750 000,00;200 000,00;30 000,00;0;0;0;9.5%;MDL;-\n"
    )

    records = parser.parse_csv(csv_content.encode("utf-8"))
    assert len(records) == 4

    # 1. Credit line in Russian with space
    rec1 = records[0]
    assert rec1.lender_name == "Banca de Economii"
    assert rec1.facility_type == "CREDIT_LINE"
    assert rec1.principal_amount == Decimal("1000000.00")
    assert rec1.outstanding_balance == Decimal("650000.00")
    assert rec1.monthly_payment == Decimal("25000.00")
    assert rec1.past_due_30d_count == 15
    assert rec1.past_due_90d_count == 0
    assert rec1.currency == "MDL"
    assert rec1.interest_rate == Decimal("14.5")
    assert rec1.collateral_value == Decimal("0.00")

    # 2. Overdraft in EUR with percentage decimal
    rec2 = records[1]
    assert rec2.facility_type == "OVERDRAFT"
    assert rec2.principal_amount == Decimal("200000.00")
    assert rec2.currency == "EUR"
    assert rec2.interest_rate == Decimal("0.125")
    assert rec2.collateral_value is None

    # 3. Romanian credit line with default and 90d
    rec3 = records[2]
    assert rec3.facility_type == "CREDIT_LINE"
    assert rec3.past_due_90d_count == 2
    assert rec3.historical_defaults_count == 1
    assert rec3.currency == "USD"
    assert rec3.collateral_value == Decimal("500000.00")

    # 4. Standard term loan
    rec4 = records[3]
    assert rec4.facility_type == "TERM_LOAN"
    assert rec4.principal_amount == Decimal("750000.00")
    assert rec4.outstanding_balance == Decimal("200000.00")


def test_credit_obligation_xlsx():
    """Validates XLSX parsing of credit obligations."""
    parser = CreditObligationParser()
    headers = ["creditor", "tip_credit", "suma_credit", "sold", "rata_lunara", "past_due_30d", "past_due_90d"]
    rows = [
        ["maib", "LINIE_DE_CREDIT", 450000.0, 300000.0, 12000.0, 0, 0],
        ["ProCredit Bank", "OVERDRAFT", 100000.0, 50000.0, 5000.0, 3, 1],
    ]
    xlsx_bytes = create_xlsx_bytes(headers, rows)
    records = parser.parse_xlsx(xlsx_bytes)

    assert len(records) == 2
    assert records[0].lender_name == "maib"
    assert records[0].facility_type == "CREDIT_LINE"
    assert records[0].principal_amount == Decimal("450000.00")
    assert records[0].outstanding_balance == Decimal("300000.00")

    assert records[1].lender_name == "ProCredit Bank"
    assert records[1].facility_type == "OVERDRAFT"
    assert records[1].past_due_30d_count == 3
    assert records[1].past_due_90d_count == 1


# =============================================================================
# 3. DYNAMIC OPENING BALANCE DETECTION IN BANK STATEMENTS
# =============================================================================


@pytest.mark.parametrize(
    "header_line, expected_opening_bal",
    [
        ("Sold initial: 45000.50 MDL", Decimal("45000.50")),
        ("Начальный остаток: 120 500,00 MDL", Decimal("120500.00")),
        ("Входящее сальдо: -1 250,00 MDL", Decimal("-1250.00")),
        ("Opening balance: -1250.00", Decimal("-1250.00")),
        ("Sold initial: 0.00 MDL", Decimal("0.00")),
        ("Начальный остаток 0.00", Decimal("0.00")),
    ],
)
def test_bank_statement_dynamic_opening_balance_csv(header_line: str, expected_opening_bal: Decimal):
    """
    Ensures BankStatementParser extracts dynamic opening balance across Romanian,
    Russian, and English statement headers, supporting negative and zero values.
    """
    parser = BankStatementParser()
    csv_text = (
        f"# Extrase de cont\n"
        f"# {header_line}\n"
        f"Data,Suma,Detalii,CUI\n"
        f"2025-01-10,1000.00,Incasare vanzari,1001\n"
        f"2025-01-11,-500.00,Plata chirie,1002\n"
    )

    payload = parser.parse_csv(
        csv_text.encode("utf-8"),
        account_id=uuid4(),
        business_id=uuid4(),
    )

    assert isinstance(payload.opening_balance, Decimal)
    assert payload.opening_balance == expected_opening_bal
    assert len(payload.lines) == 2
    # closing_balance = opening_balance + 1000.00 - 500.00
    expected_closing = expected_opening_bal + Decimal("500.00")
    assert payload.closing_balance == expected_closing


def test_bank_statement_opening_balance_missing_fallback():
    """When no opening balance header is present, defaults gracefully to Decimal('0.00')."""
    parser = BankStatementParser()
    csv_text = "Data,Suma,Detalii,CUI\n2025-01-10,2500.00,Incasare,1001\n"

    payload = parser.parse_csv(
        csv_text.encode("utf-8"),
        account_id=uuid4(),
        business_id=uuid4(),
    )
    assert payload.opening_balance == Decimal("0.00")
    assert payload.closing_balance == Decimal("2500.00")


def test_bank_statement_dynamic_opening_balance_xlsx():
    """Tests dynamic opening balance extraction from XLSX metadata rows."""
    parser = BankStatementParser()
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Extrase bancare maib"])
    ws.append(["Sold initial: 88500.75 MDL"])
    ws.append(["Data", "Suma", "Descriere", "CUI"])
    ws.append(["2025-01-15", 1500.0, "Vanzare", "100555"])
    buf = io.BytesIO()
    wb.save(buf)

    payload = parser.parse_xlsx(
        buf.getvalue(),
        account_id=uuid4(),
        business_id=uuid4(),
    )
    assert payload.opening_balance == Decimal("88500.75")
    assert payload.closing_balance == Decimal("90000.75")


# =============================================================================
# 4. STRICT FAIL-FAST & CORRUPT DOCUMENT HANDLING
# =============================================================================


@pytest.mark.parametrize(
    "corrupt_csv",
    [
        "",  # Completely empty string
        "   \n  \t  \n",  # Whitespace only
        "foo,bar,baz\n1,2,3\n",  # Missing mandatory date and amount
        "Data,Detalii\n2025-01-01,No amount column\n",  # Missing amount
    ],
)
def test_bank_statement_corrupt_files_fail_fast(corrupt_csv: str):
    """Validates that BankStatementParser raises ParsingError on corrupt files without synthetic rows."""
    parser = BankStatementParser()
    with pytest.raises(ParsingError):
        parser.parse_csv(
            corrupt_csv.encode("utf-8"),
            account_id=uuid4(),
            business_id=uuid4(),
        )


@pytest.mark.parametrize(
    "corrupt_csv",
    [
        b"",  # Empty bytes
        b"just,some,unrelated,columns\n1,2,3,4\n",  # Missing counterparty_name & gross_amount
        b"counterparty_name\nAcme Corp\n",  # Missing gross_amount
    ],
)
def test_invoice_parser_corrupt_files_fail_fast(corrupt_csv: bytes):
    """Validates that InvoiceParser raises ParsingError on missing mandatory columns."""
    parser = InvoiceParser()
    with pytest.raises(ParsingError):
        parser.parse_csv(corrupt_csv)


@pytest.mark.parametrize(
    "corrupt_csv",
    [
        b"",  # Empty bytes
        b"some_col,another_col\n1,2\n",  # Missing lender_name and principal_amount
        b"lender_name\nVictoriabank\n",  # Missing principal_amount
    ],
)
def test_credit_obligation_parser_corrupt_files_fail_fast(corrupt_csv: bytes):
    """Validates that CreditObligationParser raises ParsingError on missing mandatory columns."""
    parser = CreditObligationParser()
    with pytest.raises(ParsingError):
        parser.parse_csv(corrupt_csv)


def test_moldovan_invoice_exact_headers_and_diacritics():
    """Validates Romanian / Moldovan invoice parsing with diacritics and exact prompt headers."""
    csv_data = (
        "Număr factură;Data scadenței;Cumpărător (CUI/IDNO);Suma fără TVA;Direcție (Intrare/Ieșire);Statut (Achitat/Neachitat/Expirat)\n"
        "FAC-001;2025-05-15;Întreprinderea Ștefan Vodă S.R.L.;12 500,50 MDL;Intrare;Achitat\n"
        "FAC-002;2025-06-20;Compania 'Nistru-Agro' S.A.;-450.00;Ieșire;Neachitat\n"
        "FAC-003;2025-07-01;Românița-Grup S.R.L.;1.250.000,00;Iesire;Expirat\n"
    )
    parser = InvoiceParser()
    records = parser.parse_csv(csv_data)
    assert len(records) == 3

    assert records[0].counterparty_name == "Întreprinderea Ștefan Vodă S.R.L."
    assert records[0].gross_amount == Decimal("12500.50")
    assert records[0].invoice_type == "PAYABLE"
    assert records[0].status == "SETTLED"
    assert records[0].due_date == date(2025, 5, 15)

    assert records[1].counterparty_name == "Compania 'Nistru-Agro' S.A."
    assert records[1].gross_amount == Decimal("450.00")
    assert records[1].invoice_type == "RECEIVABLE"
    assert records[1].status == "OUTSTANDING"
    assert records[1].due_date == date(2025, 6, 20)

    assert records[2].counterparty_name == "Românița-Grup S.R.L."
    assert records[2].gross_amount == Decimal("1250000.00")
    assert records[2].invoice_type == "RECEIVABLE"
    assert records[2].status == "OVERDUE"
    assert records[2].due_date == date(2025, 7, 1)


def test_cyrillic_credit_obligations_exact_headers_and_normalization():
    """Validates Russian credit obligations with spaces in facility types and no principal_amount column."""
    csv_data = (
        "Кредитор;Номер договора;Тип обязательства;Остаток задолженности;Процентная ставка;Просрочка дней\n"
        "Moldindconbank S.A.;CR-2024/99;КРЕДИТНАЯ ЛИНИЯ;1.250.000,00;11.5%;0\n"
        "Victoriabank;CR-2023/12;ОВЕРДРАФТ;450 000,00 MDL;12.0%;15\n"
        "MAIB;L-001;ЛИЗИНГ;850000;9.5%;0\n"
    )
    parser = CreditObligationParser()
    records = parser.parse_csv(csv_data)
    assert len(records) == 3

    assert records[0].lender_name == "Moldindconbank S.A."
    assert records[0].facility_type == "CREDIT_LINE"
    assert records[0].outstanding_balance == Decimal("1250000.00")
    assert records[0].principal_amount == Decimal("1250000.00")
    assert records[0].interest_rate == Decimal("11.5")
    assert records[0].past_due_30d_count == 0

    assert records[1].facility_type == "OVERDRAFT"
    assert records[1].outstanding_balance == Decimal("450000.00")
    assert records[1].past_due_30d_count == 15

    assert records[2].facility_type == "LEASING"
    assert records[2].outstanding_balance == Decimal("850000.00")


def test_opening_balance_exact_cases():
    """Validates exact dynamic opening balance cases from audit specification."""
    parser = BankStatementParser()
    acc_id = uuid4()
    biz_id = uuid4()

    # Case 1: Sold precedent: 14500.50 MDL
    s1 = (
        "# Header\n"
        "# Sold precedent: 14500.50 MDL\n"
        "date,amount,direction,description\n"
        "2025-01-01,100.00,INFLOW,Client wire\n"
    )
    res1 = parser.parse_csv(s1, acc_id, biz_id)
    assert res1.opening_balance == Decimal("14500.50")

    # Case 2: Входящий остаток: -3000.00
    s2 = (
        "# Header\n"
        "# Входящий остаток: -3000.00\n"
        "date,amount,direction,description\n"
        "2025-01-01,100.00,INFLOW,Client wire\n"
    )
    res2 = parser.parse_csv(s2, acc_id, biz_id)
    assert res2.opening_balance == Decimal("-3000.00")

    # Case 3: No opening balance -> Decimal('0.00')
    s3 = "date,amount,direction,description\n2025-01-01,100.00,INFLOW,Client wire\n"
    res3 = parser.parse_csv(s3, acc_id, biz_id)
    assert res3.opening_balance == Decimal("0.00")


def test_parsers_fail_fast_binary_and_pdf():
    """Validates fail-fast on binary garbage and textless PDF."""
    acc_id = uuid4()
    biz_id = uuid4()
    garbage = b"\x00\xff\xfe\x12\x34\x56\x78\x9a"

    with pytest.raises(ParsingError):
        BankStatementParser().parse_csv(garbage, acc_id, biz_id)
    with pytest.raises(ParsingError):
        InvoiceParser().parse_csv(garbage)
    with pytest.raises(ParsingError):
        CreditObligationParser().parse_csv(garbage)
    with pytest.raises(ParsingError):
        BankStatementParser().parse_pdf(b"%PDF-1.4 binary content without text layer", acc_id, biz_id)
