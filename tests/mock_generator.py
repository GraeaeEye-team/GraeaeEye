"""
Mock transaction and statement generators for test fixtures and unit tests.
Isolated under tests/ to maintain zero synthetic fallback invariant in production src/.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import List, Optional
from uuid import UUID, uuid4

from fintech_app.ingestion.ai_mapper import TransactionCategorizationMapper
from fintech_app.ingestion.schemas import (
    ParsedBankStatementPayload,
    RawBankStatementLine,
    StandardizedTransactionBatch,
)
from fintech_app.shared.schemas.user_types import TransactionDirection


def generate_mock_bank_statement_payload(
    business_id: Optional[UUID] = None,
    account_id: Optional[UUID] = None,
    count: int = 50,
) -> ParsedBankStatementPayload:
    """Генерирует синтетическую банковскую выписку для тестовых сценариев."""
    b_id = business_id or uuid4()
    a_id = account_id or uuid4()

    start_d = date.today() - timedelta(days=90)
    lines: List[RawBankStatementLine] = []

    descriptions = [
        ("Оплата за поставку стройматериалов по накладной 450", Decimal("45000.00"), TransactionDirection.OUTFLOW),
        ("Зачисление выручки от покупателей за услуги консалтинга", Decimal("120000.00"), TransactionDirection.INFLOW),
        ("Выплата заработной платы за прошлый месяц", Decimal("35000.00"), TransactionDirection.OUTFLOW),
        ("Уплата НДС и подоходного налога в бюджет", Decimal("18500.00"), TransactionDirection.OUTFLOW),
        ("Погашение процентов по кредитному договору № 12", Decimal("8200.00"), TransactionDirection.OUTFLOW),
        ("Оплата аренды офиса и серверных мощностей", Decimal("15000.00"), TransactionDirection.OUTFLOW),
        ("Поступление средств по договору поставки от ООО 'Альфа'", Decimal("85000.00"), TransactionDirection.INFLOW),
    ]

    for i in range(count):
        desc, amt, direction = descriptions[i % len(descriptions)]
        variance = Decimal(str((i % 7) * 150 + 25))
        actual_amt = (amt + variance).quantize(Decimal("0.01"))
        tx_d = start_d + timedelta(days=int(i * 1.8))

        lines.append(
            RawBankStatementLine(
                date=tx_d,
                amount=actual_amt,
                direction=direction,
                description=desc,
                counterparty_raw_name=f"Контрагент №{i % 8 + 1}",
                counterparty_tax_id=f"10026000000{i % 8 + 1}",
                account_number="MD24AG000000022518001001",
                currency="MDL",
            )
        )

    return ParsedBankStatementPayload(
        business_id=b_id,
        account_id=a_id,
        statement_period_start=start_d,
        statement_period_end=date.today(),
        opening_balance=Decimal("150000.00"),
        closing_balance=Decimal("280000.00"),
        currency="MDL",
        raw_lines=lines,
    )


def generate_mock_transaction_batch(
    business_id: Optional[UUID] = None,
    account_id: Optional[UUID] = None,
    count: int = 50,
) -> StandardizedTransactionBatch:
    """Генерирует готовый стандартизированный пакет транзакций для тестов."""
    payload = generate_mock_bank_statement_payload(business_id=business_id, account_id=account_id, count=count)
    mapper = TransactionCategorizationMapper()
    return mapper.standardize_payload(payload)

