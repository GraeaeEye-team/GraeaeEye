================================================================================
SMART CREDIT SYSTEM: ASYNCHRONOUS DATABASE & PERSISTENCE LAYER
TECHNICAL ARCHITECTURE & SPECIFICATION DOCUMENT (V2.0)
================================================================================

1. SYSTEM CONCEPT & EXECUTIVE OVERVIEW
--------------------------------------------------------------------------------
1.1 Mission and Role
The Database Module serves as the centralized persistence, state management, and
relational data access engine for the Smart Credit platform. It mediates all read,
write, and analytical query operations demanded by the 9 autonomous underwriting
submodules, background data ingestion routines, and the FastAPI presentation layer.

1.2 Architectural Philosophy
* Non-Blocking Asynchrony: Built natively for Python AsyncIO leveraging psycopg (v3)
  and psycopg_pool.AsyncConnectionPool to guarantee high-throughput, non-blocking
  I/O during concurrent API requests and telemetry log streaming.
* Strict Parameterization & Injection Immunity: Absolute prohibition of dynamic string
  interpolation (f-strings) in query execution. Structural schema identifiers and
  dynamic filters are securely assembled via psycopg.sql.SQL, while data literals
  are bound exclusively via parameterized positional or named placeholders.
* Deterministic Result Contracts: All database interactions return a strongly typed,
  standardized DatabaseReport container, eliminating raw cursor leakages and providing
  uniform error encapsulation, row impact telemetry, and dictionary-mapped records.
* Entity Graph Integrity: Maintains relational constraints across core business profiles,
  B2B commercial counterparty interactions, historical facilities, and web snapshots.
* Strict 13-Table Partitioning: Enforces exactly 13 canonical tables across 5 clusters,
  with analysis_runs serving as the single immutable audit ledger for pipeline runs.


2. HIGH-LEVEL ARCHITECTURE & CONNECTION SUBSYSTEM
--------------------------------------------------------------------------------
2.1 Connection Pool Architecture
The module encapsulates connection lifecycle management within a singleton or shared
Database class in connection.py. It utilizes psycopg_pool.AsyncConnectionPool with
client-side dictionary row mapping (row_factory=dict_row).

+------------------------------------------------------------------------------+
|                   FastAPI / Engine Workers / Other Modules                   |
+------------------------------------------------------------------------------+
                                       |
                                       v
+------------------------------------------------------------------------------+
|                     Database Class (connection.py)                           |
|  - pool: AsyncConnectionPool                                                 |
|  - row_factory: dict_row                                                     |
|  - open() / close() / health_check()                                         |
+------------------------------------------------------------------------------+
                                       |
        +------------------------------+------------------------------+
        |                              |                              |
        v                              v                              v
+---------------+              +---------------+              +---------------+
| Connection 1  |              | Connection 2  |              | Connection N  |
| (dict_row)    |              | (dict_row)    |              | (dict_row)    |
+---------------+              +---------------+              +---------------+
                                       |
                                       v
+------------------------------------------------------------------------------+
|                         PostgreSQL 15+ Relational DB                         |
+------------------------------------------------------------------------------+

2.2 Connection Lifecycle & Settings
* Pool Sizing: Minimum pool size (min_size=4), Maximum pool size (max_size=20),
  maximum idle lifetime (max_idle=300.0 seconds).
* Health Check: Validates connection vitality via SELECT 1 on checkout or ping.
* Context-Managed Transactions: Every operation is guarded by asynchronous context
  managers:
  `async with self.pool.connection() as conn: async with conn.transaction():`
  guaranteeing atomic rollbacks on exceptions and automated commits on success.


3. UNIFIED DATA CONTRACT: DatabaseReport
--------------------------------------------------------------------------------
All operations (insert, select, update, delete, bulk) return an immutable DatabaseReport
instance to decouple application logic from database driver internals.

```python
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Union

@dataclass(frozen=True)
class DatabaseReport:
    """
    Standardized result contract for all Database operations.
    """
    success: bool
    data: Optional[Union[List[Dict[str, Any]], Dict[str, Any]]] = None
    affected_rows: int = 0
    error: Optional[str] = None
    operation: Optional[str] = None
    table_name: Optional[str] = None
```

3.1 Operational Semantics
* Retrieval Operations (get_*): If matching records are found, success=True,
  data contains a list of dicts (or a single dict if find_only_first=True),
  and affected_rows equals the count of records retrieved. If zero matches occur,
  success=True, data=[] (or None), and affected_rows=0.
* Mutation Operations (add_*, update_*, delete_*): affected_rows reflects
  rows inserted, updated, or removed. data contains returned records via RETURNING *
  when requested.
