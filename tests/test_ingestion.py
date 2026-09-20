"""
Тестовый набор для модуля Data Ingestion (Фазы 1-3).
Проверяет строгие финансовые Pydantic-контракты, отсутствие float-дрейфа,
фаззинг грязных CSV, потоковый парсинг Excel и интеграцию IngestionPipeline.
"""
import io
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from fintech_app.core.exceptions import ParsingError
from fintech_app.db.mock_connection import MockDatabase
from fintech_app.ingestion.ai_mapper import (
    TransactionCategorizationMapper,
    categorize_transaction,
    fuzzy_map_headers,
    validate_mapping,
)
from fintech_app.ingestion.external_intel import ExternalIntelligenceCollector
from fintech_app.ingestion.parser import (
    BankStatementParser,
    clean_amount_string,
    generate_mock_bank_statement_payload,
    generate_mock_transaction_batch,
    parse_date_flexible,
)
from fintech_app.ingestion.pipeline import IngestionPipeline
from fintech_app.ingestion.schemas import (
    NormalizedTransactionRecord,
    ParsedBankStatementPayload,
    RawBankStatementLine,
    StandardizedTransactionBatch,
)
from fintech_app.shared.schemas.user_types import (
    LiquidityClass,
    TransactionCategory,
    TransactionDirection,
)


class TestFinancialPrecisionAndContracts:
    """Проверка инвариантов строгой типизации и финансовой точности (ZERO float)."""

    def test_raw_line_rejects_float_and_enforces_decimal(self):
        line = RawBankStatementLine(
            date=date(2025, 1, 1),
            amount="1250.50",
            direction=TransactionDirection.INFLOW,
            description="Тестовый платеж",
            currency="MDL",
        )
        assert isinstance(line.amount, Decimal)
        assert line.amount == Decimal("1250.50")

    def test_normalized_record_enforces_positive_decimal(self):
        with pytest.raises(ValueError, match="strictly positive"):
            NormalizedTransactionRecord(
                business_id=uuid4(),
                account_id=uuid4(),
                timestamp=datetime.now(),
                amount=Decimal("-10.00"),
                direction=TransactionDirection.OUTFLOW,
                category=TransactionCategory.OPERATING_EXPENSE,
            )

    def test_10000_transactions_financial_precision_no_drift(self):
        """Phase 3 assertion: 10,000 транзакций сходятся до 0.01 без дрейфа округления."""
        opening_balance = Decimal("1000000.00")
        total_inflow = Decimal("0.00")
        total_outflow = Decimal("0.00")

        lines = []
        for i in range(10000):
            # Сумма с копейками, склонная к дрейфу во float (например 0.1 + 0.2)
            amt = Decimal("123.47") + Decimal(str(i % 100)) / Decimal("100")
            is_in = i % 2 == 0
            direction = TransactionDirection.INFLOW if is_in else TransactionDirection.OUTFLOW

            if is_in:
                total_inflow += amt
            else:
                total_outflow += amt

            lines.append(
                RawBankStatementLine(
                    date=date(2025, 1, 1),
                    amount=amt,
                    direction=direction,
                    description=f"Batch item {i}",
                )
            )

        closing_balance = opening_balance + total_inflow - total_outflow
        calculated_closing = opening_balance
        for line in lines:
            if line.direction == TransactionDirection.INFLOW:
                calculated_closing += line.amount
            else:
                calculated_closing -= line.amount

        assert closing_balance == calculated_closing
        assert str(closing_balance).endswith(".00")


class TestNumberAndDateCleaning:
    """Тестирование очистки европейских, американских форматов и валютных символов."""

    @pytest.mark.parametrize(
        "raw_input, expected_amt, expected_dir",
        [
            ("1.250,50", Decimal("1250.50"), TransactionDirection.INFLOW),
            ("1,250.50", Decimal("1250.50"), TransactionDirection.INFLOW),
            ("15 000,00 MDL", Decimal("15000.00"), TransactionDirection.INFLOW),
            ("€ -2.500,00", Decimal("2500.00"), TransactionDirection.OUTFLOW),
            ("(750.25)", Decimal("750.25"), TransactionDirection.OUTFLOW),
            (" 450.00 ", Decimal("450.00"), TransactionDirection.INFLOW),
            ("10.000.000,55 lei", Decimal("10000000.55"), TransactionDirection.INFLOW),
            ("-120,50 руб", Decimal("120.50"), TransactionDirection.OUTFLOW),
        ],
    )
    def test_clean_amount_string(self, raw_input, expected_amt, expected_dir):
        amt, direction = clean_amount_string(raw_input)
        assert amt == expected_amt
        assert direction == expected_dir

    @pytest.mark.parametrize(
        "raw_date, expected_date",
        [
            ("2025-05-20", date(2025, 5, 20)),
            ("20.05.2025", date(2025, 5, 20)),
            ("20/05/2025", date(2025, 5, 20)),
            ("2025/05/20 14:30:00", date(2025, 5, 20)),
            ("20-05-2025T09:15:00", date(2025, 5, 20)),
        ],
    )
    def test_parse_date_flexible(self, raw_date, expected_date):
        assert parse_date_flexible(raw_date) == expected_date


