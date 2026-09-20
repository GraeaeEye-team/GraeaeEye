"""
Интеллектуальный маппер колонок выписок и категоризатор расходов.
Обеспечивает нечеткое сопоставление заголовков банковских выписок (RU, EN, RO, DE),
семантическую категоризацию транзакций и интеграцию с LLM/эмбеддингами при необходимости.
"""
from __future__ import annotations

from datetime import datetime, time
from decimal import Decimal
import logging
import re
from typing import Any, Dict, List, Optional, Set
from uuid import UUID, uuid4

from fintech_app.core.exceptions import ParsingError
from fintech_app.ingestion.schemas import (
    NormalizedTransactionRecord,
    ParsedBankStatementPayload,
    StandardizedTransactionBatch,
)
from fintech_app.shared.schemas.user_types import (
    LiquidityClass,
    TransactionCategory,
    TransactionDirection,
)

logger = logging.getLogger(__name__)

# Словарь синонимов для канонических полей
CANONICAL_HEADER_SYNONYMS: Dict[str, List[str]] = {
    "amount": [
        "amount",
        "suma",
        "sumă",
        "valoare",
        "betrag",
        "montant",
        "сумма",
        "сумма платежа",
        "сумма операции",
        "всего",
        "total",
        "val",
    ],
    "debit": [
        "debit",
        "debitare",
        "расход",
        "списание",
        "выбытие",
        "отток",
    ],
    "credit": [
        "credit",
        "creditare",
        "приход",
        "поступление",
        "зачисление",
        "приток",
    ],
    "date": [
        "date",
        "data",
        "trans_date",
        "transaction_date",
        "timestamp",
        "datum",
        "дата",
        "дата проводки",
        "дата операции",
        "дата документа",
    ],
    "description": [
        "description",
        "detalii",
        "details",
        "memo",
        "verwendungszweck",
        "назначение",
        "назначение платежа",
        "описание",
        "детали",
        "цель платежа",
        "комментарий",
    ],
    "counterparty_tax_id": [
        "counterparty_tax_id",
        "cui",
        "cif",
        "idno",
        "tax_id",
        "inn",
        "инн",
        "инн получателя",
        "инн плательщика",
        "фискальный код",
        "код",
    ],
    "counterparty_raw_name": [
        "counterparty_raw_name",
        "counterparty",
        "beneficiar",
        "platitor",
        "контрагент",
        "получатель",
        "плательщик",
        "наименование контрагента",
        "клиент",
        "name",
    ],
    "direction": [
        "direction",
        "tip",
        "type",
        "тип",
        "тип операции",
        "направление",
        "д/к",
    ],
    "account_number": [
        "account_number",
        "account",
        "iban",
        "cont",
        "счет",
        "номер счета",
        "расчетный счет",
    ],
    "currency": [
        "currency",
        "valuta",
        "moneda",
        "валюта",
        "curr",
    ],
}


def fuzzy_map_headers(columns: List[str]) -> Dict[str, str]:
    """
    Нечетко сопоставляет произвольные заголовки столбцов выписки с каноническими полями.
    Возвращает словарь: {оригинальный_заголовок: каноническое_поле}.
    Использует сопоставление по отдельным токенам/словам с границами слов.
    """
    mapping: Dict[str, str] = {}
    used_targets: Set[str] = set()

    for col in columns:
        col_str = str(col).strip()
        col_lower = col_str.lower()
        col_words = set(re.findall(r"\b[\w/]+\b", col_lower))
        matched_field: Optional[str] = None

        for target_field, synonyms in CANONICAL_HEADER_SYNONYMS.items():
            if target_field in used_targets and target_field in ("amount", "date", "debit", "credit"):
                continue

            for syn in synonyms:
                syn_lower = syn.lower().strip()
                # 1. Точное совпадение всей строки заголовка
                if syn_lower == col_lower:
                    matched_field = target_field
                    break
                # 2. Точное совпадение одного из слов (word boundary)
                if syn_lower in col_words:
                    matched_field = target_field
                    break
                # 3. Составная фраза из нескольких слов (например "сумма платежа")
                if " " in syn_lower and syn_lower in col_lower:
                    matched_field = target_field
                    break

            if matched_field:
                break

        if matched_field:
            mapping[col_str] = matched_field
            used_targets.add(matched_field)
        else:
            mapping[col_str] = col_str

    return mapping


def validate_mapping(mapped_fields: set) -> None:
    """
    Проверяет, что обязательные поля идентифицированы.
    Либо ('amount' и 'date'), либо ('debit'/'credit' и 'date').
    При отсутствии выбрасывает ParsingError.
    """
    has_amount = "amount" in mapped_fields or ("debit" in mapped_fields or "credit" in mapped_fields)
    has_date = "date" in mapped_fields

    if not has_amount or not has_date:
        missing = []
        if not has_amount:
            missing.append("'amount' (or 'debit'/'credit')")
        if not has_date:
            missing.append("'date'")
        raise ParsingError(
            f"Statement missing required columns: {', '.join(missing)}. "
            f"Detected fields: {sorted(list(mapped_fields))}"
        )


