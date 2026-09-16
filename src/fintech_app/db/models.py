"""
Схема таблиц и связей реляционного графа данных (PostgreSQL).
Определяет структуру сущностей: Компании, Контрагенты, Контракты, Счета (Invoices), Транзакции.
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class CompanyModel:
    id: int
    name: str
    inn: str


@dataclass
class CounterpartyModel:
    id: int
    company_id: int
    name: str
    inn: str


@dataclass
class ContractModel:
    id: int
    company_id: int
    counterparty_id: int
    contract_number: str
    payment_terms_days: int


@dataclass
class InvoiceModel:
    id: int
    contract_id: int
    amount: float
    issue_date: datetime
    due_date: datetime
    is_paid: bool


@dataclass
class TransactionModel:
    id: int
    invoice_id: Optional[int]
    amount: float
    transaction_date: datetime
    description: str

