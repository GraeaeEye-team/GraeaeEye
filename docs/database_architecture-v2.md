```text
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
submodules, background data ingestion routines, and the FastAPI presentation layer[cite: 1, 3, 5].

1.2 Architectural Philosophy
* Non-Blocking Asynchrony: Built natively for Python AsyncIO leveraging `psycopg`
  (v3) and `psycopg_pool.AsyncConnectionPool` to guarantee high-throughput, non-blocking
  I/O during concurrent API requests and telemetry log streaming[cite: 5].
* Strict Parameterization & Injection Immunity: Absolute prohibition of dynamic string
  interpolation (f-strings) in query execution. Structural schema identifiers and
  dynamic filters are securely assembled via `psycopg.sql.SQL`, while data literals
  are bound exclusively via parameterized positional or named placeholders[cite: 5].
* Deterministic Result Contracts: All database interactions return a strongly typed,
  standardized `DatabaseReport` container, eliminating raw cursor leakages and providing
  uniform error encapsulation, row impact telemetry, and dictionary-mapped records[cite: 5].
* Entity Graph Integrity: Maintains relational constraints across core business profiles,
  B2B commercial counterparty interactions, historical facilities, and web snapshots[cite: 3, 5].


2. HIGH-LEVEL ARCHITECTURE & CONNECTION SUBSYSTEM
--------------------------------------------------------------------------------
2.1 Connection Pool Architecture
The module encapsulates connection lifecycle management within a singleton or shared
`Database` class in `connection.py`[cite: 5]. It utilizes `psycopg_pool.AsyncConnectionPool`
with client-side dictionary row mapping (`row_factory=dict_row`)[cite: 5].

+------------------------------------------------------------------------------+
|                            FastAPI / Engine Workers / Other Modules          |
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
+---------------+             +---------------+              +---------------+
| Connection 1  |             | Connection 2  |              | Connection N  |
| (dict_row)    |             | (dict_row)    |              | (dict_row)    |
+---------------+             +---------------+              +---------------+
                                      |
                                      v
+------------------------------------------------------------------------------+
|                         PostgreSQL 15+ Relational DB                         |
+------------------------------------------------------------------------------+

2.2 Connection Lifecycle & Settings
* Pool Sizing: Minimum pool size (`min_size=4`), Maximum pool size (`max_size=20`),
  maximum idle lifetime (`max_idle=300.0` seconds).
* Health Check: Validates connection vitality via `SELECT 1` on checkout or ping.
* Context-Managed Transactions: Every operation is guarded by asynchronous context
  managers (`async with self.pool.connection() as conn: async with conn.transaction():`),
  guaranteeing atomic rollbacks on exceptions and automated commits on success.


3. UNIFIED DATA CONTRACT: `DatabaseReport`
--------------------------------------------------------------------------------
All operations (insert, select, update, delete) return an immutable `DatabaseReport`
instance to decouple application logic from database driver internals[cite: 5].

```python
from dataclasses import dataclass
from typing import Any, List, Optional, Union

@dataclass(frozen=True)
class DatabaseReport:
    """
    Standardized result contract for all Database operations.
    """
    success: bool
    data: Optional[Union[List[dict], dict]] = None
    affected_rows: int = 0
    error: Optional[str] = None
    operation: Optional[str] = None
    table_name: Optional[str] = None