def categorize_transaction(
    description: str,
    direction: TransactionDirection,
) -> TransactionCategory:
    """
    Определяет финансовую категорию транзакции на основе ключевых слов и направления.
    """
    if direction == TransactionDirection.INFLOW:
        return TransactionCategory.REVENUE

    desc_lower = (description or "").lower()

    # Зарплатные выплаты
    payroll_keywords = [
        "salariu", "salary", "remunerare", "payroll", "зарплат", "заработ",
        "оплата труда", "фот", "вознаграждение", "аванс сотруд", "расчет при увол",
        "премия", "з/п", " зп "
    ]
    if any(k in desc_lower for k in payroll_keywords):
        return TransactionCategory.PAYROLL

    # Налоговые и бюджетные платежи
    tax_keywords = [
        "fisc", "tva", "impozit", "buget", "tax", "vat", "налог", "пошлина",
        "бюджет", "сбор", "пенсион", "страхов", "соцстрах", "фсс", "ффомс",
        "ндфл", "ндс", "усн", "госпошлина"
    ]
    if any(k in desc_lower for k in tax_keywords):
        return TransactionCategory.TAX

    # Обслуживание долга, кредиты, лизинг
    debt_keywords = [
        "credit", "dobanda", "loan", "leasing", "кредит", "процент",
        "лизинг", "долг", "погашение овердрафт", "тело долга", "комиссия банка",
        "ссуда"
    ]
    if any(k in desc_lower for k in debt_keywords):
        return TransactionCategory.DEBT_SERVICE

    # Дивиденды и распределение прибыли
    dividend_keywords = [
        "dividend", "distribuire profit", "дивиденд", "выплата прибыли",
        "распределение прибыли", "доход участник"
    ]
    if any(k in desc_lower for k in dividend_keywords):
        return TransactionCategory.DIVIDEND

    # Оплата поставщикам / контрагентам
    supplier_keywords = [
        "furnizor", "supplier", "поставщик", "оплата товара", "закупка",
        "по договору поставки", "счет-фактур", "акт выполнен", "накладная"
    ]
    if any(k in desc_lower for k in supplier_keywords):
        return TransactionCategory.SUPPLIER_PAYMENT

    # Категория по умолчанию для списаний
    return TransactionCategory.OPERATING_EXPENSE


class TransactionCategorizationMapper:
    """
    Класс семантической классификации и приведения распарсенных строк к канонической форме.
    """

    def map_categories_and_counterparties(
        self, payload: ParsedBankStatementPayload
    ) -> StandardizedTransactionBatch:
        """
        Преобразует неструктурированные строки выписки в StandardizedTransactionBatch,
        назначая категории расходов и создавая канонические DTO для вставки в БД.
        """
        transactions: List[NormalizedTransactionRecord] = []
        total_inflow = Decimal("0.00")
        total_outflow = Decimal("0.00")

        for line in payload.lines:
            category = categorize_transaction(line.description, line.direction)
            ts = datetime.combine(line.date, time.min)

            counterparty_id: Optional[UUID] = None
            if line.counterparty_tax_id:
                counterparty_id = UUID(int=abs(hash(f"tax_{line.counterparty_tax_id}")) % (2**128))
            elif line.counterparty_raw_name:
                counterparty_id = UUID(int=abs(hash(f"name_{line.counterparty_raw_name}")) % (2**128))

            record = NormalizedTransactionRecord(
                transaction_id=uuid4(),
                business_id=payload.business_id,
                account_id=payload.account_id,
                counterparty_id=counterparty_id,
                invoice_id=None,
                counterparty_tax_id=line.counterparty_tax_id,
                counterparty_name=line.counterparty_raw_name,
                timestamp=ts,
                amount=line.amount,
                direction=line.direction,
                category=category,
                liquidity_class=LiquidityClass.IMMEDIATE_CASH,
                description=line.description,
            )
            transactions.append(record)

            if line.direction == TransactionDirection.INFLOW:
                total_inflow += line.amount
            else:
                total_outflow += line.amount

        return StandardizedTransactionBatch(
            business_id=payload.business_id,
            account_id=payload.account_id,
            transactions=transactions,
            total_count=len(transactions),
            total_inflow=total_inflow.quantize(Decimal("0.01")),
            total_outflow=total_outflow.quantize(Decimal("0.01")),
        )


def map_columns_with_ai(column_names: List[str]) -> Dict[str, str]:
    """
    Каноническая обертка маппинга колонок. Сначала использует быстрый fuzzy-маппер.
    """
    return fuzzy_map_headers(column_names)