* Bulk Streaming (bulk_insert_*): affected_rows reflects rows streamed via cursor.copy().
* Exceptional States: On database exceptions (psycopg.Error, network drop, constraint
  violation), the transaction is rolled back, returning success=False, data=None,
  affected_rows=0, and error populated with the sanitized driver message.


4. COMPREHENSIVE RELATIONAL SCHEMA CATALOG (13 TABLES ACROSS 5 CLUSTERS)
--------------------------------------------------------------------------------
The relational schema comprises strictly 13 tables partitioned into 5 functional clusters.
The analysis_runs table acts as the sole historical audit ledger; no 14th table exists.

4.1 Cluster 1: Core Corporate Identity & Governance
* Table: businesses
  Represents foundational corporate identity, incorporation status, and governance.
  - business_id (UUID, PK): Unique enterprise identifier (RFC-4122).
  - tax_id (VARCHAR(32), UNIQUE, NOT NULL): State tax registration number.
  - legal_name (VARCHAR(255), NOT NULL): Registered corporate legal title.
  - industry_code (VARCHAR(16), NOT NULL): Standard sector classification (NACE/SIC).
  - registration_date (DATE, NOT NULL): Official date of legal establishment.
  - total_board_seats (INT, DEFAULT 1): Total seats on the board of directors.
  - independent_directors_count (INT, DEFAULT 0): Non-executive external directors.
  - Constraints: CHECK (total_board_seats >= 1), CHECK (independent_directors_count >= 0),
    CHECK (independent_directors_count <= total_board_seats).

* Table: shareholders
  Represents equity cap-table distribution and managerial overlap.
  - ownership_id (UUID, PK): Unique equity record identifier.
  - business_id (UUID, FK -> businesses.business_id ON DELETE CASCADE, NOT NULL).
  - shareholder_name (VARCHAR(255), NOT NULL): Legal name of owner.
  - equity_percentage (DECIMAL(5,2), NOT NULL): Equity holding (0.00% to 100.00%).
  - is_management_member (BOOLEAN, DEFAULT FALSE): Executive/board membership flag.
  - Constraints: CHECK (equity_percentage >= 0.00 AND equity_percentage <= 100.00).

4.2 Cluster 2: External Intelligence & Open Data
* Table: web_reputation
  Time-stamped snapshots gathered by background OSINT collectors and scrapers.
  - record_id (UUID, PK): Unique snapshot identifier.
  - business_id (UUID, FK -> businesses.business_id ON DELETE CASCADE, NOT NULL).
  - scan_timestamp (TIMESTAMP WITH TIME ZONE, NOT NULL, DEFAULT NOW()).
  - active_lawsuits_count (INT, DEFAULT 0): Open court/litigation cases as defendant.
  - total_lawsuit_claims_amount (DECIMAL(18,2), DEFAULT 0.00): Total monetary claims.
  - is_in_sanctions_list (BOOLEAN, DEFAULT FALSE): AML/sanctions watchlist hit.
  - news_sentiment_score (DECIMAL(4,3), NULL): NLP sentiment score (-1.000 to +1.000).
  - web_traffic_monthly_visits (INT, NULL): Estimated web traffic volume.
  - Indexes: (business_id, scan_timestamp DESC).

* Table: macro_sector_metrics
  Industry-level macroeconomic reference data linked via sector classification codes.
  - metric_id (UUID, PK): Unique metric record identifier.
  - industry_code (VARCHAR(16), NOT NULL): Target sector classification.
  - reference_date (DATE, NOT NULL): Period of statistical calculation.
  - sector_growth_rate_yoy (DECIMAL(5,2), NOT NULL): Sector annual growth rate %.
  - sector_default_rate (DECIMAL(5,2), NOT NULL): Baseline loan default rate %.
  - risk_outlook_score (INT, NOT NULL): Regulatory/macro threat level (1 to 10).
  - Constraints: CHECK (risk_outlook_score BETWEEN 1 AND 10).
  - Indexes: (industry_code, reference_date DESC).

4.3 Cluster 3: Commercial Graph & Cash Flow Ledger
* Table: counterparties
  Master entity ledger of trading partners identified in invoices and banking statements.
  - counterparty_id (UUID, PK): Unique counterparty identifier.
  - business_id (UUID, FK -> businesses.business_id ON DELETE CASCADE, NOT NULL).
  - tax_id (VARCHAR(32), NULL): Counterparty national tax registration number.
  - legal_name (VARCHAR(255), NOT NULL): Registered title of trading partner.
  - counterparty_role (VARCHAR(16), NOT NULL): Commercial role.
    Enum / CHECK: 'CLIENT', 'SUPPLIER', 'MIXED', 'BOTH'.
  - Indexes: (business_id, counterparty_role).