```

3.1 Operational Semantics

* Retrieval Operations (`get_*`): If matching records are found, `success=True`,
`data` contains a list of dicts (or a single dict if `find_only_first=True`),
and `affected_rows` equals the count of records retrieved. If zero matches occur,
`success=True`, `data=[]` (or `None`), and `affected_rows=0`.


* Mutation Operations (`add_*`, `update_*`, `delete_*`): `affected_rows` reflects
rows inserted, updated, or removed. `data` contains returned records via `RETURNING *`
when requested.
* Exceptional States: On database exceptions (`psycopg.Error`, network drop, constraint
violation), the transaction is rolled back, returning `success=False`, `data=None`,
`affected_rows=0`, and `error` populated with the sanitized driver message.

4. COMPREHENSIVE RELATIONAL SCHEMA CATALOG

---

The relational schema comprises 13 tables partitioned into 5 functional clusters.

4.1 Cluster 1: Core Corporate Identity & Governance

* `businesses`: Corporate baseline information, tax identifiers, board size, and
independent director counts.


* Primary Key: `business_id` (UUID)


* Unique Constraints: `tax_id` (VARCHAR(32))


* Foreign Keys: None


* `shareholders`: Cap-table distribution, ownership percentage, and executive status.


* Primary Key: `ownership_id` (UUID)


* Foreign Keys: `business_id` -> `businesses(business_id)` ON DELETE CASCADE





4.2 Cluster 2: External Intelligence & Macro Data

* `web_reputation`: Snapshots of litigation counts, total claims, sanctions flags,
and scraped news sentiment.


* Primary Key: `record_id` (UUID)


* Foreign Keys: `business_id` -> `businesses(business_id)` ON DELETE CASCADE


* Indexes: `(business_id, scan_timestamp DESC)`



* `macro_sector_metrics`: Industry benchmark data tracking growth, default rates,
and risk outlook.


* Primary Key: `metric_id` (UUID)


* Indexes: `(industry_code, reference_date DESC)`




4.3 Cluster 3: Commercial Graph & Cash Flow Ledger

* `counterparties`: Client and supplier master data.


* Primary Key: `counterparty_id` (UUID)


* Foreign Keys: `business_id` -> `businesses(business_id)` ON DELETE CASCADE




* `invoices`: Commercial trade payables and receivables tracking contractual versus
actual payment settlement.


* Primary Key: `invoice_id` (UUID)


* Foreign Keys: `business_id` -> `businesses(business_id)`,
`counterparty_id` -> `counterparties(counterparty_id)`

* Indexes: `(business_id, status)`, `(due_date)`



* `bank_accounts`: Commercial bank accounts, currencies, cleared balances, and overdrafts.


* Primary Key: `account_id` (UUID)


* Foreign Keys: `business_id` -> `businesses(business_id)` ON DELETE CASCADE




* `transactions`: Bank statement transaction ledgers with categorical mapping.


* Primary Key: `transaction_id` (UUID)


* Foreign Keys: `business_id` -> `businesses(business_id)`,
`account_id` -> `bank_accounts(account_id)`,
`counterparty_id` -> `counterparties(counterparty_id)` (nullable),
`invoice_id` -> `invoices(invoice_id)` (nullable)


* Indexes: `(business_id, timestamp DESC)`, `(category)`




4.4 Cluster 4: Liabilities & Repayment Track Record

* `credit_obligations`: Credit facilities, loans, and historical past-due indicators.


* Primary Key: `obligation_id` (UUID)


* Foreign Keys: `business_id` -> `businesses(business_id)` ON DELETE CASCADE





4.5 Cluster 5: Web Application Identity & Execution Telemetry

* `users`: Authentication credentials and user roles.


* Primary Key: `user_id` (UUID)


* Unique Constraints: `email`



* `user_settings`: UI workspace preferences and theme toggles.


* Primary Key: `setting_id` (UUID)


* Foreign Keys: `user_id` -> `users(user_id)` ON DELETE CASCADE




* `analysis_runs`: Pipeline execution state, file manifest, raw feature vectors, and LLM output.


* Primary Key: `run_id` (UUID)


* Foreign Keys: `user_id` -> `users(user_id)`,
`business_id` -> `businesses(business_id)` (nullable)


* Indexes: `(user_id, created_at DESC)`, `(status)`



* `analysis_logs`: Live console events emitted during pipeline execution.


* Primary Key: `log_id` (BIGSERIAL)


* Foreign Keys: `run_id` -> `analysis_runs(run_id)` ON DELETE CASCADE


* Indexes: `(run_id, timestamp ASC)`




5. DATA ACCESS LAYER (DAL) API SPECIFICATION

---

The `Database` class in `connection.py` exposes explicit, strongly typed asynchronous
methods for every table in the system. Dynamic filter and update parameters are
assembled using `psycopg.sql` constructs.

5.1 Universal Dynamic Query Building Mechanism

```python
# Internal query building standard
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

5.2 DAL Method Signatures: Core Corporate Identity

* Table `businesses`:


* `async def add_record_to_businesses(self, tax_id: str, legal_name: str, industry_code: str, registration_date: date, business_id: Optional[UUID] = None, total_board_seats: int = 1, independent_directors_count: int = 0) -> DatabaseReport`

* `async def get_records_from_businesses(self, find_only_first: bool = False, limit: Optional[int] = None, offset: Optional[int] = None, **filters) -> DatabaseReport`

* `async def update_records_in_businesses(self, updates: dict, **filters) -> DatabaseReport`

* `async def delete_records_from_businesses(self, delete_only_first: bool = False, **filters) -> DatabaseReport`



* Table `shareholders`:


* `async def add_record_to_shareholders(self, business_id: UUID, shareholder_name: str, equity_percentage: Decimal, is_management_member: bool, ownership_id: Optional[UUID] = None) -> DatabaseReport`

* `async def get_records_from_shareholders(self, find_only_first: bool = False, limit: Optional[int] = None, offset: Optional[int] = None, **filters) -> DatabaseReport`

* `async def update_records_in_shareholders(self, updates: dict, **filters) -> DatabaseReport`

* `async def delete_records_from_shareholders(self, delete_only_first: bool = False, **filters) -> DatabaseReport`




5.3 DAL Method Signatures: External Intelligence & Macro Data

* Table `web_reputation`:


* `async def add_record_to_web_reputation(self, business_id: UUID, scan_timestamp: datetime, active_lawsuits_count: int = 0, total_lawsuit_claims_amount: Decimal = Decimal('0.00'), is_in_sanctions_list: bool = False, news_sentiment_score: Optional[Decimal] = None, web_traffic_monthly_visits: Optional[int] = None, record_id: Optional[UUID] = None) -> DatabaseReport`

* `async def get_records_from_web_reputation(self, find_only_first: bool = False, limit: Optional[int] = None, offset: Optional[int] = None, **filters) -> DatabaseReport`

* `async def update_records_in_web_reputation(self, updates: dict, **filters) -> DatabaseReport`

* `async def delete_records_from_web_reputation(self, delete_only_first: bool = False, **filters) -> DatabaseReport`



* Table `macro_sector_metrics`:


* `async def add_record_to_macro_sector_metrics(self, industry_code: str, reference_date: date, sector_growth_rate_yoy: Decimal, sector_default_rate: Decimal, risk_outlook_score: int, metric_id: Optional[UUID] = None) -> DatabaseReport`

* `async def get_records_from_macro_sector_metrics(self, find_only_first: bool = False, limit: Optional[int] = None, offset: Optional[int] = None, **filters) -> DatabaseReport`

* `async def update_records_in_macro_sector_metrics(self, updates: dict, **filters) -> DatabaseReport`

* `async def delete_records_from_macro_sector_metrics(self, delete_only_first: bool = False, **filters) -> DatabaseReport`




5.4 DAL Method Signatures: Commercial Graph & Cash Flow Ledger

* Table `counterparties`:


* `async def add_record_to_counterparties(self, business_id: UUID, legal_name: str, counterparty_role: str, tax_id: Optional[str] = None, counterparty_id: Optional[UUID] = None) -> DatabaseReport`

* `async def get_records_from_counterparties(self, find_only_first: bool = False, limit: Optional[int] = None, offset: Optional[int] = None, **filters) -> DatabaseReport`

* `async def update_records_in_counterparties(self, updates: dict, **filters) -> DatabaseReport`

* `async def delete_records_from_counterparties(self, delete_only_first: bool = False, **filters) -> DatabaseReport`



* Table `invoices`:


* `async def add_record_to_invoices(self, business_id: UUID, counterparty_id: UUID, invoice_type: str, gross_amount: Decimal, issue_date: date, due_date: date, status: str, actual_payment_date: Optional[date] = None, invoice_id: Optional[UUID] = None) -> DatabaseReport`

* `async def get_records_from_invoices(self, find_only_first: bool = False, limit: Optional[int] = None, offset: Optional[int] = None, **filters) -> DatabaseReport`

* `async def update_records_in_invoices(self, updates: dict, **filters) -> DatabaseReport`

* `async def delete_records_from_invoices(self, delete_only_first: bool = False, **filters) -> DatabaseReport`



* Table `bank_accounts`:


* `async def add_record_to_bank_accounts(self, business_id: UUID, currency: str, current_balance: Decimal, overdraft_limit: Decimal = Decimal('0.00'), account_id: Optional[UUID] = None) -> DatabaseReport`

* `async def get_records_from_bank_accounts(self, find_only_first: bool = False, limit: Optional[int] = None, offset: Optional[int] = None, **filters) -> DatabaseReport`

* `async def update_records_in_bank_accounts(self, updates: dict, **filters) -> DatabaseReport`

* `async def delete_records_from_bank_accounts(self, delete_only_first: bool = False, **filters) -> DatabaseReport`



* Table `transactions`:


* `async def add_record_to_transactions(self, business_id: UUID, account_id: UUID, timestamp: datetime, amount: Decimal, direction: str, category: str, liquidity_class: str, counterparty_id: Optional[UUID] = None, invoice_id: Optional[UUID] = None, transaction_id: Optional[UUID] = None) -> DatabaseReport`

