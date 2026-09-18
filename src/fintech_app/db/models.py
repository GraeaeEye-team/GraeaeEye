"""
Схема таблиц и связей реляционного графа данных (PostgreSQL).
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any, Dict, List, Optional, Union
from uuid import UUID, uuid4

# =====================================================================
# 0. ПЕРЕЧИСЛЕНИЯ (ENUMS) ДЛЯ ВАЛИДАЦИИ СТАТУСОВ И ТИПОВ ДАННЫХ
# =====================================================================

class CounterpartyRole(StrEnum):
    """Роли контрагента в торговом графе компании."""
    CLIENT = "CLIENT"          # Покупатель/дебитор
    SUPPLIER = "SUPPLIER"      # Поставщик/кредитор
    MIXED = "MIXED"            # Одновременно и покупатель, и поставщик


class InvoiceType(StrEnum):
    """Тип коммерческого счета-фактуры."""
    RECEIVABLE = "RECEIVABLE"  # Дебиторская задолженность (нам должны)
    PAYABLE = "PAYABLE"        # Кредиторская задолженность (мы должны)


class InvoiceStatus(StrEnum):
    """Жизненный цикл оплаты счета."""
    PAID = "PAID"              # Полностью оплачен
    OUTSTANDING = "OUTSTANDING"# Выставлен, срок оплаты еще не наступил
    OVERDUE = "OVERDUE"        # Просрочен по договору
    DEFAULTED = "DEFAULTED"    # Безнадежный долг / списание


class TransactionDirection(StrEnum):
    """Направление движения денежных средств."""
    INFLOW = "INFLOW"          # Поступление на счет
    OUTFLOW = "OUTFLOW"        # Списание со счета


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
    IMMEDIATE_CASH = "IMMEDIATE_CASH"          # Доступно прямо сейчас
    RESTRICTED_ESCROW = "RESTRICTED_ESCROW"    # Заблокировано на эскроу
    TERM_DEPOSIT = "TERM_DEPOSIT"              # Срочный депозит (нельзя снять мгновенно)


class FacilityType(StrEnum):
    """Тип долгового обязательства."""
    TERM_LOAN = "TERM_LOAN"                    # Классический кредит
    LEASING = "LEASING"                        # Финансовый лизинг оборудования/авто
    LINE_OF_CREDIT = "LINE_OF_CREDIT"          # Возобновляемая кредитная линия


class UserRole(StrEnum):
    """Роли пользователей в системе скоринга."""
    ADMIN = "ADMIN"
    UNDERWRITER = "UNDERWRITER"
    ANALYST = "ANALYST"


class AnalysisStatus(StrEnum):
    """Состояние конвейера скоринга."""
    QUEUED = "QUEUED"          # В очереди на запуск
    PARSING = "PARSING"        # Чтение и валидация входных файлов
    PROCESSING = "PROCESSING"  # Расчет подмодулей 4.1–4.9
    COMPLETED = "COMPLETED"    # Успешно завершен с полным отчетом
    FAILED = "FAILED"          # Ошибка выполнения пайплайна
    DEGRADED = "DEGRADED"      # Завершен с пропуском части подмодулей из-за нехватки данных


class LogSeverity(StrEnum):
    """Уровни логирования для консоли реального времени."""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARN = "WARN"
    ERROR = "ERROR"


# =====================================================================
# 1. ЕДИНЫЙ СЕРВИСНЫЙ КОНТРАКТ РЕЗУЛЬТАТА ОПЕРАЦИЙ БАЗЫ ДАННЫХ
# =====================================================================

@dataclass(frozen=True)
class DatabaseReport:
    """
    Универсальный контейнер возврата для ВСЕХ методов класса Database (DAL).
    
    Зачем нужен:
    1. Изолирует вызывающий код (FastAPI, подмодули анализа) от низкоуровневых
       деталей драйвера psycopg и сырых SQL-курсоров.
    2. Гарантирует предсказуемую обработку ошибок: при сбое транзакции success=False,
       а текст исключения пишется в error без аварийного падения сервиса.
    3. Позволяет вернуть как одну запись, так и массив словарей с количеством
       затронутых строк (affected_rows).
    """
    success: bool
    data: Optional[Union[List[Dict[str, Any]], Dict[str, Any]]] = None
    affected_rows: int = 0
    error: Optional[str] = None
    operation: Optional[str] = None
    table_name: Optional[str] = None


# =====================================================================
# 2. КЛАСТЕР 1: КОРПОРАТИВНОЕ УПРАВЛЕНИЕ И СТРУКТУРА СОБСТВЕННОСТИ
# =====================================================================

@dataclass
class BusinessRecord:
    """
    Профиль оцениваемой компании (таблица `businesses`).
    
    Зачем нужен:
    Базовый узел графа сущностей. К business_id привязываются все счета,
    транзакции и внешние метрики. Используется Подмодулем 4.1 (Ownership Structure)
    для расчета доли независимых директоров, а также Подмодулем 4.3 (Macro Risk)
    через код отрасли industry_code.
    """
    tax_id: str
    legal_name: str
    industry_code: str
    registration_date: date
    business_id: UUID = field(default_factory=uuid4)
    total_board_seats: int = 1
    independent_directors_count: int = 0


@dataclass
class ShareholderRecord:
    """
    Запись об акционере/учредителе (таблица `shareholders`).
    
    Зачем нужен:
    Хранит распределение долей капитала. Используется Подмодулем 4.1
    для вычисления индекса Херфиндаля-Хиршмана (HHI) концентрации капитала
    и оценки конфликта интересов (совмещение владения и руководства).
    """
    business_id: UUID
    shareholder_name: str
    equity_percentage: Decimal
    is_management_member: bool
    ownership_id: UUID = field(default_factory=uuid4)


# =====================================================================
# 3. КЛАСТЕР 2: ВНЕШНЯЯ РАЗВЕДКА И МАКРОЭКОНОМИКА
# =====================================================================

@dataclass
class WebReputationRecord:
    """
    Срез открытых данных и цифрового следа (таблица `web_reputation`).
    
    Зачем нужен:
    Пополняется асинхронными парсерами судебных реестров, санкционных баз
    и новостей. Используется Подмодулем 4.2 (Web Presence & Legal Reputation)
    для штрафования компании за открытые иски и негативный новостной фон.
    """
    business_id: UUID
    scan_timestamp: datetime
    record_id: UUID = field(default_factory=uuid4)
    active_lawsuits_count: int = 0
    total_lawsuit_claims_amount: Decimal = Decimal("0.00")
    is_in_sanctions_list: bool = False
    news_sentiment_score: Optional[Decimal] = None  # от -1.000 до +1.000
    web_traffic_monthly_visits: Optional[int] = None


@dataclass
class MacroSectorMetricRecord:
    """
    Отраслевые бенчмарки и макроэкономика (таблица `macro_sector_metrics`).
    
    Зачем нужен:
    Справочник макропоказателей отраслей (NACE/ОКВЭД). Используется
    Подмодулем 4.3 (Macro & Sector Risk) для отделения проблем самой компании
    от системного спада во всей отрасли.
    """
    industry_code: str
    reference_date: date
    sector_growth_rate_yoy: Decimal
    sector_default_rate: Decimal
    risk_outlook_score: int  # Шкала от 1 до 10
    metric_id: UUID = field(default_factory=uuid4)


# =====================================================================
# 4. КЛАСТЕР 3: КОММЕРЧЕСКИЙ ГРАФ, ЛИКВИДНОСТЬ И ДЕНЕЖНЫЙ ПОТОК
# =====================================================================

@dataclass
class CounterpartyRecord:
    """
    Справочник контрагентов компании (таблица `counterparties`).
    
    Зачем нужен:
    Строит вершины графа торговых отношений. Позволяет группировать выручку
    и расходы по конкретным покупателям и поставщикам для выявления монозависимости.
    """
    business_id: UUID
    legal_name: str
    counterparty_role: CounterpartyRole
    tax_id: Optional[str] = None
    counterparty_id: UUID = field(default_factory=uuid4)


@dataclass
class InvoiceRecord:
    """
    Счета-фактуры дебиторов и кредиторов (таблица `invoices`).
    
    Зачем нужен:
    Критический источник данных для трех задач:
    1. Подмодуль 4.4 (Client Dependency) — концентрация выручки по покупателям.
    2. Подмодуль 4.6 (Immediate Cash Readiness) — объем обязательств к выплате в 30 дней.
    3. Подмодуль 4.8 (Receivables Quality) — дельта между due_date и actual_payment_date
       для поведенческого скоринга задержек клиентов (payment slippage).
    """
    business_id: UUID
    counterparty_id: UUID
    invoice_type: InvoiceType
    gross_amount: Decimal
    issue_date: date
    due_date: date
    status: InvoiceStatus
    actual_payment_date: Optional[date] = None
    invoice_id: UUID = field(default_factory=uuid4)


@dataclass
class BankAccountRecord:
    """
    Банковские счета компании (таблица `bank_accounts`).
    
    Зачем нужен:
    Отображает остатки «живых» денег и лимиты овердрафта.
    Используется Подмодулем 4.6 для расчета коэффициента абсолютной ликвидности (Cash Ratio)
    и запаса операционных дней (Days Cash on Hand).
    """
    business_id: UUID
    currency: str
    current_balance: Decimal
    account_id: UUID = field(default_factory=uuid4)
    overdraft_limit: Decimal = Decimal("0.00")


@dataclass
class TransactionRecord:
    """
    Банковские проводки и выписки (таблица `transactions`).
    
    Зачем нужен:
    1. Подмодуль 4.7 (Cash Flow Stability) — анализ волатильности помесячной выручки.
    2. Подмодуль 4.5 (Supplier Dependency) — группировка расходов на поставщиков.
    3. Подмодуль 4.6 (Immediate Cash Readiness) — расчет средней зарплаты и налогов за 3 мес.
    """
    business_id: UUID
    account_id: UUID
    timestamp: datetime
    amount: Decimal
    direction: TransactionDirection
    category: TransactionCategory
    liquidity_class: LiquidityClass
    counterparty_id: Optional[UUID] = None
    invoice_id: Optional[UUID] = None
    transaction_id: UUID = field(default_factory=uuid4)


# =====================================================================
# 5. КЛАСТЕР 4: КРЕДИТНАЯ ИСТОРИЯ И ДОЛГОВАЯ НАГРУЗКА
# =====================================================================

@dataclass
class CreditObligationRecord:
    """
    Действующие и закрытые кредитные линии (таблица `credit_obligations`).
    
    Зачем нужен:
    Используется Подмодулем 4.9 (Internal Credit Discipline & Leverage) для расчета
    платежной дисциплины (штрафы за просрочки 30/90 дней), коэффициента покрытия
    долга (DSCR) и левериджа (Debt-to-Cash Flow).
    """
    business_id: UUID
    lender_name: str
    facility_type: FacilityType
    principal_amount: Decimal
    outstanding_balance: Decimal
    monthly_payment: Decimal
    obligation_id: UUID = field(default_factory=uuid4)
    past_due_30d_count: int = 0
    past_due_90d_count: int = 0
    historical_defaults_count: int = 0


# =====================================================================
# 6. КЛАСТЕР 5: ПОЛЬЗОВАТЕЛИ, СЕССИИ И ОРКЕСТРАЦИЯ АНАЛИЗА
# =====================================================================

@dataclass
class UserRecord:
    """
    Учетная запись андеррайтера или аналитика (таблица `users`).
    
    Зачем нужен:
    Обеспечивает аутентификацию в веб-интерфейсе, хранит хеш пароля (Argon2/bcrypt)
    и определяет права доступа через поле role.
    """
    email: str
    password_hash: str
    full_name: str
    user_id: UUID = field(default_factory=uuid4)
    role: UserRole = UserRole.ANALYST
    is_active: bool = True
    created_at: Optional[datetime] = None


@dataclass
class UserSettingsRecord:
    """
    Персональные настройки рабочего пространства (таблица `user_settings`).
    
    Зачем нужен:
    Хранит состояние интерфейса пользователя между сессиями (тема оформления,
    поведение консоли логов, авто-раскрытие карточек отчетов).
    """
    user_id: UUID
    setting_id: UUID = field(default_factory=uuid4)
    ui_theme: str = "system"
    terminal_sound_effects: bool = False
    auto_expand_reports: bool = True


@dataclass
class AnalysisRunRecord:
    """
    Жизненный цикл сессии скоринга компании (таблица `analysis_runs`).
    
    Зачем нужен:
    Главный агрегатор результатов оценки:
    1. Связывает загруженные файлы пользователя с созданной сущностью businesses.
    2. Фиксирует статус выполнения пайплайна для отображения на фронтенде.
    3. Хранит вектор из 18 индексов (raw_indices_payload), сухие отчеты подмодулей
       и финальный синтез от LLM с общим баллом (universal_score).
    """
    user_id: UUID
    input_company_name: str
    input_tax_id: str
    input_industry_code: str
    files_manifest: Dict[str, Any]
    active_submodules: List[str]
    run_id: UUID = field(default_factory=uuid4)
    business_id: Optional[UUID] = None
    status: AnalysisStatus = AnalysisStatus.QUEUED
    raw_indices_payload: Optional[Dict[str, Optional[float]]] = None
    submodules_reports: Optional[List[Dict[str, Any]]] = None
    llm_final_summary: Optional[str] = None
    universal_score: Optional[Decimal] = None
    failure_reason: Optional[str] = None
    created_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


@dataclass
class AnalysisLogRecord:
    """
    Телеметрия и логи этапов пайплайна (таблица `analysis_logs`).
    
    Зачем нужен:
    Каждое событие работы подмодулей или парсинга пишется в эту структуру
    и транслируется через Server-Sent Events (SSE) в терминал веб-интерфейса,
    позволяя аналитику видеть ход выполнения в реальном времени.
    """
    run_id: UUID
    severity: LogSeverity
    stage: str
    message: str
    timestamp: Optional[datetime] = None