* Table: invoices
  Commercial receivables and payables tracking contractual payment discipline.
  - invoice_id (UUID, PK): Unique invoice identifier.
  - business_id (UUID, FK -> businesses.business_id ON DELETE CASCADE, NOT NULL).
  - counterparty_id (UUID, FK -> counterparties.counterparty_id, NOT NULL).
  - invoice_type (VARCHAR(16), NOT NULL): Role direction.
    Enum / CHECK: 'RECEIVABLE', 'PAYABLE'.
  - gross_amount (DECIMAL(18,2), NOT NULL): Nominal invoice monetary total (> 0.00).
  - issue_date (DATE, NOT NULL): Issuance date.
  - due_date (DATE, NOT NULL): Contractual settlement deadline.
  - actual_payment_date (DATE, NULL): Actual date full payment was cleared.
  - status (VARCHAR(16), NOT NULL): Payment lifecycle state.
    Enum / CHECK: 'PAID', 'SETTLED', 'OUTSTANDING', 'OVERDUE', 'DEFAULTED', 'DISPUTED'.
  - Constraints: CHECK (gross_amount > 0.00). DAL applies defensive abs() on intake.
  - Indexes: (business_id, status), (due_date).

* Table: bank_accounts
  Commercial bank accounts, cleared liquid balances, and authorized credit lines.
  - account_id (UUID, PK): Unique bank account identifier.
  - business_id (UUID, FK -> businesses.business_id ON DELETE CASCADE, NOT NULL).
  - currency (VARCHAR(3), NOT NULL): ISO currency code ('MDL', 'EUR', 'USD').
  - current_balance (DECIMAL(18,2), NOT NULL): Cleared cash balance.
  - overdraft_limit (DECIMAL(18,2), DEFAULT 0.00): Approved revolving credit line.
  - Constraints: CHECK (overdraft_limit >= 0.00).

* Table: transactions
  Granular bank statement ledger lines linking flows to categories and counterparties.
  - transaction_id (UUID, PK): Unique transaction identifier.
  - business_id (UUID, FK -> businesses.business_id ON DELETE CASCADE, NOT NULL).
  - account_id (UUID, FK -> bank_accounts.account_id, NOT NULL).
  - counterparty_id (UUID, FK -> counterparties.counterparty_id, NULL).
  - invoice_id (UUID, FK -> invoices.invoice_id, NULL).
  - timestamp (TIMESTAMP WITH TIME ZONE, NOT NULL): Execution timestamp.
  - amount (DECIMAL(18,2), NOT NULL): Monetary value (strictly non-negative).
  - direction (VARCHAR(8), NOT NULL): Enum / CHECK: 'INFLOW', 'OUTFLOW'.
  - category (VARCHAR(32), NOT NULL): Cash flow classification.
    Enum / CHECK: 'REVENUE', 'CLIENT_REVENUE', 'OPERATING_EXPENSE',
    'SUPPLIER_PAYMENT', 'PAYROLL', 'TAX', 'DEBT_SERVICE',
    'CREDIT_REPAYMENT', 'INTEREST_FEE', 'DIVIDEND', 'OTHER'.
  - liquidity_class (VARCHAR(24), NOT NULL, DEFAULT 'IMMEDIATE_CASH'):
    Enum / CHECK: 'IMMEDIATE_CASH', 'SHORT_TERM_RECEIVABLE',
    'RESTRICTED_ESCROW', 'TERM_DEPOSIT', 'TIED_CAPITAL'.
  - Constraints: CHECK (amount >= 0.00). DAL applies defensive abs() on intake.
  - Indexes: (business_id, timestamp DESC), (category).

4.4 Cluster 4: Liabilities & Repayment Track Record
* Table: credit_obligations
  Direct loan facilities, bank credit lines, factoring agreements, and leasing.
  - obligation_id (UUID, PK): Unique facility identifier.
  - business_id (UUID, FK -> businesses.business_id ON DELETE CASCADE, NOT NULL).
  - lender_name (VARCHAR(255), NOT NULL): Financial institution or debt holder.
  - facility_type (VARCHAR(32), NOT NULL): Credit vehicle category.
    Enum / CHECK: 'TERM_LOAN', 'CREDIT_LINE', 'LINE_OF_CREDIT',
    'OVERDRAFT', 'LEASING', 'FACTORING'.
  - principal_amount (DECIMAL(18,2), NOT NULL): Original facility size.
  - outstanding_balance (DECIMAL(18,2), NOT NULL): Current unpaid principal balance.
  - monthly_payment (DECIMAL(18,2), NOT NULL): Contractual monthly debt service.
  - past_due_30d_count (INT, DEFAULT 0): Historical delinquency instances (1-30 DPD).
  - past_due_90d_count (INT, DEFAULT 0): Historical delinquency instances (31-90 DPD).
  - historical_defaults_count (INT, DEFAULT 0): Severe defaults (90+ DPD).
  - Constraints: CHECK (principal_amount >= 0.00), CHECK (outstanding_balance >= 0.00),
    CHECK (monthly_payment >= 0.00), CHECK (past_due_30d_count >= 0),
    CHECK (past_due_90d_count >= 0), CHECK (historical_defaults_count >= 0).
    DAL mutation methods defensively apply abs() across all monetary balances.