* `async def get_records_from_transactions(self, find_only_first: bool = False, limit: Optional[int] = None, offset: Optional[int] = None, **filters) -> DatabaseReport`

* `async def update_records_in_transactions(self, updates: dict, **filters) -> DatabaseReport`

* `async def delete_records_from_transactions(self, delete_only_first: bool = False, **filters) -> DatabaseReport`




5.5 DAL Method Signatures: Liabilities & Debt Facilities

* Table `credit_obligations`:


* `async def add_record_to_credit_obligations(self, business_id: UUID, lender_name: str, facility_type: str, principal_amount: Decimal, outstanding_balance: Decimal, monthly_payment: Decimal, past_due_30d_count: int = 0, past_due_90d_count: int = 0, historical_defaults_count: int = 0, obligation_id: Optional[UUID] = None) -> DatabaseReport`

* `async def get_records_from_credit_obligations(self, find_only_first: bool = False, limit: Optional[int] = None, offset: Optional[int] = None, **filters) -> DatabaseReport`

* `async def update_records_in_credit_obligations(self, updates: dict, **filters) -> DatabaseReport`

* `async def delete_records_from_credit_obligations(self, delete_only_first: bool = False, **filters) -> DatabaseReport`




5.6 DAL Method Signatures: UI State & Execution Telemetry

* Table `users`:


* `async def add_record_to_users(self, email: str, password_hash: str, full_name: str, role: str = 'ANALYST', is_active: bool = True, user_id: Optional[UUID] = None) -> DatabaseReport`

* `async def get_records_from_users(self, find_only_first: bool = False, limit: Optional[int] = None, offset: Optional[int] = None, **filters) -> DatabaseReport`

* `async def update_records_in_users(self, updates: dict, **filters) -> DatabaseReport`

* `async def delete_records_from_users(self, delete_only_first: bool = False, **filters) -> DatabaseReport`



* Table `user_settings`:


* `async def add_record_to_user_settings(self, user_id: UUID, ui_theme: str = 'system', terminal_sound_effects: bool = False, auto_expand_reports: bool = True, setting_id: Optional[UUID] = None) -> DatabaseReport`

* `async def get_records_from_user_settings(self, find_only_first: bool = False, limit: Optional[int] = None, offset: Optional[int] = None, **filters) -> DatabaseReport`

* `async def update_records_in_user_settings(self, updates: dict, **filters) -> DatabaseReport`

* `async def delete_records_from_user_settings(self, delete_only_first: bool = False, **filters) -> DatabaseReport`



* Table `analysis_runs`:


* `async def add_record_to_analysis_runs(self, user_id: UUID, input_company_name: str, input_tax_id: str, input_industry_code: str, files_manifest: dict, active_submodules: list, status: str = 'QUEUED', business_id: Optional[UUID] = None, run_id: Optional[UUID] = None) -> DatabaseReport`

* `async def get_records_from_analysis_runs(self, find_only_first: bool = False, limit: Optional[int] = None, offset: Optional[int] = None, **filters) -> DatabaseReport`

* `async def update_records_in_analysis_runs(self, updates: dict, **filters) -> DatabaseReport`

* `async def delete_records_from_analysis_runs(self, delete_only_first: bool = False, **filters) -> DatabaseReport`



* Table `analysis_logs`:


* `async def add_record_to_analysis_logs(self, run_id: UUID, severity: str, stage: str, message: str, log_id: Optional[int] = None) -> DatabaseReport`

* `async def get_records_from_analysis_logs(self, find_only_first: bool = False, limit: Optional[int] = None, offset: Optional[int] = None, **filters) -> DatabaseReport`

* `async def update_records_in_analysis_logs(self, updates: dict, **filters) -> DatabaseReport`

* `async def delete_records_from_analysis_logs(self, delete_only_first: bool = False, **filters) -> DatabaseReport`




5.7 Bulk Insertion Extensions
To support high-velocity CSV ingestion into `transactions` and `invoices` without
per-row network roundtrips:

* `async def bulk_insert_transactions(self, records: List[dict]) -> DatabaseReport`
* `async def bulk_insert_invoices(self, records: List[dict]) -> DatabaseReport`
Uses `cursor.copy()` or `execute_values()` via binary protocols, scaling ingestion
to over 50,000 rows per second.

6. CONCURRENCY, TRANSACTIONS & PERFORMANCE

---

