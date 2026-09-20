"""
Pydantic-схемы валидации распарсенных данных (Data Ingestion Contracts).
Гарантируют строгую типизацию (Decimal, UUID, date) и чистоту входных данных
перед маппингом и сохранением в реляционный граф PostgreSQL через DAL.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

from fintech_app.shared.schemas.user_types import (
    LiquidityClass,
    TransactionCategory,
    TransactionDirection,
)


class RawBankStatementLine(BaseModel):
    """
    Сырая распарсенная строка выписки после извлечения из CSV / XLSX.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    date: date
    amount: Decimal
    direction: TransactionDirection
    description: str = Field(default="")
    counterparty_raw_name: Optional[str] = None
    counterparty_tax_id: Optional[str] = None
    account_number: str = Field(default="")
    currency: str = Field(default="MDL")

    @field_validator("amount", mode="before")
    @classmethod
    def parse_decimal_amount(cls, v: Any) -> Decimal:
        if isinstance(v, Decimal):
            return v.quantize(Decimal("0.01"))
        if v is None:
            raise ValueError("Amount cannot be null.")
        return Decimal(str(v)).quantize(Decimal("0.01"))


class ParsedBankStatementPayload(BaseModel):
    """
    Нормализованный пакет выписки одного банковского счета за расчетный период.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    account_id: UUID
    business_id: UUID
    opening_balance: Decimal
    closing_balance: Decimal
    period_start: date
    period_end: date
    lines: List[RawBankStatementLine] = Field(default_factory=list)

    @field_validator("opening_balance", "closing_balance", mode="before")
    @classmethod
    def coerce_balance_to_decimal(cls, v: Any) -> Decimal:
        if isinstance(v, Decimal):
            return v.quantize(Decimal("0.01"))
        if v is None:
            return Decimal("0.00")
        return Decimal(str(v)).quantize(Decimal("0.01"))


class ParsedJudicialRecord(BaseModel):
    """
    Структурированная судебная запись, полученная из внешних реестров.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    case_number: str
    filing_date: date
    role: str = Field(default="DEFENDANT", description="DEFENDANT, PLAINTIFF, THIRD_PARTY")
    claim_amount: Decimal = Field(default=Decimal("0.00"))
    case_status: str = Field(default="OPEN", description="OPEN, CLOSED, APPEALED")

    @field_validator("claim_amount", mode="before")
    @classmethod
    def coerce_claim_amount(cls, v: Any) -> Decimal:
        if isinstance(v, Decimal):
            return v.quantize(Decimal("0.01"))
        if v is None:
            return Decimal("0.00")
        return Decimal(str(v)).quantize(Decimal("0.01"))


class NormalizedTransactionRecord(BaseModel):
    """
    Каноническая запись транзакции для вставки в таблицу transactions PostgreSQL.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    transaction_id: UUID = Field(default_factory=uuid4)
    business_id: UUID
    account_id: UUID
    counterparty_id: Optional[UUID] = None
    invoice_id: Optional[UUID] = None
    counterparty_tax_id: Optional[str] = None
    counterparty_name: Optional[str] = None
    timestamp: datetime
    amount: Decimal
    direction: TransactionDirection
    category: TransactionCategory
    liquidity_class: LiquidityClass = LiquidityClass.IMMEDIATE_CASH
    description: str = Field(default="")

    @field_validator("amount", mode="before")
    @classmethod
    def enforce_positive_decimal(cls, v: Any) -> Decimal:
        dec = Decimal(str(v)) if not isinstance(v, Decimal) else v
        if dec <= Decimal("0.00"):
            raise ValueError("Transaction amount must be strictly positive.")
        return dec.quantize(Decimal("0.01"))


class StandardizedTransactionBatch(BaseModel):
    """
    Готовый пакет нормализованных транзакций с агрегированными суммами притока и оттока.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    business_id: UUID
    account_id: UUID
    transactions: List[NormalizedTransactionRecord] = Field(default_factory=list)
    total_count: int = 0
    total_inflow: Decimal = Field(default=Decimal("0.00"))
    total_outflow: Decimal = Field(default=Decimal("0.00"))

    def to_dict_records(self) -> List[Dict[str, Any]]:
        """Преобразует транзакции в список словарей для DAL cursor.copy()."""
        return [
            {
                "transaction_id": t.transaction_id,
                "business_id": t.business_id,
                "account_id": t.account_id,
                "counterparty_id": t.counterparty_id,
                "invoice_id": t.invoice_id,
                "timestamp": t.timestamp,
                "amount": t.amount,
                "direction": t.direction.value if hasattr(t.direction, "value") else str(t.direction),
                "category": t.category.value if hasattr(t.category, "value") else str(t.category),
                "liquidity_class": (
                    t.liquidity_class.value if hasattr(t.liquidity_class, "value") else str(t.liquidity_class)
                ),
            }
            for t in self.transactions
        ]


class IngestionResult(BaseModel):
    """
    Итоговый контракт возврата результатов работы IngestionPipeline.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    success: bool
    business_id: Optional[UUID] = None
    records_ingested: int = 0
    external_data_acquired: bool = False
    warnings: List[str] = Field(default_factory=list)
    error: Optional[str] = None
    message: str = ""


class NormalizedTransactionSchema(BaseModel):
    """Legacy compatibility schema for backward compatibility."""

    transaction_date: date
    amount: Decimal
    counterparty_inn: Optional[str] = None
    description: str = Field(default="")


class ParsedInvoiceRecord(BaseModel):
    """
    Распарсенная запись счета-фактуры (invoices).
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    invoice_id: UUID = Field(default_factory=uuid4)
    counterparty_name: str
    counterparty_role: Optional[str] = "CLIENT"
    invoice_type: str = "RECEIVABLE"
    gross_amount: Decimal
    issue_date: date
    due_date: date
    actual_payment_date: Optional[date] = None
    status: str = "OUTSTANDING"

    @field_validator("gross_amount", mode="before")
    @classmethod
    def coerce_amount(cls, v: Any) -> Decimal:
        if isinstance(v, Decimal):
            return abs(v).quantize(Decimal("0.01"))
        if v is None:
            raise ValueError("gross_amount cannot be None")
        return abs(Decimal(str(v))).quantize(Decimal("0.01"))


class ParsedCreditObligationRecord(BaseModel):
    """
    Распарсенная запись кредитного обязательства (credit_obligations).
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    obligation_id: UUID = Field(default_factory=uuid4)
    lender_name: str
    facility_type: str = "TERM_LOAN"
    principal_amount: Decimal
    outstanding_balance: Decimal
    monthly_payment: Decimal
    past_due_30d_count: int = 0
    past_due_90d_count: int = 0
    historical_defaults_count: int = 0

    @field_validator("principal_amount", "outstanding_balance", "monthly_payment", mode="before")
    @classmethod
    def coerce_amounts(cls, v: Any) -> Decimal:
        if isinstance(v, Decimal):
            return abs(v).quantize(Decimal("0.01"))
        if v is None:
            return Decimal("0.00")
        return abs(Decimal(str(v))).quantize(Decimal("0.01"))