4.5 Cluster 5: Web Application Identity & Execution Telemetry
* Table: users
  Authentication credentials, roles, and administrative flags.
  - user_id (UUID, PK): Unique user identifier (RFC-4122).
  - email (VARCHAR(255), UNIQUE, NOT NULL): Corporate email address.
  - password_hash (VARCHAR(255), NOT NULL): Argon2id password digest.
  - full_name (VARCHAR(128), NOT NULL): User legal name.
  - role (VARCHAR(32), DEFAULT 'ANALYST'): Enum / CHECK: 'ADMIN', 'UNDERWRITER', 'ANALYST'.
  - is_active (BOOLEAN, DEFAULT TRUE): Account status flag.
  - created_at (TIMESTAMP WITH TIME ZONE, DEFAULT NOW()): Registration timestamp.

* Table: user_settings
  Persistent UI workspace preferences and theme options.
  - setting_id (UUID, PK): Unique setting identifier.
  - user_id (UUID, FK -> users.user_id ON DELETE CASCADE, UNIQUE, NOT NULL).
  - ui_theme (VARCHAR(16), DEFAULT 'system'): Enum / CHECK: 'light', 'dark', 'system'.
  - terminal_sound_effects (BOOLEAN, DEFAULT FALSE): Audio toggle for console logs.
  - auto_expand_reports (BOOLEAN, DEFAULT TRUE): Diagnostic view state toggle.

* Table: analysis_runs
  Permanent historical audit ledger. Preserves input payloads, feature vectors, verdicts,
  and diagnostic reports for both COMPLETED and FAILED runs. Directly serves the historical
  runs overview (/history); no 14th table exists.
  - run_id (UUID, PK): Unique evaluation job identifier (RFC-4122).
  - user_id (UUID, FK -> users.user_id, NOT NULL): Requesting underwriter.
  - business_id (UUID, FK -> businesses.business_id, NULL): Associated company.
  - status (VARCHAR(32), NOT NULL, DEFAULT 'QUEUED'): Pipeline execution state.
    Enum / CHECK: 'QUEUED', 'PARSING', 'PROCESSING', 'COMPLETED', 'FAILED', 'DEGRADED'.
  - input_company_name (VARCHAR(255), NOT NULL): Declared corporate legal name.
  - input_tax_id (VARCHAR(32), NOT NULL): Declared national tax identification.
  - input_industry_code (VARCHAR(16), NOT NULL): Sector classification code.
  - files_manifest (JSONB, NOT NULL): Metadata of uploaded financial files.
  - active_submodules (JSONB, NOT NULL): List of enabled submodule identifiers.
  - raw_indices_payload (JSONB, NULL): Aggregated 18D numerical feature vector.
  - submodules_reports (JSONB, NULL): Granular submodule reports and verdicts.
  - llm_final_summary (TEXT, NULL): Synthesis generated by Gemini / LLM layer.
  - universal_score (DECIMAL(5,2), NULL): Normalized overall score (0.00 to 100.00).
  - verdict_category (VARCHAR(32), NULL): Risk classification.
    Enum / CHECK: 'PRIME_LOW_RISK', 'MODERATE_MONITORED', 'HIGH_RISK_REJECT'.
  - recommendation (VARCHAR(32), NULL): Underwriting recommendation.
    Enum / CHECK: 'APPROVED', 'MANUAL_REVIEW', 'REJECTED'.
  - failure_reason (TEXT, NULL): Error diagnostics if status is 'FAILED'.
  - created_at (TIMESTAMP WITH TIME ZONE, DEFAULT NOW()): Initiation timestamp.
  - completed_at (TIMESTAMP WITH TIME ZONE, NULL): Completion timestamp.
  - Indexes: (user_id, created_at DESC), (status).