6.1 Isolation Levels
Default isolation level is `READ COMMITTED`, eliminating dirty reads while preventing
serialization bottlenecks during parallel analysis submodule executions.
Critical analytical rollups utilize `REPEATABLE READ` if point-in-time cross-table
auditing is mandated.

6.2 Foreign Key Indexing & Query Acceleration
To avoid sequential scans during analytical submodule joins, standard indexes are
established on all Foreign Key and temporal filter columns:

```sql
CREATE INDEX idx_trans_biz_time ON transactions (business_id, timestamp DESC);
CREATE INDEX idx_invoices_biz_status ON invoices (business_id, status);
CREATE INDEX idx_logs_run_seq ON analysis_logs (run_id, timestamp ASC);
CREATE INDEX idx_runs_user_date ON analysis_runs (user_id, created_at DESC);

```

6.3 Connection Pool Sizing Equation
Pool size is calibrated against the maximum worker threads in Uvicorn:
`Pool_Max_Size = (Uvicorn_Workers * Concurrent_Coroutines_Per_Worker) + Background_Workers`
Nominal setting: 20 pooled connections per backend container instance.

7. SECURITY, SANITIZATION & HARDENING

---

7.1 SQL Injection Neutralization
All queries employ parameterized placeholders:

```python
# CORRECT & SECURE:
query = sql.SQL("SELECT * FROM {table} WHERE {col} = %s").format(
    table=sql.Identifier("businesses"),
    col=sql.Identifier("tax_id")
)
await cursor.execute(query, [sanitized_tax_id])

```

Direct value interpolation using python string formatting (`%`, `.format()`, or `f""`)
within SQL statements is strictly prohibited and flagged as a fatal error in code review.

7.2 Privilege Separation & Role Hardening
The database enforces three distinct PostgreSQL user roles:

* `app_migration_user`: DDL permissions (CREATE, ALTER, DROP) used exclusively by Alembic.
* `app_runtime_user`: DML permissions (SELECT, INSERT, UPDATE, DELETE) for the FastAPI
backend and analytical workers.
* `readonly_analyst`: SELECT-only permissions on reporting views.

7.3 Encryption & Transport Security
All database communication enforces TLS 1.3 encryption (`sslmode=verify-full`).
Authentication secrets and API keys are read from environment variables; password
hashes in the `users` table are salted using Argon2id.

8. TESTING & MOCK IMPLEMENTATION STUB

---

To support isolated testing of the Web and Analytical modules when PostgreSQL is
offline, a drop-in in-memory Mock DAL (`MockDatabase`) is provided.

```python
class MockDatabase:
    """
    In-memory mock reproducing the Database interface for offline unit testing.
    """
    def __init__(self):
        self._storage: dict[str, list[dict]] = {
            "businesses": [],
            "shareholders": [],
            "invoices": [],
            "transactions": [],
            "bank_accounts": [],
            "credit_obligations": [],
            "users": [],
            "analysis_runs": [],
            "analysis_logs": []
        }

    async def add_record_to_businesses(self, **kwargs) -> DatabaseReport:
        record = dict(kwargs)
        if "business_id" not in record or record["business_id"] is None:
            record["business_id"] = uuid4()
        self._storage["businesses"].append(record)
        return DatabaseReport(success=True, data=record, affected_rows=1)

    async def get_records_from_businesses(self, find_only_first: bool = False, **filters) -> DatabaseReport:
        results = [
            row for row in self._storage["businesses"]
            if all(row.get(k) == v for k, v in filters.items() if v is not None)
        ]
        if find_only_first:
            return DatabaseReport(success=True, data=results[0] if results else None, affected_rows=int(bool(results)))
        return DatabaseReport(success=True, data=results, affected_rows=len(results))

    async def update_records_in_businesses(self, updates: dict, **filters) -> DatabaseReport:
        affected = 0
        for row in self._storage["businesses"]:
            if all(row.get(k) == v for k, v in filters.items() if v is not None):
                row.update(updates)
                affected += 1
        return DatabaseReport(success=True, affected_rows=affected)

    async def delete_records_from_businesses(self, delete_only_first: bool = False, **filters) -> DatabaseReport:
        initial_len = len(self._storage["businesses"])
        self._storage["businesses"] = [
            row for row in self._storage["businesses"]
            if not all(row.get(k) == v for k, v in filters.items() if v is not None)
        ]
        return DatabaseReport(success=True, affected_rows=initial_len - len(self._storage["businesses"]))

```

# ================================================================================
END OF SPECIFICATION

```

```