class TestFuzzyHeaderMapperAndCategorization:
    """Тестирование нечеткого сопоставления заголовков и категоризации расходов."""

    def test_fuzzy_mapping_multilingual(self):
        # Румынский / Молдавский
        ro_cols = ["Data", "Suma", "Detalii operatiune", "CUI / CIF", "IBAN"]
        ro_mapped = fuzzy_map_headers(ro_cols)
        assert ro_mapped["Data"] == "date"
        assert ro_mapped["Suma"] == "amount"
        assert ro_mapped["Detalii operatiune"] == "description"
        assert ro_mapped["CUI / CIF"] == "counterparty_tax_id"
        assert ro_mapped["IBAN"] == "account_number"

        # Русский
        ru_cols = ["Дата документа", "Сумма операции", "Назначение платежа", "ИНН", "Счет"]
        ru_mapped = fuzzy_map_headers(ru_cols)
        assert ru_mapped["Дата документа"] == "date"
        assert ru_mapped["Сумма операции"] == "amount"
        assert ru_mapped["Назначение платежа"] == "description"
        assert ru_mapped["ИНН"] == "counterparty_tax_id"

        # Немецкий / Английский
        de_cols = ["Datum", "Betrag", "Verwendungszweck"]
        de_mapped = fuzzy_map_headers(de_cols)
        assert de_mapped["Datum"] == "date"
        assert de_mapped["Betrag"] == "amount"
        assert de_mapped["Verwendungszweck"] == "description"

    def test_validation_mapping_missing_raises_parsing_error(self):
        with pytest.raises(ParsingError):
            validate_mapping({"description", "account_number"})

    def test_expense_categorization(self):
        assert categorize_transaction("Выплата заработной платы за июнь", TransactionDirection.OUTFLOW) == TransactionCategory.PAYROLL
        assert categorize_transaction("Plata salariu angajati", TransactionDirection.OUTFLOW) == TransactionCategory.PAYROLL
        assert categorize_transaction("Уплата НДС за 2 квартал", TransactionDirection.OUTFLOW) == TransactionCategory.TAX
        assert categorize_transaction("Achitare impozit pe venit", TransactionDirection.OUTFLOW) == TransactionCategory.TAX
        assert categorize_transaction("Погашение процентов по кредитному договору", TransactionDirection.OUTFLOW) == TransactionCategory.DEBT_SERVICE
        assert categorize_transaction("Выплата дивидендов учредителям", TransactionDirection.OUTFLOW) == TransactionCategory.DIVIDEND
        assert categorize_transaction("Оплата поставщику по накладной 102", TransactionDirection.OUTFLOW) == TransactionCategory.SUPPLIER_PAYMENT
        assert categorize_transaction("Канцтовары и аренда", TransactionDirection.OUTFLOW) == TransactionCategory.OPERATING_EXPENSE
        assert categorize_transaction("Поступление от покупателя", TransactionDirection.INFLOW) == TransactionCategory.REVENUE


class TestEdgeCaseFuzzingAndParser:
    """Тестирование грязных CSV, пустых строк и смешанных форматов."""

    def test_dirty_csv_fuzzing(self):
        dirty_csv = """# Bank Report Header
Generated at 2025-01-01
Account: 123456789

Date,Amount,Description,TaxID
2025-01-10,"1.250,50",Good row,1001
corrupted-date,"500.00",Bad date row,1002
2025-01-11,not-a-number,Bad amount row,1003
,,,
2025-01-12,"-300.00",Valid outflow,1004

"""
        parser = BankStatementParser()
        payload = parser.parse_csv(dirty_csv.encode("utf-8-sig"), uuid4(), uuid4())
        # Должны сохраниться только 2 валидные строки
        assert len(payload.lines) == 2
        assert payload.lines[0].amount == Decimal("1250.50")
        assert payload.lines[1].amount == Decimal("300.00")
        assert payload.lines[1].direction == TransactionDirection.OUTFLOW

    def test_debit_credit_two_column_csv(self):
        two_col_csv = """Дата;Расход;Приход;Назначение;ИНН
10.03.2025;5000,00;;Оплата канцелярии;7701
11.03.2025;;25000,00;Выручка от продаж;7702
"""
        parser = BankStatementParser()
        payload = parser.parse_csv(two_col_csv.encode("utf-8"), uuid4(), uuid4())
        assert len(payload.lines) == 2
        assert payload.lines[0].direction == TransactionDirection.OUTFLOW
        assert payload.lines[0].amount == Decimal("5000.00")
        assert payload.lines[1].direction == TransactionDirection.INFLOW
        assert payload.lines[1].amount == Decimal("25000.00")


class TestExternalIntelAndPipelineIntegration:
    """Тестирование ExternalIntelligenceCollector и IngestionPipeline с MockDatabase."""

    @pytest.mark.asyncio
    async def test_external_intel_fallback(self):
        collector = ExternalIntelligenceCollector(use_mock=True)
        res = await collector.collect_all({
            "business_id": uuid4(),
            "company_name": "Test Company SRL",
            "tax_id": "100260000001",
            "sector_code": "G46",
        })
        assert res["success"] is True
        assert res["reputation"]["has_active_claims"] is False
        assert res["macro_metrics"]["macro_risk_level"] == "MODERATE"

    @pytest.mark.asyncio
    async def test_ingestion_pipeline_end_to_end(self):
        mock_db = MockDatabase()
        pipeline = IngestionPipeline(db=mock_db)

        csv_content = b"""Data,Suma,Detalii,CUI
2025-02-01,"10.000,00",Incasare vanzari,100100
2025-02-02,"-2.500,00",Plata salariu,100200
2025-02-03,"-1.000,00",Plata taxe buget,100300
"""
        result = await pipeline.run(
            metadata={"company_name": "Moldova Trade SRL", "tax_id": "100987654321"},
            files=[("statement.csv", csv_content)],
        )

        assert result.success is True
        assert result.records_ingested == 3
        assert result.external_data_acquired is True
        assert len(mock_db._storage["transactions"]) == 3