* Table: analysis_logs
  Live console telemetry events emitted during submodule and pipeline execution.
  - log_id (BIGSERIAL, PK): Incrementing log sequence ID.
  - run_id (UUID, FK -> analysis_runs.run_id ON DELETE CASCADE, NOT NULL).
  - timestamp (TIMESTAMP WITH TIME ZONE, DEFAULT NOW()): Event timestamp.
  - severity (VARCHAR(16), NOT NULL): Enum / CHECK: 'DEBUG', 'INFO', 'WARN', 'ERROR'.
  - stage (VARCHAR(32), NOT NULL): Pipeline execution stage.
  - message (TEXT, NOT NULL): Diagnostic message payload.
  - Indexes: (run_id, timestamp ASC).


5. DATA ACCESS LAYER (DAL) API SPECIFICATION (57 ASYNC METHODS)
--------------------------------------------------------------------------------
The Database class in connection.py and the MockDatabase class in mock_connection.py
expose exactly 57 asynchronous methods providing complete parity across real and mock
environments. All query inputs are parameterized via psycopg.sql.

5.1 Universal Dynamic Query Building & Input Sanitization
All query filters and column identifiers are securely assembled using psycopg.sql:

```python
def _build_where_clause(filters: dict) -> tuple[sql.Composed, list]:
    conditions = []
    values = []
    for col, val in filters.items():
        if val is not None:
            conditions.append(sql.SQL("{col} = %s").format(col=sql.Identifier(col)))
            values.append(val)
    if not conditions:
        return sql.SQL(""), []
    return sql.SQL(" WHERE ") + sql.SQL(" AND ").join(conditions), values
```

Defensive Magnitude Normalization (`abs()`):
To guarantee strict compliance with PostgreSQL non-negative CHECK constraints
(`amount >= 0.00`, `gross_amount > 0.00`, `principal_amount >= 0.00`), all DAL mutation
methods (`add_record_to_transactions`, `bulk_insert_transactions`, `add_record_to_invoices`,
`bulk_insert_invoices`, `add_record_to_credit_obligations`) automatically apply `abs()`
to monetary inputs before parameter binding or streaming serialization. This defensively
neutralizes signed debits or negative outflow conventions present in raw banking statements.

5.2 DAL Signatures: Cluster 1 (businesses, shareholders)
```python
# Table: businesses
async def add_record_to_businesses(
    self, tax_id: str, legal_name: str, industry_code: str,
    registration_date: date, business_id: Optional[UUID] = None,
    total_board_seats: int = 1, independent_directors_count: int = 0
) -> DatabaseReport: ...

async def get_records_from_businesses(
    self, find_only_first: bool = False, limit: Optional[int] = None,
    offset: Optional[int] = None, **filters
) -> DatabaseReport: ...

async def update_records_in_businesses(
    self, updates: Dict[str, Any], **filters
) -> DatabaseReport: ...

async def delete_records_from_businesses(
    self, delete_only_first: bool = False, **filters
) -> DatabaseReport: ...

# Table: shareholders
async def add_record_to_shareholders(
    self, business_id: UUID, shareholder_name: str, equity_percentage: Decimal,
    is_management_member: bool = False, ownership_id: Optional[UUID] = None
) -> DatabaseReport: ...

async def get_records_from_shareholders(
    self, find_only_first: bool = False, limit: Optional[int] = None,
    offset: Optional[int] = None, **filters
) -> DatabaseReport: ...

async def update_records_in_shareholders(
    self, updates: Dict[str, Any], **filters
) -> DatabaseReport: ...

async def delete_records_from_shareholders(
    self, delete_only_first: bool = False, **filters
) -> DatabaseReport: ...
```

5.3 DAL Signatures: Cluster 2 (web_reputation, macro_sector_metrics)
```python
# Table: web_reputation
async def add_record_to_web_reputation(
    self, business_id: UUID, scan_timestamp: Optional[datetime] = None,
    active_lawsuits_count: int = 0,
    total_lawsuit_claims_amount: Decimal = Decimal("0.00"),
    is_in_sanctions_list: bool = False,
    news_sentiment_score: Optional[Decimal] = None,
    web_traffic_monthly_visits: Optional[int] = None,
    record_id: Optional[UUID] = None
) -> DatabaseReport: ...

async def get_records_from_web_reputation(
    self, find_only_first: bool = False, limit: Optional[int] = None,
    offset: Optional[int] = None, **filters
) -> DatabaseReport: ...

async def update_records_in_web_reputation(
    self, updates: Dict[str, Any], **filters
) -> DatabaseReport: ...

async def delete_records_from_web_reputation(
    self, delete_only_first: bool = False, **filters
) -> DatabaseReport: ...

# Table: macro_sector_metrics
async def add_record_to_macro_sector_metrics(
    self, industry_code: str, reference_date: date,
    sector_growth_rate_yoy: Decimal, sector_default_rate: Decimal,
    risk_outlook_score: int, metric_id: Optional[UUID] = None
) -> DatabaseReport: ...

async def get_records_from_macro_sector_metrics(
    self, find_only_first: bool = False, limit: Optional[int] = None,
    offset: Optional[int] = None, **filters
) -> DatabaseReport: ...

async def update_records_in_macro_sector_metrics(
    self, updates: Dict[str, Any], **filters
) -> DatabaseReport: ...

async def delete_records_from_macro_sector_metrics(
    self, delete_only_first: bool = False, **filters
) -> DatabaseReport: ...
```

