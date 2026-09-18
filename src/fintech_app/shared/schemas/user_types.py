"""
Пользовательские типы данных и доменные перечисления (Enums).
Использует StrEnum из стандартной библиотеки Python 3.12.
"""
from enum import StrEnum


class EvaluationStatus(StrEnum):
    """Статус исполнения расчета подмодуля."""
    SUCCESS = "SUCCESS"
    DATA_ABSENT = "DATA_ABSENT"
    ERROR = "ERROR"


class CounterpartyRole(StrEnum):
    """Роли контрагента в торговом графе компании."""
    CLIENT = "CLIENT"
    SUPPLIER = "SUPPLIER"
    MIXED = "MIXED"


class InvoiceType(StrEnum):
    """Тип коммерческого счета-фактуры."""
    RECEIVABLE = "RECEIVABLE"
    PAYABLE = "PAYABLE"


class InvoiceStatus(StrEnum):
    """Жизненный цикл оплаты счета."""
    PAID = "PAID"
    OUTSTANDING = "OUTSTANDING"
    OVERDUE = "OVERDUE"
    DEFAULTED = "DEFAULTED"


class TransactionDirection(StrEnum):
    """Направление движения денежных средств."""
    INFLOW = "INFLOW"
    OUTFLOW = "OUTFLOW"


class TransactionCategory(StrEnum):
    """Категория транзакции для анализа операционных расходов и денежного потока."""
    REVENUE = "REVENUE"
    OPERATING_EXPENSE = "OPERATING_EXPENSE"
    PAYROLL = "PAYROLL"
    TAX = "TAX"
    DEBT_SERVICE = "DEBT_SERVICE"
    DIVIDEND = "DIVIDEND"
    OTHER = "OTHER"


class LiquidityClass(StrEnum):
    """Класс ликвидности актива для расчета моментальной платежеспособности."""
    IMMEDIATE_CASH = "IMMEDIATE_CASH"
    RESTRICTED_ESCROW = "RESTRICTED_ESCROW"
    TERM_DEPOSIT = "TERM_DEPOSIT"


class FacilityType(StrEnum):
    """Тип долгового обязательства."""
    TERM_LOAN = "TERM_LOAN"
    LEASING = "LEASING"
    LINE_OF_CREDIT = "LINE_OF_CREDIT"


class AnalysisStatus(StrEnum):
    """Состояние конвейера скоринга."""
    QUEUED = "QUEUED"
    PARSING = "PARSING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    DEGRADED = "DEGRADED"
