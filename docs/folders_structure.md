================================================================================
GRAEAEEYE (SMART CREDIT & CASH FLOW NAVIGATOR)
TECHNICAL ARCHITECTURE & DEVELOPER SPECIFICATION DOCUMENT
================================================================================

TABLE OF CONTENTS
================================================================================
SECTION 0: HIGH-LEVEL OVERVIEW & FOLDER STRUCTURE PHILOSOPHY ......... Lines ~10-44
           Human-readable overview of system design and folder philosophy.

SECTION 1: CONCEPT AND ARCHITECTURAL PHILOSOPHY ....................... Lines ~45-160
           Business domain rationale, system mission, and file inventory.

SECTION 2: ARCHITECTURE AND VISUALIZATION ............................. Lines ~161-265
           Layered architecture diagram, cluster components, and roles.

SECTION 3: UNIFIED DATA CONTRACTS ...................................... Lines ~266-345
           Dataclasses, Pydantic schemas, Settings, and operational semantics.

SECTION 4: DESCRIPTION OF MODULES AND THEIR LOCATIONS ................. Lines ~346-375
           Physical filesystem mapping and runtime contexts for each module.

SECTION 5: FAQ - KEY DEVELOPER GUIDANCE (18 HOW-TO ITEMS) ............. Lines ~376-610
           Concise, clustered Q&A with exact code snippets (# CORRECT & SECURE).

SECTION 6: DATA FLOWS AND LIFECYCLE .................................... Lines ~611-645
           Step-by-step file-to-file path from upload to prediction.

SECTION 7: CONFIGS ..................................................... Lines ~646-670
           Environment variables, defaults, and configuration parameter table.

SECTION 8: DEPENDENCIES AND ENVIRONMENT ................................ Lines ~671-695
           Infrastructure requirements, Docker setup, and Python packages.

SECTION 12: USE CASES .................................................. Lines ~696-780
            Happy path ingestion/forecasting and 2 edge-case stress scenarios.
================================================================================


0. HIGH-LEVEL OVERVIEW & FOLDER STRUCTURE PHILOSOPHY
--------------------------------------------------------------------------------
The `src/fintech_app/` directory is structured to reflect a clean, decoupled architecture
separating data intake, relational storage, predictive analytics, and REST API delivery.
By isolating parsing in `ingestion/`, database management in `db/`, Machine Learning algorithms
in `ml/`, and HTTP controllers in `api/`, each feature team can develop independently without
merge conflicts or unexpected side effects. Core configuration and shared data types live
centrally in `core/` and `shared/` to enforce unified system contracts across all modules.
This modular boundary ensures that changes to UI endpoints or machine learning models do
not break database persistence or raw data parsing pipelines.


1. CONCEPT AND ARCHITECTURAL PHILOSOPHY
--------------------------------------------------------------------------------
1.1 Architectural Rationale
GraeaeEye is a specialized financial intelligence platform designed to address the
fundamental Small and Medium Enterprise (SME) paradox: "Profit != Cash". An SME can
be highly profitable on paper (accrual accounting) while simultaneously heading
towards insolvency due to delayed accounts receivable and short-term cash flow gaps.

To solve this challenge, the system architecture is built around three core principles:
1. Domain Decoupling: Data ingestion, data storage, predictive analytics, and REST API
   delivery are decoupled into dedicated directories under `src/fintech_app/`.
2. AI-Driven Ingestion: Bank statements arrive in heterogeneous Excel/CSV formats. The
   ingestion layer uses contextual fuzzy AI mapping to map raw headers to a canonical
   data schema before database persistence.
3. Forward-Looking Early Warning Core: Instead of static historical reporting, the engine
   combines time-series forecasting (Prophet/XGBoost), counterparty behavioral scoring
   (survival analysis/delay probability), and What-If scenario simulations with SHAP
   explainability (XAI).

1.2 System File & Folder Hierarchy (Surface & Role Overview)

Root Directory Level:
- `README.md`: High-level domain context, business scenarios, and hackathon team guidelines.
- `Dockerfile`: Multi-stage OCI container specification based on `python:3.12-slim`.
- `docker-compose.yml`: Multi-container orchestration (PostgreSQL 16 container + Backend API).
- `requirements.txt`: Locked third-party Python package dependencies.
- `pyproject.toml`: Modern Python project build and metadata configuration.
- `.env.example`: Environment variable template for local development and CI/CD.
- `.gitignore`: Version control exclusion rules for Python caches, virtual environments, and storage.

Package Directory (`src/fintech_app/`):
- `src/fintech_app/__init__.py`: Package root marker.
- `src/fintech_app/main.py`: Entry point for the FastAPI ASGI application service.

Core Subsystem (`src/fintech_app/core/`):
- `src/fintech_app/core/__init__.py`: Core package marker.
- `src/fintech_app/core/config.py`: Centralized configuration manager using environment variables.
- `src/fintech_app/core/exceptions.py`: Custom exception class hierarchy (`GraeaeEyeException` root).
- `src/fintech_app/core/logger.py`: Centralized logging setup (`logger` instance with standard output handler).

Database & Relational Model Subsystem (`src/fintech_app/db/`):
- `src/fintech_app/db/__init__.py`: Database package marker.
- `src/fintech_app/db/connection.py`: Database connection pool wrapper (`Database` class via `psycopg_pool.AsyncConnectionPool`).
- `src/fintech_app/db/models.py`: Data record dataclasses (`BusinessRecord`, `ShareholderRecord`, `WebReputationRecord`, `CounterpartyRecord`, `InvoiceRecord`, `TransactionRecord`, `CreditObligationRecord`, `UserRecord`, `AnalysisRunRecord`, `AnalysisLogRecord`) and `DatabaseReport`.

Data Ingestion & Parser Subsystem (`src/fintech_app/ingestion/`):
- `src/fintech_app/ingestion/__init__.py`: Ingestion package marker.
- `src/fintech_app/ingestion/parser.py`: File loader utilities (`BankStatementParser`).
- `src/fintech_app/ingestion/ai_mapper.py`: Contextual column mapping logic (`TransactionCategorizationMapper`).
- `src/fintech_app/ingestion/schemas.py`: Pydantic validation schemas (`ParsedBankStatementPayload`).

Predictive Machine Learning Engine Subsystem (`src/fintech_app/ml/`):
- `src/fintech_app/ml/__init__.py`: ML package marker.
- `src/fintech_app/ml/submodule_ownership.py`: Ownership Structure Evaluator (`OwnershipStructureEvaluator`).
- `src/fintech_app/ml/submodule_reputation.py`: Web Reputation Evaluator (`WebReputationEvaluator`).
- `src/fintech_app/ml/submodule_macro.py`: Macro & Sector Risk Evaluator (`MacroSectorRiskEvaluator`).
- `src/fintech_app/ml/submodule_client_dep.py`: Client Dependency Evaluator (`ClientDependencyEvaluator`).
- `src/fintech_app/ml/submodule_supplier_dep.py`: Supplier Dependency Evaluator (`SupplierDependencyEvaluator`).
- `src/fintech_app/ml/submodule_cash_readiness.py`: Immediate Cash Readiness Evaluator (`ImmediateCashReadinessEvaluator`).
- `src/fintech_app/ml/submodule_cash_stability.py`: Cash Flow Stability Evaluator (`CashflowStabilityEvaluator`).
- `src/fintech_app/ml/submodule_receivables.py`: Receivables Quality Evaluator (`ReceivablesQualityEvaluator`).
- `src/fintech_app/ml/submodule_credit_discipline.py`: Internal Credit Discipline & Leverage Evaluator (`CreditDisciplineLeverageEvaluator`).
- `src/fintech_app/ml/pipeline.py`: Master pipeline orchestrator (`UnderwritingAnalyticalPipeline`).
- `src/fintech_app/ml/scoring.py`: Underwriting credit scoring engine (`CreditScoringEngine`).

API Layer & Endpoints (`src/fintech_app/api/`):
- `src/fintech_app/api/__init__.py`: API package marker.
- `src/fintech_app/api/router.py`: API v1 main router registering endpoint sub-routers.
- `src/fintech_app/api/dependencies.py`: FastAPI dependency injection helpers (`get_db_connection`).
- `src/fintech_app/api/endpoints/__init__.py`: Endpoints package marker.
- `src/fintech_app/api/endpoints/analysis.py`: Session lifecycle endpoints (`/api/v1/analysis/start`, `/stream/{run_id}`, `/report/{run_id}`).

Shared Utilities & Domain Types (`src/fintech_app/shared/`):
- `src/fintech_app/shared/__init__.py`: Shared package marker.
- `src/fintech_app/shared/schemas/__init__.py`: Shared schemas marker.
- `src/fintech_app/shared/schemas/user_types.py`: Domain enums (`CounterpartyRole`, `InvoiceType`, `InvoiceStatus`, `TransactionDirection`, `TransactionCategory`, `LiquidityClass`, `FacilityType`, `AnalysisStatus`, `EvaluationStatus`).
- `src/fintech_app/shared/utils.py`: Common helpers (`format_currency`).


2. ARCHITECTURE AND VISUALIZATION
--------------------------------------------------------------------------------
The system follows a Layered Monolithic Architecture optimized for high developer throughput
and straightforward deployment via Docker Compose.

Component Structural Layout (ASCII View):

+-------------------------------------------------------------------------------+
|                             CLIENT / FRONTEND UI                              |
+-------------------------------------------------------------------------------+
                                      |
                                      v (HTTP / REST API & SSE Streaming)
+-------------------------------------------------------------------------------+
|                             API CONTROLLER LAYER                              |
|   src/fintech_app/main.py  |  src/fintech_app/api/router.py                   |
|   endpoints: POST /analysis/start, GET /analysis/stream, GET /analysis/report     |
+-------------------------------------------------------------------------------+
           |                                     |
           v                                     v
+-----------------------------------+   +---------------------------------------+
|      INGESTION & PARSER LAYER     |   |         ANALYTICAL CORE (9 SUBMODULES)|
|  src/fintech_app/ingestion/       |   |  src/fintech_app/ml/                  |
|  - parser.py (Statement parser)   |   |  - 9 flat submodule evaluators        |
|  - ai_mapper.py (AI column mapper)|   |  - pipeline.py (18D vector pipeline)  |
|  - schemas.py (Pydantic DTOs)     |   |  - scoring.py (Scoring & LLM summary) |
+-----------------------------------+   +---------------------------------------+
           |                                     /
           \                                   /
            \                                 /
             v                               v
+-------------------------------------------------------------------------------+
|                       DATABASE & DATA RELATIONAL GRAPH                        |
|   src/fintech_app/db/connection.py (AsyncConnectionPool wrapper)              |
|   src/fintech_app/db/models.py (BusinessRecord, InvoiceRecord, Transaction)  |
+-------------------------------------------------------------------------------+
                                      |
                                      v
+-------------------------------------------------------------------------------+
|                           POSTGRESQL 16 (DATABASE)                            |
+-------------------------------------------------------------------------------+

2.1 Detailed Component Clusters

Cluster 2.1.1: Core Infrastructure & Operations
- Location: `src/fintech_app/core/`
- Responsibility: Centralizes system initialization, environment variable management,
  logging setup, and application-wide exception handling.
- Key Entities: `Settings` dataclass (`config.py`), `GraeaeEyeException` hierarchy (`exceptions.py`),
  `logger` (`logger.py`).

Cluster 2.1.2: Relational Data Graph & Storage
- Location: `src/fintech_app/db/`
- Responsibility: Controls asynchronous SQL execution via `psycopg_pool.AsyncConnectionPool`,
  connection lifecycle, and defines table dataclasses.
- Key Entities: `Database` (`connection.py`), `DatabaseReport`, `BusinessRecord`,
  `ShareholderRecord`, `CounterpartyRecord`, `InvoiceRecord`, `TransactionRecord`,
  `CreditObligationRecord`, `AnalysisRunRecord`, `AnalysisLogRecord` (`models.py`).

Cluster 2.1.3: Intelligent Data Ingestion
- Location: `src/fintech_app/ingestion/`
- Responsibility: Ingests unstructured CSV/Excel bank statements, uses fuzzy string matching
  to normalize column headers, and validates records before DB write.
- Key Entities: `BankStatementParser` (`parser.py`), `TransactionCategorizationMapper` (`ai_mapper.py`),
  `ParsedBankStatementPayload` (`schemas.py`).

Cluster 2.1.4: Core Analytical Submodule Engine
- Location: `src/fintech_app/ml/`
- Responsibility: Runs 9 autonomous submodules, aggregates the 18-element feature vector,
  calculates credit score, and synthesizes LLM reports.
- Key Entities: 9 Submodule Evaluators (`submodule_*.py`), `UnderwritingAnalyticalPipeline` (`pipeline.py`),
  `CreditScoringEngine` (`scoring.py`).

Cluster 2.1.5: REST API Controller & Service Layer
- Location: `src/fintech_app/api/` & `src/fintech_app/main.py`
- Responsibility: Exposes FastAPI endpoints for external web consumption, handles request
  validation, triggers background execution, and streams real-time SSE logs.
- Key Entities: `app` (`main.py`), `api_router` (`router.py`), `get_db_connection` (`dependencies.py`),
  analysis session handlers (`analysis.py`).

Cluster 2.1.6: Shared Domain Utilities & Enums
- Location: `src/fintech_app/shared/`
- Responsibility: Provides reusable enumeration types and formatting helper functions.
- Key Entities: `CounterpartyRole`, `InvoiceType`, `InvoiceStatus`, `TransactionDirection`,
  `TransactionCategory`, `LiquidityClass`, `FacilityType`, `AnalysisStatus`, `EvaluationStatus`
  (`shared/schemas/user_types.py`).


3. UNIFIED DATA CONTRACTS
--------------------------------------------------------------------------------
This section documents the primary data structures that act as contracts across modules.

3.1 Database Operation Contract (`DatabaseReport`)
Defined in: `src/fintech_app/db/models.py`

Code Definition:
```python
from dataclasses import dataclass
from typing import Optional, Union, List

@dataclass(frozen=True)
class DatabaseReport:
    """Standardized result contract for all Database operations."""
    success: bool
    data: Optional[Union[List[dict], dict]] = None
    affected_rows: int = 0
    error: Optional[str] = None
    operation: Optional[str] = None
    table_name: Optional[str] = None
```

3.1.1 Operational Semantics:
- `success`: `True` if query/transaction completed cleanly without database errors; `False` on exception or constraint violation.
- `data`: On `success` with query results, contains a `dict` (single row) or `List[dict]` (multiple rows). On `error` or non-SELECT operations, set to `None`.
- `affected_rows`: Integer count of rows inserted, updated, deleted, or retrieved. `0` if no rows affected or on error.
- `error`: `None` on success. On failure, contains descriptive string detailing the SQL error or exception traceback.
- `operation`: String tag denoting query type (e.g., `'INSERT'`, `'UPDATE'`, `'SELECT'`, `'DELETE'`). `None` if unassigned.
- `table_name`: Target database table name (e.g., `'transactions'`, `'businesses'`). `None` if unassigned.

3.2 Ingestion Data Validation Contract (`RawBankStatementLine`)
Defined in: `src/fintech_app/ingestion/schemas.py`

Code Definition:
```python
from datetime import date
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, Field

class RawBankStatementLine(BaseModel):
    date: date
    amount: Decimal
    direction: str
    description: str = Field(default="")
    counterparty_tax_id: Optional[str] = None
    account_number: str
    currency: str = Field(default="MDL")
```

3.2.1 Operational Semantics:
- `date`: Required `date` object representing payment date.
- `amount`: Required `Decimal` monetary value (fixed point 18,2).
- `direction`: Required string indicating `INFLOW` or `OUTFLOW`.
- `counterparty_tax_id`: Optional string representing National Tax Identification Number (tax_id). Set to `None` if omitted.
- `description`: String payment memo. Defaults to `""` if not provided in statement.

3.3 Core Configuration Contract (`Settings`)
Defined in: `src/fintech_app/core/config.py`

Code Definition:
```python
from dataclasses import dataclass
import os

@dataclass
class Settings:
    app_env: str = os.getenv("APP_ENV", "development")
    log_level: str = os.getenv("LOG_LEVEL", "INFO")

    postgres_server: str = os.getenv("POSTGRES_SERVER", "localhost")
    postgres_port: int = int(os.getenv("POSTGRES_PORT", "5432"))
    postgres_user: str = os.getenv("POSTGRES_USER", "postgres")
    postgres_password: str = os.getenv("POSTGRES_PASSWORD", "postgres")
    postgres_db: str = os.getenv("POSTGRES_DB", "graeae_eye_db")

    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")

    @property
    def database_url(self) -> str:
        return f"postgresql://{self.postgres_user}:{self.postgres_password}@{self.postgres_server}:{self.postgres_port}/{self.postgres_db}"
```

3.4 Domain Enums
Defined in: `src/fintech_app/shared/schemas/user_types.py`

Code Definition:
```python
from enum import StrEnum

class CounterpartyRole(StrEnum):
    CLIENT = "CLIENT"
    SUPPLIER = "SUPPLIER"
    MIXED = "MIXED"

class InvoiceType(StrEnum):
    RECEIVABLE = "RECEIVABLE"
    PAYABLE = "PAYABLE"

class InvoiceStatus(StrEnum):
    PAID = "PAID"
    OUTSTANDING = "OUTSTANDING"
    OVERDUE = "OVERDUE"
    DEFAULTED = "DEFAULTED"

class TransactionDirection(StrEnum):
    INFLOW = "INFLOW"
    OUTFLOW = "OUTFLOW"

class TransactionCategory(StrEnum):
    REVENUE = "REVENUE"
    OPERATING_EXPENSE = "OPERATING_EXPENSE"
    PAYROLL = "PAYROLL"
    TAX = "TAX"
    DEBT_SERVICE = "DEBT_SERVICE"
    DIVIDEND = "DIVIDEND"
    OTHER = "OTHER"

class LiquidityClass(StrEnum):
    IMMEDIATE_CASH = "IMMEDIATE_CASH"
    RESTRICTED_ESCROW = "RESTRICTED_ESCROW"
    TERM_DEPOSIT = "TERM_DEPOSIT"

class FacilityType(StrEnum):
    TERM_LOAN = "TERM_LOAN"
    LEASING = "LEASING"
    LINE_OF_CREDIT = "LINE_OF_CREDIT"

class AnalysisStatus(StrEnum):
    QUEUED = "QUEUED"
    PARSING = "PARSING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    DEGRADED = "DEGRADED"

class EvaluationStatus(StrEnum):
    SUCCESS = "SUCCESS"
    DATA_ABSENT = "DATA_ABSENT"
    ERROR = "ERROR"
```


4. DESCRIPTION OF MODULES AND THEIR LOCATIONS
--------------------------------------------------------------------------------
4.1 Frontend & REST API Gateway Layer
- Physical Path: `src/fintech_app/main.py` and `src/fintech_app/api/`
- Operational Context: Runs inside Uvicorn ASGI server process on port 8000. Handles HTTP requests,
  deserializes JSON/multipart payloads, calls internal modules, and formats JSON responses.

4.2 Intelligent Data Ingestion & Parser Module
- Physical Path: `src/fintech_app/ingestion/`
- Operational Context: Stateless utility module invoked by `upload.py` endpoint when bank statements
  are submitted. Converts binary files (`.csv`, `.xlsx`) to DataFrames, applies fuzzy column mapping,
  validates types via Pydantic, and returns normalized transaction dictionaries.

4.3 Relational Database & Entity Storage Layer
- Physical Path: `src/fintech_app/db/`
- Operational Context: Interacts directly with PostgreSQL via psycopg/sqlalchemy drivers. Provides entity
  dataclasses and execution context for reading raw financial transactions and persisting client state.

4.4 Predictive Machine Learning Engine
- Physical Path: `src/fintech_app/ml/`
- Operational Context: Invoked by forecast and scenario endpoints. Consumes normalized transactions from
  database models, builds time-series models, computes delay probabilities, and simulates stress tests.

4.5 Infrastructure & Shared Utilities
- Physical Path: `src/fintech_app/core/` and `src/fintech_app/shared/`
- Operational Context: Loaded at application startup. Configures global logging, settings, exception
  handling, domain enums, and utility functions across all subsystems.


5. FAQ - KEY DEVELOPER GUIDANCE (HOW-TO INTERACTION GUIDE)
--------------------------------------------------------------------------------

CLUSTER 5.1: DATABASE & RELATIONAL STORAGE LAYER (`src/fintech_app/db/`)

Q1: How do I persist normalized transactions and handle query results via `DatabaseReport`?
- Target Files: `src/fintech_app/db/connection.py`, `src/fintech_app/db/models.py`
- Key Entities: `Database`, `DatabaseReport`, `TransactionRecord`
- Workflow: Execute parameterized SQL with `db.cursor`, commit on success, and return a `DatabaseReport` contract.
```python
# CORRECT & SECURE
async def save_transaction(db: Database, business_id: UUID, account_id: UUID, amount: Decimal, tx_date: datetime, desc: str) -> DatabaseReport:
    try:
        query = sql.SQL(
            "INSERT INTO transactions (business_id, account_id, amount, timestamp, category) "
            "VALUES (%s, %s, %s, %s, %s) RETURNING transaction_id;"
        )
        report = await db.execute_query(query, [business_id, account_id, amount, tx_date, desc])
        return report
    except Exception as err:
        return DatabaseReport(success=False, error=str(err), operation="INSERT", table_name="transactions")
```

Q2: How do I execute atomic multi-entity SQL transactions with rollback on failure?
- Target Files: `src/fintech_app/db/connection.py`, `src/fintech_app/db/models.py`
- Key Entities: `Database.connection`, `DatabaseReport`
- Workflow: Group multiple `execute()` calls under an `async with conn.transaction():` block.
```python
# CORRECT & SECURE
async def create_business_with_account(db: Database, legal_name: str, tax_id: str, currency: str) -> DatabaseReport:
    try:
        async with db.pool.connection() as conn:
            async with conn.transaction():
                cur = conn.cursor()
                await cur.execute(
                    "INSERT INTO businesses (legal_name, tax_id) VALUES (%s, %s) RETURNING business_id;",
                    (legal_name, tax_id)
                )
                b_id = (await cur.fetchone())[0]
                await cur.execute(
                    "INSERT INTO bank_accounts (business_id, currency, current_balance) VALUES (%s, %s, 0.00);",
                    (b_id, currency)
                )
                return DatabaseReport(success=True, data={"business_id": b_id}, affected_rows=2, operation="INSERT")
    except Exception as err:
        return DatabaseReport(success=False, error=str(err))
```

Q3: Where and how do I register a new relational data model?
- Target Files: `src/fintech_app/db/models.py`
- Key Entities: `@dataclass`
- Workflow: Add a strongly-typed Python dataclass matching the PostgreSQL table schema.
```python
# CORRECT & SECURE
from dataclasses import dataclass, field
from decimal import Decimal
from uuid import UUID, uuid4

@dataclass
class InvoiceRecord:
    business_id: UUID
    counterparty_id: UUID
    invoice_type: InvoiceType
    gross_amount: Decimal
    issue_date: date
    due_date: date
    status: InvoiceStatus
    invoice_id: UUID = field(default_factory=uuid4)
```

Q4: How do I guarantee database connection cleanup in HTTP request contexts?
- Target Files: `src/fintech_app/db/connection.py`, `src/fintech_app/api/dependencies.py`
- Key Entities: `Database`, `get_db_connection()`
- Workflow: Use Python generator `yield` in FastAPI dependencies to release pooled connections.
```python
# CORRECT & SECURE
async def get_db_connection():
    db = Database.get_instance()
    try:
        yield db
    finally:
        pass  # Pooled connections are automatically recycled by psycopg_pool
```

--------------------------------------------------------------------------------

CLUSTER 5.2: DATA INGESTION & PARSER SUBSYSTEM (`src/fintech_app/ingestion/`)

Q5: How do I add support for a new file format (e.g., `.json` or `.pdf`)?
- Target Files: `src/fintech_app/ingestion/parser.py`
- Key Entities: `BankStatementParser`
- Workflow: Add format extension parsing methods in `BankStatementParser`.
```python
# CORRECT & SECURE
class BankStatementParser:
    def parse_pdf(self, file_content: bytes, account_id: UUID, business_id: UUID) -> ParsedBankStatementPayload:
        # Extract tables from PDF bytes and construct payload DTO
        pass
```

Q6: How do I extend AI column mapping rules for custom bank headers?
- Target Files: `src/fintech_app/ingestion/ai_mapper.py`
- Key Entities: `TransactionCategorizationMapper`
- Workflow: Add keyword matching or LLM mapping logic inside `TransactionCategorizationMapper`.
```python
# CORRECT & SECURE
def map_header_to_field(header: str) -> str:
    low = header.lower()
    if any(k in low for k in ["сумма", "amount", "val"]): return "amount"
    if any(k in low for k in ["дата", "date"]): return "date"
    if any(k in low for k in ["инн", "tax_id"]): return "counterparty_tax_id"
    return "description"
```

Q7: How do I add new required or optional fields to the statement validation schema?
- Target Files: `src/fintech_app/ingestion/schemas.py`
- Key Entities: `RawBankStatementLine`
- Workflow: Add Pydantic field annotations with type constraints and default values.
```python
# CORRECT & SECURE
from pydantic import BaseModel, Field
from decimal import Decimal
from typing import Optional
from datetime import date

class RawBankStatementLine(BaseModel):
    date: date
    amount: Decimal
    direction: str
    currency: str = Field(default="MDL")
    description: str = Field(default="")
    counterparty_tax_id: Optional[str] = None
```

Q8: How do I handle unparseable or corrupted statement headers with `ParsingError`?
- Target Files: `src/fintech_app/ingestion/ai_mapper.py`, `src/fintech_app/core/exceptions.py`
- Key Entities: `ParsingError`
- Workflow: Raise `ParsingError` when essential target fields (`amount` or `date`) cannot be identified.
```python
# CORRECT & SECURE
from src.fintech_app.core.exceptions import ParsingError

def validate_mapping(mapped_fields: set) -> None:
    if "amount" not in mapped_fields or "date" not in mapped_fields:
        raise ParsingError("Statement missing required columns: 'amount' and 'date'.")
```

--------------------------------------------------------------------------------

CLUSTER 5.3: CORE ANALYTICAL SUBMODULE ENGINE (`src/fintech_app/ml/`)

Q9: How do I implement a new autonomous submodule evaluator?
- Target Files: `src/fintech_app/ml/submodule_*.py`
- Key Entities: `SubmoduleResult`, `EvaluationStatus`
- Workflow: Create evaluator class receiving `CompanyDataSnapshot` and returning `SubmoduleResult`.
```python
# CORRECT & SECURE
class CustomEvaluator:
    def __init__(self) -> None:
        self.code = "CUSTOM"
        self.impact_weight = 0.10

    def evaluate(self, snapshot: CompanyDataSnapshot) -> SubmoduleResult:
        if not snapshot.bank_accounts:
            return SubmoduleResult(
                submodule_code=self.code,
                status=EvaluationStatus.DATA_ABSENT,
                impact_weight=self.impact_weight,
                verdict="DATA_ABSENT",
                indices={"Custom_Index": None},
                summary="Data absent.",
                diagnostic_report="[CUSTOM SUBMODULE] STATUS: DATA_ABSENT"
            )
        return SubmoduleResult(
            submodule_code=self.code,
            status=EvaluationStatus.SUCCESS,
            impact_weight=self.impact_weight,
            verdict="NOMINAL",
            indices={"Custom_Index": 85.0},
            summary="Evaluation successful.",
            diagnostic_report="[CUSTOM SUBMODULE] VERDICT: NOMINAL"
        )
```

Q10: How do I run the full 9-submodule pipeline and retrieve the 18-element feature vector?
- Target Files: `src/fintech_app/ml/pipeline.py`
- Key Entities: `UnderwritingAnalyticalPipeline`, `UnderwritingPipelineResult`
- Workflow: Instantiate `UnderwritingAnalyticalPipeline` and call `run_analysis(snapshot)`.
```python
# CORRECT & SECURE
pipeline = UnderwritingAnalyticalPipeline()
pipeline_result = pipeline.run_analysis(snapshot)
vector_18d = pipeline_result.feature_vector  # 18-element numerical feature vector
```

Q11: How do I compute the overall credit score and verdict from the feature vector?
- Target Files: `src/fintech_app/ml/scoring.py`
- Key Entities: `CreditScoringEngine`, `CreditScoringResult`
- Workflow: Call `CreditScoringEngine().calculate_score(vector_18d, dossier_text)`.
```python
# CORRECT & SECURE
scoring_engine = CreditScoringEngine()
scoring_result = scoring_engine.calculate_score(feature_vector, compiled_dossier_text)
score = scoring_result.investment_attractiveness_score  # 0.0 to 100.0
```

Q12: How should ML submodules handle missing data or unprovided entity files?
- Target Files: `src/fintech_app/ml/submodule_*.py`
- Key Entities: `EvaluationStatus.DATA_ABSENT`
- Workflow: Return `SubmoduleResult` with status `DATA_ABSENT`, verdict `BYPASSED`, and numerical indices set to `None`.
```python
# CORRECT & SECURE
if not snapshot.credit_obligations:
    return SubmoduleResult(
        submodule_code="ICDL",
        status=EvaluationStatus.DATA_ABSENT,
        impact_weight=0.16,
        verdict="DATA_ABSENT",
        indices={"Debt_Repayment_Discipline_Index": None},
        summary="No credit obligation records provided.",
        diagnostic_report="[SUBMODULE 4.9] STATUS: DATA_ABSENT"
    )
```

--------------------------------------------------------------------------------

CLUSTER 5.4: REST API & SESSION ORCHESTRATION (`src/fintech_app/api/` & `main.py`)

Q13: How do I register session execution endpoints in `api_router`?
- Target Files: `src/fintech_app/api/endpoints/analysis.py`, `src/fintech_app/api/router.py`
- Key Entities: `APIRouter()`
- Workflow: Register routes for `/api/v1/analysis/start`, `/api/v1/analysis/stream/{run_id}`, and `/api/v1/analysis/report/{run_id}`.
```python
# CORRECT & SECURE
from fastapi import APIRouter

api_router = APIRouter(prefix="/api/v1")
# Includes analysis start, stream (SSE), and report endpoints
```

Q14: How do I stream real-time execution logs to the frontend using Server-Sent Events (SSE)?
- Target Files: `src/fintech_app/api/endpoints/analysis.py`
- Key Entities: `StreamingResponse`
- Workflow: Return `StreamingResponse(event_generator(), media_type="text/event-stream")`.
```python
# CORRECT & SECURE
from fastapi.responses import StreamingResponse

@router.get("/analysis/stream/{run_id}")
async def stream_analysis_logs(run_id: UUID):
    return StreamingResponse(event_generator(run_id), media_type="text/event-stream")
```

Q15: How do I catch `GraeaeEyeException` and return standardized HTTP error responses?
- Target Files: `src/fintech_app/core/exceptions.py`, `src/fintech_app/main.py`
- Key Entities: `app.add_exception_handler()`, `GraeaeEyeException`
- Workflow: Register custom exception handler on `FastAPI` app instance in `main.py`.
```python
# CORRECT & SECURE
from fastapi import Request
from fastapi.responses import JSONResponse
from src.fintech_app.core.exceptions import GraeaeEyeException

@app.exception_handler(GraeaeEyeException)
async def graeae_exception_handler(request: Request, exc: GraeaeEyeException):
    return JSONResponse(status_code=400, content={"status": "error", "message": str(exc)})
```

--------------------------------------------------------------------------------

CLUSTER 5.5: INFRASTRUCTURE, CONFIGS & ENUMS (`src/fintech_app/core/` & `shared/`)

Q16: How do I register a new environment configuration parameter?
- Target Files: `src/fintech_app/core/config.py`, `.env.example`
- Key Entities: `Settings`
- Workflow: Add field to `Settings` dataclass in `config.py` and document variable in `.env.example`.
```python
# CORRECT & SECURE
from dataclasses import dataclass
import os

@dataclass
class Settings:
    app_env: str = os.getenv("APP_ENV", "development")
    db_timeout: int = int(os.getenv("DB_TIMEOUT", "30"))

settings = Settings()
```

Q17: How do I extend domain enums like `AnalysisStatus` or `FacilityType`?
- Target Files: `src/fintech_app/shared/schemas/user_types.py`
- Key Entities: `AnalysisStatus`, `FacilityType`
- Workflow: Add enum member string definitions inheriting from `StrEnum`.
```python
# CORRECT & SECURE
from enum import StrEnum

class AnalysisStatus(StrEnum):
    QUEUED = "QUEUED"
    PARSING = "PARSING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    DEGRADED = "DEGRADED"
```

Q18: How do I log module diagnostics using centralized `logger`?
- Target Files: `src/fintech_app/core/logger.py`
- Key Entities: `logger`
- Workflow: Import `logger` from `src.fintech_app.core.logger` and call standard logging methods.
```python
# CORRECT & SECURE
from src.fintech_app.core.logger import logger

def process_data(run_id: UUID):
    logger.info(f"Processing analysis run_id={run_id}")
```


6. DATA FLOWS AND LIFECYCLE
--------------------------------------------------------------------------------
6.1 End-to-End Data Processing Pipeline

Step 1: Enterprise Setup & File Intake
- Client submits company metadata and multipart CSV files to `POST /api/v1/analysis/start`.
- Creates record in `analysis_runs` with status `QUEUED` and returns `{ "run_id": "UUID" }`.

Step 2: Asynchronous Data Ingestion & Graph Creation
- Background worker sets run status to `PARSING`.
- CSV files are loaded by `BankStatementParser`, validated by Pydantic schemas, and inserted into PostgreSQL via `Database` methods (`businesses`, `counterparties`, `invoices`, `transactions`, `bank_accounts`, `credit_obligations`).

Step 3: Real-Time Telemetry & Log Streaming
- Browser connects to `GET /api/v1/analysis/stream/{run_id}`.
- Telemetry events emitted during parsing and submodule execution are written to `analysis_logs` and streamed to the client console via Server-Sent Events (SSE).

Step 4: Analytical Core Evaluation (9 Submodules)
- Worker constructs `CompanyDataSnapshot` for the business entity.
- `UnderwritingAnalyticalPipeline` invokes all 9 submodules concurrently.
- Produces the 18-element feature vector and plain-text diagnostic section reports.

Step 5: Scoring, LLM Synthesis & Report Generation
- `CreditScoringEngine` computes overall Investment Attractiveness Score (0-100) and probability of default.
- LLM synthesizes submodule reports into executive summary narrative.
- Final output payload is persisted into `analysis_runs` and run status marked as `COMPLETED`.

Step 6: Underwriting Report Retrieval
- Browser transitions to report viewer and fetches `GET /api/v1/analysis/report/{run_id}` to render radial gauge, 18 feature indices, 9 submodule cards, and LLM summary.


7. CONFIGS
--------------------------------------------------------------------------------
All configuration properties are loaded dynamically from environment variables or a `.env` file via `src/fintech_app/core/config.py`.

Configuration Property Reference:

+--------------------+----------------+-------------------+---------------------------------------------------------+
| Variable Name      | Type           | Default Value     | Description & Purpose                                   |
+--------------------+----------------+-------------------+---------------------------------------------------------+
| APP_ENV            | String         | "development"     | Execution environment ("development", "production").    |
| LOG_LEVEL          | String         | "INFO"            | Logging verbosity ("DEBUG", "INFO", "WARNING", "ERROR").|
| POSTGRES_SERVER    | String         | "localhost"       | Database host address ("db" inside Docker Compose).     |
| POSTGRES_PORT      | Integer        | 5432              | PostgreSQL service port.                                |
| POSTGRES_USER      | String         | "postgres"        | Database authentication username.                       |
| POSTGRES_PASSWORD  | String         | "postgres"        | Database authentication password.                       |
| POSTGRES_DB        | String         | "graeae_eye_db"   | Target database schema name.                            |
| OPENAI_API_KEY     | String         | ""                | OpenAI API key for LLM narrative synthesis.             |
+--------------------+----------------+-------------------+---------------------------------------------------------+


8. DEPENDENCIES AND ENVIRONMENT
--------------------------------------------------------------------------------
8.1 System & Runtime Requirements
- Operating System: Linux (Ubuntu 22.04 LTS recommended), macOS, or Windows WSL2.
- Runtime Environment: Python 3.12+ (64-bit).
- Database Engine: PostgreSQL 16.x.
- Containerization: Docker 24.0+ and Docker Compose v2+.

8.2 Third-Party Packages & Frameworks (`requirements.txt`)
- Core Web Framework: `fastapi >= 0.110.0`, `uvicorn[standard] >= 0.28.0`, `pydantic >= 2.6.4`, `python-multipart >= 0.0.9`.
- Database Driver & Pool: `psycopg[binary] >= 3.1.18`, `psycopg-pool >= 3.2.1`.
- Data Science & Machine Learning: `pandas >= 2.2.1`, `numpy >= 1.26.4`, `scipy >= 1.12.0`.
- LLM Integration & Middleware: `openai >= 1.14.1`, `ollama >= 0.1.7`.
- Quality & Tooling: `ruff >= 0.3.2`.


12. USE CASES
--------------------------------------------------------------------------------

12.1 Use Case 1: Happy Path - Full Enterprise Analysis & Underwriting Dossier Generation
- Context: An analyst initiates evaluation of an SME by submitting corporate metadata and full CSV package.
- Input Data:
  - Form: `company_name="Agro Solutions SRL"`, `tax_id="1003600045123"`, `industry_code="A.01.11"`
  - Files: `accounts.csv`, `transactions.csv`, `invoices.csv`, `obligations.csv`, `shareholders.csv`
  - Target Endpoint: `POST /api/v1/analysis/start`
- System Execution Flow:
  1. Endpoint validates form and files, inserts record into `analysis_runs`, returns `run_id`.
  2. Client connects to `GET /api/v1/analysis/stream/{run_id}` for SSE telemetry.
  3. Background worker parses files, populates entity graph, and builds `CompanyDataSnapshot`.
  4. `UnderwritingAnalyticalPipeline` executes 9 submodules concurrently and extracts 18-element feature vector.
  5. `CreditScoringEngine` computes score (82.5/100) and synthesizes LLM narrative dossier.
  6. Client fetches `GET /api/v1/analysis/report/{run_id}` to display underwriting dossier.

--------------------------------------------------------------------------------

12.2 Use Case 2: Edge Case - Handling Omitted CSV File with Graceful Submodule Bypass
- Context: Analyst submits enterprise evaluation without `obligations.csv` (Credit obligations history absent).
- Input Data:
  - Form: `company_name="Tech Services SRL"`, `tax_id="1003600099887"`, `industry_code="J.62.01"`
  - Files: `accounts.csv`, `transactions.csv`, `invoices.csv` (omitted `obligations.csv`)
  - Target Endpoint: `POST /api/v1/analysis/start`
- System Execution Flow:
  1. `analysis_runs` created and background pipeline initiated.
  2. Submodules 4.1 through 4.8 execute normally against available records.
  3. Submodule 4.9 (`CreditDisciplineLeverageEvaluator`) detects empty obligations list in `CompanyDataSnapshot`.
  4. Submodule 4.9 returns `SubmoduleResult` with status `DATA_ABSENT`, verdict `BYPASSED`, and null debt indices.
  5. Pipeline compiles vector with null debt features; scoring engine computes score on available indices and notes data omission in report.
- Expected Output Result:
  - Report HTTP 200: Submodule 4.9 rendered as `BYPASSED` card with amber explanation notice.

================================================================================
END OF SPECIFICATION DOCUMENT
================================================================================