5.4 DAL Signatures: Cluster 3 (counterparties, invoices, bank_accounts, transactions)
```python
# Table: counterparties
async def add_record_to_counterparties(
    self, business_id: UUID, legal_name: str, counterparty_role: str,
    tax_id: Optional[str] = None, counterparty_id: Optional[UUID] = None
) -> DatabaseReport: ...

async def get_records_from_counterparties(
    self, find_only_first: bool = False, limit: Optional[int] = None,
    offset: Optional[int] = None, **filters
) -> DatabaseReport: ...

async def update_records_in_counterparties(
    self, updates: Dict[str, Any], **filters
) -> DatabaseReport: ...

async def delete_records_from_counterparties(
    self, delete_only_first: bool = False, **filters
) -> DatabaseReport: ...

# Table: invoices
async def add_record_to_invoices(
    self, business_id: UUID, counterparty_id: UUID, invoice_type: str,
    gross_amount: Decimal, issue_date: date, due_date: date, status: str,
    actual_payment_date: Optional[date] = None,
    invoice_id: Optional[UUID] = None
) -> DatabaseReport: ...

async def get_records_from_invoices(
    self, find_only_first: bool = False, limit: Optional[int] = None,
    offset: Optional[int] = None, **filters
) -> DatabaseReport: ...

async def update_records_in_invoices(
    self, updates: Dict[str, Any], **filters
) -> DatabaseReport: ...

async def delete_records_from_invoices(
    self, delete_only_first: bool = False, **filters
) -> DatabaseReport: ...

# Table: bank_accounts
async def add_record_to_bank_accounts(
    self, business_id: UUID, currency: str, current_balance: Decimal,
    overdraft_limit: Decimal = Decimal("0.00"),
    account_id: Optional[UUID] = None
) -> DatabaseReport: ...

async def get_records_from_bank_accounts(
    self, find_only_first: bool = False, limit: Optional[int] = None,
    offset: Optional[int] = None, **filters
) -> DatabaseReport: ...

async def update_records_in_bank_accounts(
    self, updates: Dict[str, Any], **filters
) -> DatabaseReport: ...

async def delete_records_from_bank_accounts(
    self, delete_only_first: bool = False, **filters
) -> DatabaseReport: ...

# Table: transactions
async def add_record_to_transactions(
    self, business_id: UUID, account_id: UUID, timestamp: datetime,
    amount: Decimal, direction: str, category: str,
    liquidity_class: str = "IMMEDIATE_CASH",
    counterparty_id: Optional[UUID] = None, invoice_id: Optional[UUID] = None,
    transaction_id: Optional[UUID] = None
) -> DatabaseReport: ...

async def get_records_from_transactions(
    self, find_only_first: bool = False, limit: Optional[int] = None,
    offset: Optional[int] = None, **filters
) -> DatabaseReport: ...

async def update_records_in_transactions(
    self, updates: Dict[str, Any], **filters
) -> DatabaseReport: ...

async def delete_records_from_transactions(
    self, delete_only_first: bool = False, **filters
) -> DatabaseReport: ...
```

5.5 DAL Signatures: Cluster 4 (credit_obligations)
```python
# Table: credit_obligations
async def add_record_to_credit_obligations(
    self, business_id: UUID, lender_name: str, facility_type: str,
    principal_amount: Decimal, outstanding_balance: Decimal,
    monthly_payment: Decimal, past_due_30d_count: int = 0,
    past_due_90d_count: int = 0, historical_defaults_count: int = 0,
    obligation_id: Optional[UUID] = None
) -> DatabaseReport: ...

async def get_records_from_credit_obligations(
    self, find_only_first: bool = False, limit: Optional[int] = None,
    offset: Optional[int] = None, **filters
) -> DatabaseReport: ...

async def update_records_in_credit_obligations(
    self, updates: Dict[str, Any], **filters
) -> DatabaseReport: ...

async def delete_records_from_credit_obligations(
    self, delete_only_first: bool = False, **filters
) -> DatabaseReport: ...
```

5.6 DAL Signatures: Cluster 5 (users, user_settings, analysis_runs, analysis_logs)
```python
# Table: users
async def add_record_to_users(
    self, email: str, password_hash: str, full_name: str,
    role: str = "ANALYST", is_active: bool = True,
    user_id: Optional[UUID] = None
) -> DatabaseReport: ...

async def get_records_from_users(
    self, find_only_first: bool = False, limit: Optional[int] = None,
    offset: Optional[int] = None, **filters
) -> DatabaseReport: ...

async def update_records_in_users(
    self, updates: Dict[str, Any], **filters
) -> DatabaseReport: ...

async def delete_records_from_users(
    self, delete_only_first: bool = False, **filters
) -> DatabaseReport: ...

# Table: user_settings
async def add_record_to_user_settings(
    self, user_id: UUID, ui_theme: str = "system",
    terminal_sound_effects: bool = False,
    auto_expand_reports: bool = True,
    setting_id: Optional[UUID] = None
) -> DatabaseReport: ...

async def get_records_from_user_settings(
    self, find_only_first: bool = False, limit: Optional[int] = None,
    offset: Optional[int] = None, **filters
) -> DatabaseReport: ...

async def update_records_in_user_settings(
    self, updates: Dict[str, Any], **filters
) -> DatabaseReport: ...

async def delete_records_from_user_settings(
    self, delete_only_first: bool = False, **filters
) -> DatabaseReport: ...

# Table: analysis_runs (Full signature including verdict and recommendation)
async def add_record_to_analysis_runs(
    self, user_id: UUID, input_company_name: str, input_tax_id: str,
    input_industry_code: str, files_manifest: Dict[str, Any],
    active_submodules: List[str], status: str = "QUEUED",
    business_id: Optional[UUID] = None, run_id: Optional[UUID] = None,
    raw_indices_payload: Optional[Dict[str, Any]] = None,
    submodules_reports: Optional[List[Dict[str, Any]]] = None,
    llm_final_summary: Optional[str] = None,
    universal_score: Optional[Decimal] = None,
    verdict_category: Optional[str] = None,
    recommendation: Optional[str] = None,
    failure_reason: Optional[str] = None
) -> DatabaseReport: ...

async def get_records_from_analysis_runs(
    self, find_only_first: bool = False, limit: Optional[int] = None,
    offset: Optional[int] = None, **filters
) -> DatabaseReport: ...

async def update_records_in_analysis_runs(
    self, updates: Dict[str, Any], **filters
) -> DatabaseReport: ...

async def delete_records_from_analysis_runs(
    self, delete_only_first: bool = False, **filters
) -> DatabaseReport: ...

# Table: analysis_logs
async def add_record_to_analysis_logs(
    self, run_id: UUID, severity: str, stage: str, message: str,
    timestamp: Optional[datetime] = None, log_id: Optional[int] = None
) -> DatabaseReport: ...

async def get_records_from_analysis_logs(
    self, find_only_first: bool = False, limit: Optional[int] = None,
    offset: Optional[int] = None, **filters
) -> DatabaseReport: ...

async def update_records_in_analysis_logs(
    self, updates: Dict[str, Any], **filters
) -> DatabaseReport: ...

async def delete_records_from_analysis_logs(
    self, delete_only_first: bool = False, **filters
) -> DatabaseReport: ...
```

5.7 High-Performance Bulk Streaming Extensions
To support high-velocity tabular ingestion into transactions and invoices without
per-row network roundtrips, the DAL implements streaming via psycopg cursor.copy():

```python
async def bulk_insert_transactions(
    self, records: List[Dict[str, Any]]
) -> DatabaseReport: ...

async def bulk_insert_invoices(
    self, records: List[Dict[str, Any]]
) -> DatabaseReport: ...
```
Streaming execution scales pipeline ingestion throughput to over 50,000 records
per second using binary or formatted tab-delimited streams. Both streaming methods
defensively apply `abs()` to monetary fields before serializing into the COPY buffer.

5.8 Connection Lifecycle & Vitality
```python
def open(self) -> None: ...
def close(self) -> None: ...
async def health_check(self) -> bool: ...
```


6. CONCURRENCY, TRANSACTIONS & PERFORMANCE
--------------------------------------------------------------------------------
6.1 Isolation Levels
Default isolation level is READ COMMITTED, eliminating dirty reads while preventing
serialization bottlenecks during parallel analysis submodule executions.
Critical analytical rollups utilize REPEATABLE READ if point-in-time cross-table
auditing is mandated.

6.2 Foreign Key Indexing & Query Acceleration
To avoid sequential table scans during analytical submodule joins, composite indexes
are established on Foreign Keys and temporal filter columns:

```sql
CREATE INDEX idx_trans_biz_time ON transactions (business_id, timestamp DESC);
CREATE INDEX idx_invoices_biz_status ON invoices (business_id, status);
CREATE INDEX idx_logs_run_seq ON analysis_logs (run_id, timestamp ASC);
CREATE INDEX idx_runs_user_date ON analysis_runs (user_id, created_at DESC);
CREATE INDEX idx_counterparties_biz_role ON counterparties (business_id, counterparty_role);
CREATE INDEX idx_reputation_biz_time ON web_reputation (business_id, scan_timestamp DESC);
CREATE INDEX idx_macro_ind_date ON macro_sector_metrics (industry_code, reference_date DESC);
```

6.3 Connection Pool Sizing Equation
Pool size is calibrated against the maximum worker threads in Uvicorn:
`Pool_Max_Size = (Uvicorn_Workers * Concurrent_Coroutines_Per_Worker) + Background_Workers`
Nominal setting: 20 pooled connections per backend container instance.


7. SECURITY, SANITIZATION & HARDENING
--------------------------------------------------------------------------------
7.1 SQL Injection Neutralization
All queries employ parameterized placeholders assembled safely via psycopg.sql:

```python
# CORRECT & SECURE:
query = sql.SQL("SELECT * FROM {table} WHERE {col} = %s").format(
    table=sql.Identifier("businesses"),
    col=sql.Identifier("tax_id")
)
await cursor.execute(query, [sanitized_tax_id])
```

Direct string formatting (f-strings, %, or .format()) within SQL statements is
strictly prohibited and rejected during automated linting and code review.

7.2 Privilege Separation & Role Hardening
The database enforces three distinct PostgreSQL user roles:
* app_migration_user: DDL permissions (CREATE, ALTER, DROP) used exclusively by migrations.
* app_runtime_user: DML permissions (SELECT, INSERT, UPDATE, DELETE) for the FastAPI
  backend and analytical workers.
* readonly_analyst: SELECT-only permissions on reporting views.

7.3 Encryption & Transport Security
All database communication enforces TLS 1.3 encryption (sslmode=verify-full).
Authentication secrets and API keys are read from environment variables; password
hashes in the users table are salted using Argon2id.


8. TESTING & IN-MEMORY MOCK IMPLEMENTATION (MockDatabase)
--------------------------------------------------------------------------------
To support offline development, CI pipelines, and unit testing without requiring
a running PostgreSQL instance, MockDatabase in mock_connection.py provides 100%
interface parity with the real Database class across all 57 methods.

The in-memory storage dictionary initializes all 13 tables:

```python
class MockDatabase:
    """
    In-memory mock reproducing the complete 57-method Database interface.
    """
    def __init__(self) -> None:
        self._storage: Dict[str, List[Dict[str, Any]]] = {
            "businesses": [],
            "shareholders": [],
            "web_reputation": [],
            "macro_sector_metrics": [],
            "counterparties": [],
            "invoices": [],
            "bank_accounts": [],
            "transactions": [],
            "credit_obligations": [],
            "users": [],
            "user_settings": [],
            "analysis_runs": [],
            "analysis_logs": [],
        }

    async def add_record_to_businesses(self, **kwargs) -> DatabaseReport:
        record = dict(kwargs)
        if "business_id" not in record or record["business_id"] is None:
            record["business_id"] = uuid4()
        self._storage["businesses"].append(record)
        return DatabaseReport(success=True, data=record, affected_rows=1)

    async def get_records_from_businesses(
        self, find_only_first: bool = False, **filters
    ) -> DatabaseReport:
        results = [
            row for row in self._storage["businesses"]
            if all(row.get(k) == v for k, v in filters.items() if v is not None)
        ]
        if find_only_first:
            data = results[0] if results else None
            return DatabaseReport(success=True, data=data, affected_rows=int(bool(results)))
        return DatabaseReport(success=True, data=results, affected_rows=len(results))

    async def update_records_in_businesses(
        self, updates: Dict[str, Any], **filters
    ) -> DatabaseReport:
        affected = 0
        for row in self._storage["businesses"]:
            if all(row.get(k) == v for k, v in filters.items() if v is not None):
                row.update(updates)
                affected += 1
        return DatabaseReport(success=True, affected_rows=affected)

    async def delete_records_from_businesses(
        self, delete_only_first: bool = False, **filters
    ) -> DatabaseReport:
        initial_len = len(self._storage["businesses"])
        self._storage["businesses"] = [
            row for row in self._storage["businesses"]
            if not all(row.get(k) == v for k, v in filters.items() if v is not None)
        ]
        return DatabaseReport(
            success=True, affected_rows=initial_len - len(self._storage["businesses"])
        )

    def reset(self) -> None:
        """Helper method for unit tests to clear all storage state."""
        for key in self._storage:
            self._storage[key].clear()
```

================================================================================
END OF SPECIFICATION
================================================================================
