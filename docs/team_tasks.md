# SMART CREDIT SYSTEM: ENGINEERING ROADMAP & DEVELOPER TASK SPECIFICATION (V3.0)
**Confidential & Internal Engineering Governance Document**  
**Target Repository:** `GraeaeEye` (`src/fintech_app/`)  
**Integration Branch:** `dev`  
**Runtime Baseline:** Python 3.12+ | PostgreSQL 16 | FastAPI | psycopg3 (`AsyncConnectionPool`)

---

## 1. EXECUTIVE SUMMARY & ONBOARDING RECAP

### 1.1 The SME Paradox: Why "Profit != Cash" Kills Viable Enterprises
In traditional corporate banking, credit underwriting for Small and Medium Enterprises (SMEs) remains trapped in a retrospective paradigm. Lenders evaluate creditworthiness by reviewing annual accounting balance sheets and tax declarations submitted months after the fiscal period closes. This approach suffers from a fatal structural flaw: **it functions as a rear-view mirror**.

In operational reality, **accounting profit does not equal liquid cash**. An SME can experience explosive top-line revenue growth, close lucrative commercial contracts, and display substantial paper profits on its income statement—yet simultaneously collapse into sudden, catastrophic insolvency. This occurs when incoming payments are deferred by 60 to 90 days (trade credit extended to customers) while unavoidable operational cash outflows (payroll, social contributions, VAT, vendor advances, server infrastructure, and facility rent) must be settled within 5 to 10 days. 

When receivables stall, a profitable business experiences a lethal liquidity shortfall (a "cash crunch"). Traditional bank scoring models only identify this distress after the enterprise has already defaulted on a loan installment. The **Smart Credit System** resolves this paradox by replacing backward-looking balance sheets with a **high-frequency, forward-looking early-warning radar**. By ingesting raw transaction ledgers, commercial invoices, and debt repayment histories, the platform constructs an interconnected corporate financial graph that quantifies cash burn, customer payment slippage, supplier dependency, and hidden liquidity risks weeks before they threaten enterprise survival.

```
                          TRADITIONAL UNDERWRITING vs. SMART CREDIT RADAR
                          
  [ Traditional Banks ] ---> Annual Balance Sheet (Lagging 6-12 Months) ---> Blind to Cash Gaps ---> Default
                                                                                                        ▲
                                                                                                        │
  [ Smart Credit Engine ] -> Ingest Bank & Invoice Ledger (Real-Time)   ---> Graph Analysis  ---> Early Alert
                                                                          (Cash Runway, HHI,       (Weeks Ahead)
                                                                           Slippage, DPD)
```

---

### 1.2 The Platform Architecture at a Glance
The system does not process financial data as disconnected spreadsheets. It operates as an asynchronous, multi-stage intelligence pipeline:
1. **Intake & Ingestion Graph:** Uploaded CSV files (bank statements, commercial receivables/payables, historical loans) are sanitized, categorized, and converted into an entity graph in PostgreSQL 16.
2. **Decoupled 9-Submodule Analytical Core:** Rather than feeding noisy data into an uninterpretable "black box," the analytical engine evaluates the enterprise across **9 autonomous, single-responsibility submodules** spanning Governance, Market Reputation, Counterparty Concentrations, Cash Flow Dynamics, and Credit Discipline.
3. **Dual-Output Mechanism:** Every active submodule emits:
   - A structured, human-readable **diagnostic report** with explicit verdicts and sub-indices.
   - Standardized numerical indices strictly bounded between **0.00 and 100.00**, totaling the canonical **18-dimensional feature vector** (strictly distributed across the 9 submodules as: **2 + 2 + 1 + 2 + 2 + 2 + 2 + 2 + 3 = 18 indices**).
4. **Aggregation & LLM Synthesis:** The resulting **18-dimensional feature vector** feeds downstream scoring logic in `CreditScoringEngine` to produce an investment attractiveness score (0–100), default probabilities, and risk recommendations (`APPROVED`, `MANUAL_REVIEW`, `REJECTED`), while an integrated LLM synthesizes the 9 narrative reports into an executive-level **Underwriting Dossier**.

---

### 1.3 The 4 Golden Rules of Team Engineering
To enable 5 engineers to build this platform concurrently without blocking or code collisions, every contributor must strictly observe four non-negotiable rules:

| Rule | Principle | Operational Mandate |
| :--- | :--- | :--- |
| **Rule 1** | **Never Block a Teammate** | **The Functional Mock Stub Mandate:** If an API endpoint, parser, or database method you depend on is not yet implemented by your colleague, **NEVER raise `NotImplementedError`** and never halt work. Implement a deterministic mock stub returning synthetic, schema-valid data. Downstream code, UI pages, and ingestion pipelines must always run cleanly. |
| **Rule 2** | **Single Source of Truth** | **PostgreSQL via DAL (`db/connection.py`):** Modules do not share loose CSV files, global variables, or in-memory caches. All data writes and reads must pass strictly through asynchronous `Database` class methods returning standardized `DatabaseReport` containers. |
| **Rule 3** | **Continuous Integration** | **Atomic PRs into `dev`:** Never hoard code in personal branches for multiple days. Open small, self-contained, reviewable PRs daily against the `dev` branch. Delayed "big bang" merges are strictly forbidden. |
| **Rule 4** | **Git as Sole Authority** | **Code-First Interfaces:** Never negotiate function signatures, data types, or database schemas via ad-hoc private chat messages. If an interface must change, declare the change in code, push your branch, and open a PR. If it is not in Git, it does not exist. |

---

## 2. SYNCHRONIZATION MILESTONES (3-PHASE TIMELINE)

```
+---------------------------------------------------------------------------------------------------------+
|                                    PLATFORM SYNCHRONIZATION TIMELINE                                     |
+---------------------------------------------------------------------------------------------------------+
| PHASE 1: CONTRACT FREEZING & FUNCTIONAL MOCKS (Days 1 - 2)                                              |
| [Lead Architect] -> DB Schema DDL & Connection Pool Stub (returning valid DatabaseReport)               |
| [Web Backend]   -> FastAPI Skeleton, Session Auth Mock, Pipeline Stubs (/start, /stream, /report)       |
| [Frontend]      -> UI Layout, Tailwind Styles, static/js/mock_service.js (Zero-backend UI preview)      |
| [Ingestion]     -> Pydantic Schemas (Raw/Parsed/Batch), Mock Ingestion Fixtures                         |
| [Analytical]    -> 9 Flat Submodule Skeletons (returning SubmoduleResult with canonical 18D indices)   |
| GATE 1: All modules run independently. Zero syntax errors, zero NotImplementedError exceptions.        |
+---------------------------------------------------------------------------------------------------------+
| PHASE 2: AUTONOMOUS DOMAIN IMPLEMENTATION (Days 3 - 5)                                                  |
| [Lead Architect] -> Full PostgreSQL 16 DDL, async psycopg3 queries, binary bulk streaming, DAL methods |
| [Web Backend]   -> BackgroundTask execution, SSE log broadcaster, Argon2/JWT cookies, LLM synthesis    |
| [Frontend]      -> /docs visual canvas, /analyze/new wizard, /track terminal, /report dossier dashboard |
| [Ingestion]     -> Chunked CSV reading, fuzzy AI column mapper, keyword expense classifier              |
| [Analytical]    -> Concrete math (HHI, Cash Ratio, DCOH, CV, DSCR, OLS trend), 18D vector aggregation   |
| GATE 2: Full functional depth implemented. Unit tests green across isolated subsystems.                |
+---------------------------------------------------------------------------------------------------------+
| PHASE 3: END-TO-END INTEGRATION & VERIFICATION (Days 6 - 7)                                             |
| [Whole Team]    -> Set USE_MOCK_ENGINE=false in .env. Full loop: UI Upload -> Ingestion -> PostgreSQL  |
|                    -> Snapshot Assembly -> 9 Submodules Parallel -> Scoring -> LLM Dossier -> SSE UI.   |
| GATE 3: 100% End-to-End integration pass. Zero float financial fields, zero SQLAlchemy references.     |
+---------------------------------------------------------------------------------------------------------+
```

### Phase 1: Contract Freezing & Functional Mock Stubs (Days 1 – 2)
- **Objective:** Freeze all module boundaries, Pydantic models, and method signatures. Deploy deterministic mock adapters across every layer so that each developer can boot the full system locally on Day 1 without waiting for backend or database code.
- **Exit Criteria (Gate 1):**
  - `python3 -m py_compile src/fintech_app/**/*.py` passes with zero errors.
  - Starting the FastAPI server boots cleanly and serves frontend templates via `/static`.
  - Calling mock endpoints returns schema-valid data matching `docs/architecture-v3.md` and `docs/ui_architecture.md`.

### Phase 2: Autonomous Domain Implementation (Days 3 – 5)
- **Objective:** Replace mock stubs with high-performance production logic: real PostgreSQL DDL/DAL, streaming CSV parsers, algorithmic financial scoring math, SSE logging channels, and responsive UI components.
- **Exit Criteria (Gate 2):**
  - Database schema initializes completely via Docker Compose with all 13 tables and indexes.
  - Submodules 4.1–4.9 calculate mathematically rigorous indices from in-memory snapshots according to canonical formulas.
  - Ingestion transforms sample CSV files into relational records without memory spikes.

### Phase 3: End-to-End Integration & Verification (Days 6 – 7)
- **Objective:** Toggle `USE_MOCK_ENGINE=false` in `.env`. Connect the real PostgreSQL persistence layer, asynchronous background workers, streaming SSE telemetry, and analytical pipeline into a seamless end-to-end workflow.
- **Exit Criteria (Gate 3):**
  - An analyst uploads 5 CSV files via `/analyze/new`; the system parses lines, builds the entity graph, executes 9 submodules concurrently, streams logs to `/analyze/track/{id}`, and renders the complete financial dossier at `/analyze/report/{id}`.
  - Linter gate passes: `ruff check .` and `ruff format .` return zero violations.

---

## 3. GRANULAR DEVELOPER TASK CARDS

```
+----------------------------------------------------------------------------------------------------+
|                                    TEAM OWNERSHIP & SUBSYSTEM MATRIX                                |
+------------------+------------------------------+---------------------------+----------------------+
| Handle           | Engineering Role             | Assigned Git Branch       | Primary Scope        |
+------------------+------------------------------+---------------------------+----------------------+
| @newgopro        | Lead Architect & DevOps      | feature/database-dal      | DB, DAL, Docker, CI  |
| @egordjundiet    | Web Backend & Pipeline Lead  | feature/backend-api       | FastAPI, SSE, Auth   |
| @Xtnray          | Web Frontend & UX Architect  | feature/ui-frontend       | UI, HTML/JS, Canvas  |
| @ozzyrastamouse  | Data Ingestion Specialist    | feature/data-parser       | CSV, AI Mapper, Clean|
| @Mr-Ressentiment | Quantitative & ML Architect  | feature/analytical-core   | 9 Submodules, Scoring|
+------------------+------------------------------+---------------------------+----------------------+
```

---

### 3.1 DEVELOPER CARD: @newgopro
* **Handle:** `@newgopro`
* **Domain Role:** Lead Architect, Database & DevOps
* **Assigned Branch:** `feature/database-dal` (branched off `dev`)

#### High-Level Intuition
You are the foundation of the platform. If the database crashes, corrupts data, or blocks I/O threads, the entire underwriting system grinds to a halt. Your mission is to build an unshakeable, non-blocking PostgreSQL 16 persistence engine. You guarantee that financial data never loses precision (using `DECIMAL(18,2)`), that queries never succumb to SQL injection (using `psycopg.sql`), and that your teammates never experience application crashes by providing both a high-throughput async DAL and an offline-capable `MockDatabase`.

#### Target File Manifest
- `docker-compose.yml` (PostgreSQL 16 container definition)
- `src/fintech_app/db/connection.py` (`Database`, `MockDatabase`, connection pool management)
- `src/fintech_app/db/models.py` (Dataclasses, Enums, `DatabaseReport`, `CompanyDataSnapshot`)
- `src/fintech_app/db/schema.sql` (13-table DDL script with constraints and indexes)
- `src/fintech_app/db/repository.py` (`CompanyEvaluationRepository`)

#### Phased Implementation Tasks

##### Phase 1 Tasks (Contracts & Mocks)
1. **Container Infrastructure:** Configure `docker-compose.yml` defining `postgres:16-alpine` with health checks, persistent volume mapping, and port `5432`.
2. **Unified Data Contract:** Verify and lock `DatabaseReport` dataclass in `src/fintech_app/db/models.py`:
   ```python
   @dataclass(frozen=True)
   class DatabaseReport:
       success: bool
       data: Optional[Union[List[dict], dict]] = None
       affected_rows: int = 0
       error: Optional[str] = None
       operation: Optional[str] = None
       table_name: Optional[str] = None
   ```
3. **Mock DAL Implementation:** In `src/fintech_app/db/connection.py`, construct a fully functional `MockDatabase` class that implements every planned method of `Database` (e.g., `get_business`, `add_transaction`, `bulk_insert_transactions`) returning synthetic, schema-valid `DatabaseReport` objects so teammates can develop without a running PostgreSQL instance.

##### Phase 2 Tasks (Business Logic & High-Performance DAL)
1. **13-Table Relational DDL:** Author `src/fintech_app/db/schema.sql` enforcing RFC-4122 `UUID` primary keys, `DECIMAL(18,2)` for monetary values, foreign key cascades, and high-performance b-tree indexes across all 5 functional clusters:
   - **Cluster 1 (Identity & Cap-Table):** `businesses`, `shareholders`
   - **Cluster 2 (External Intelligence):** `web_reputation`, `macro_sector_metrics`
   - **Cluster 3 (Commercial Graph & Cash Ledger):** `counterparties`, `invoices`, `bank_accounts`, `transactions`
   - **Cluster 4 (Credit & Liabilities):** `credit_obligations`
   - **Cluster 5 (Web & Telemetry):** `users`, `user_settings`, `analysis_runs`, `analysis_logs`
2. **Async Connection Pool Management:** Implement `Database` in `src/fintech_app/db/connection.py`:
   - Initialize `psycopg_pool.AsyncConnectionPool` with `min_size=4`, `max_size=20`, `max_idle=300.0`, and `row_factory=dict_row`.
   - Provide `open()`, `close()`, and `health_check()` coroutines.
   - Enforce context-managed transactions (`async with conn.transaction():`) ensuring atomic rollbacks on error.
3. **Universal Parameterized CRUD:** Implement dynamic query builder methods using `psycopg.sql.SQL`, `Identifier`, and `Placeholder` preventing SQL injection:
   - `async def select_records(self, table_name: str, filters: dict, limit: int = 100) -> DatabaseReport`
   - `async def insert_record(self, table_name: str, payload: dict) -> DatabaseReport`
   - `async def update_records(self, table_name: str, payload: dict, filters: dict) -> DatabaseReport`
4. **Binary Streaming Ingestion Methods:** Implement high-speed bulk ingestion using `psycopg.AsyncCursor.copy()`:
   - `async def bulk_insert_transactions(self, records: List[dict]) -> DatabaseReport`
   - `async def bulk_insert_invoices(self, records: List[dict]) -> DatabaseReport`
5. **Snapshot Extraction Repository:** In `src/fintech_app/db/repository.py`, implement `CompanyEvaluationRepository`:
   ```python
   class CompanyEvaluationRepository:
       def __init__(self, db: Database):
           self.db = db

       async def get_evaluation_snapshot(
           self, 
           business_id: UUID, 
           as_of_date: date
       ) -> CompanyDataSnapshot:
           """Queries all 5 relational clusters and constructs the immutable evaluation snapshot."""
   ```

##### Phase 3 Tasks (Testing & Integration)
1. **Migration Runner:** Create a lightweight database initialization script `src/fintech_app/db/init_db.py` that connects via the pool and executes `schema.sql`.
2. **Load & Stress Testing:** Write an integration benchmark testing insertion of 50,000 transaction records via `bulk_insert_transactions` in under 2.0 seconds.
3. **PR Gatekeeping:** Act as primary code reviewer on all PRs into `dev`, ensuring zero occurrences of `SQLAlchemy` or raw string formatting in SQL statements.

#### Strict Technical Invariants & Rules
- **ZERO `SQLAlchemy`:** Absolute prohibition. Only pure async `psycopg` (v3) and `psycopg-pool`.
- **ZERO String Formatting in SQL:** No Python f-strings or `.format()` for SQL syntax. Use `psycopg.sql`.
- **DECIMAL(18,2) Strictness:** All balances, revenues, loan principals, and invoice sums must be Python `Decimal`.
- **UUID PKs:** Every primary key (except auto-incrementing `analysis_logs.log_id`) must be RFC-4122 `uuid.UUID`.

---

### 3.2 DEVELOPER CARD: @egordjundiet
* **Handle:** `@egordjundiet`
* **Domain Role:** Web Backend & Pipeline Runtime
* **Assigned Branch:** `feature/backend-api` (branched off `dev`)

#### High-Level Intuition
You are the central conductor of the application orchestra. The frontend interacts exclusively with your API, and the analytical engine executes under your supervision. Your mission is to build a robust, secure FastAPI web server that ingests user files, manages background analysis jobs without blocking web workers, streams live telemetry logs down to the browser in real time via Server-Sent Events (SSE), and coordinates the final AI-powered synthesis of the underwriting report. In accordance with our clean directory layout in `docs/folders_structure.md`, background tasks and mock providers live directly inside `src/fintech_app/api/`, invoking `UnderwritingAnalyticalPipeline` and `CreditScoringEngine` straight from `src/fintech_app/ml/`.

#### Target File Manifest
- `src/fintech_app/main.py` (FastAPI initialization, CORS, static mounts)
- `src/fintech_app/api/router.py` (API route aggregator)
- `src/fintech_app/api/dependencies.py` (Database connection & auth dependency injection)
- `src/fintech_app/api/endpoints/auth.py` (Session authentication, Argon2 hashing, JWT in secure cookies)
- `src/fintech_app/api/endpoints/analysis.py` (Session lifecycle: `/start`, `/stream/{id}`, `/report/{id}`, background tasks calling ML/DAL directly)
- `src/fintech_app/api/mock_provider.py` (`MockAnalysisProvider` simulating execution)

#### Phased Implementation Tasks

##### Phase 1 Tasks (Contracts & Mocks)
1. **FastAPI Application Setup:** In `src/fintech_app/main.py`, configure FastAPI with CORS middleware, lifespan events for database pool connection, and mount `/static` for frontend assets.
2. **Contract Route Declarations:** Declare all core endpoints returning mocked Pydantic payloads:
   - `POST /api/v1/auth/login`
   - `POST /api/v1/auth/register`
   - `POST /api/v1/analysis/start`
   - `GET /api/v1/analysis/stream/{run_id}`
   - `GET /api/v1/analysis/report/{run_id}`
   - `GET /api/v1/health`
3. **Backend Mock Provider:** Implement `MockAnalysisProvider` in `src/fintech_app/api/mock_provider.py`. When `USE_MOCK_ENGINE=true` in `.env`, the provider simulates an 8-second realistic pipeline run, emitting synthetic logs every 800ms and producing a complete mock diagnostic dossier matching `docs/ui_architecture.md`.

##### Phase 2 Tasks (Business Logic & Execution Engine)
1. **Cryptographic Authentication:** In `src/fintech_app/api/endpoints/auth.py`:
   - Password hashing and verification using `passlib` with Argon2/bcrypt.
   - Issue signed JWT access tokens stored strictly in HTTP-only, Secure, SameSite cookies.
   - Implement `get_current_user` dependency in `dependencies.py` checking the token on protected routes.
2. **Intake & Direct Pipeline Orchestration:** In `src/fintech_app/api/endpoints/analysis.py`:
   - Implement `POST /api/v1/analysis/start` accepting multipart form data: company name, tax ID, sector code, active submodules JSON array, and up to 5 CSV files.
   - Insert an `analysis_runs` record with status `QUEUED` into PostgreSQL.
   - Enqueue background task via FastAPI `BackgroundTasks`. The worker task parses files, loads data into PostgreSQL via `Database`, constructs `CompanyDataSnapshot` via `CompanyEvaluationRepository`, and directly invokes `UnderwritingAnalyticalPipeline.run_analysis()` from `src/fintech_app/ml/pipeline.py` and `CreditScoringEngine.calculate_score()` from `src/fintech_app/ml/scoring.py`.
3. **Real-Time Telemetry via Server-Sent Events (SSE):**
   - Implement `GET /api/v1/analysis/stream/{run_id}` returning a `StreamingResponse(..., media_type="text/event-stream")`.
   - Poll or listen to `analysis_logs` table for new entries, streaming JSON events formatted as:
     `data: {"timestamp": "...", "severity": "INFO", "stage": "SUBMODULE_4_6", "message": "..."}\n\n`
   - Send terminal event `event: complete` when `analysis_runs.status` transitions to `COMPLETED` or `FAILED`.
4. **Diagnostic Report Delivery:** Implement `GET /api/v1/analysis/report/{run_id}`:
   - Fetch completed run from `analysis_runs`.
   - Return structured JSON containing the canonical 18D feature vector, 9 submodule report cards, universal score, verdict category (`PRIME_LOW_RISK`, `MODERATE_MONITORED`, `HIGH_RISK_REJECT`), recommendation (`APPROVED`, `MANUAL_REVIEW`, `REJECTED`), and LLM executive narrative.
5. **LLM Narrative Synthesis:** In `src/fintech_app/api/endpoints/analysis.py`:
   - Connect to OpenAI API (`gpt-4o-mini`) or local Ollama instance (`http://localhost:11434`).
   - Feed the dry diagnostic reports emitted by Submodules 4.1–4.9 into the structured prompt generated by `CreditScoringEngine`.
   - Persist the synthesized text into `analysis_runs.llm_final_summary`.

##### Phase 3 Tasks (Testing & Integration)
1. **SSE Load Test:** Verify that 10 concurrent browser connections to `/api/v1/analysis/stream/{run_id}` stream telemetry smoothly without deadlocking the AsyncIO event loop.
2. **Fail-Safe Degradation Test:** Simulate a failure in an optional submodule (e.g. missing sector data) and verify that the endpoint marks the run as `DEGRADED`, finishes the remaining modules, and serves the report without throwing an HTTP 500 error.

#### Strict Technical Invariants & Rules
- **No Blocking Operations in Async Handlers:** File I/O and heavy CPU math must run inside thread pools (`run_in_threadpool`) or background tasks.
- **Strict Cookie Security:** Never transmit raw JWT tokens in JSON response bodies. Use `Set-Cookie: HttpOnly; Secure; SameSite=Lax`.
- **Standardized Error Handling:** All API errors must return standard JSON schemas: `{"detail": "Descriptive message", "code": "ERROR_CODE"}`.

---

### 3.3 DEVELOPER CARD: @Xtnray
* **Handle:** `@Xtnray`
* **Domain Role:** Web Frontend & Client UX
* **Assigned Branch:** `feature/ui-frontend` (branched off `dev`)

#### High-Level Intuition
You create the face of the product. The most sophisticated financial math is useless if the credit underwriter cannot understand the risk profile within 5 seconds. Your mission is to build a sleek, hyper-responsive, interactive web interface using modern vanilla JavaScript and TailwindCSS. You will visually communicate the core problem ("Profit != Cash") via dynamic charts, guide users through data upload with real-time file validation, provide a live execution terminal, and render an underwriting dossier that makes complex risk indices immediately actionable.

#### Target File Manifest
- `static/index.html` (Landing page & conceptual problem explanation)
- `static/docs.html` (Interactive documentation & "Profit != Cash" visual canvas)
- `static/analyze_new.html` (Intake wizard form & multi-zone file uploader)
- `static/analyze_track.html` (Real-time telemetry terminal & progress tracker)
- `static/analyze_report.html` (Comprehensive underwriting dossier & interactive simulator)
- `static/js/api_client.js` (Centralized HTTP & SSE fetch client)
- `static/js/mock_service.js` (Client-side mock interceptor for zero-backend UI development)
- `static/js/charts.js` (Canvas/SVG rendering for radar curves and gauge meters)

#### Phased Implementation Tasks

##### Phase 1 Tasks (Contracts & Mocks)
1. **Zero-Backend Client Mocking Layer:** Implement `static/js/mock_service.js`:
   - Intercept global `window.fetch` and `window.EventSource` when a debug flag (`localStorage.getItem('USE_UI_MOCKS') === 'true'`) is active.
   - Return realistic mock responses for `/api/v1/analysis/start`, simulate SSE logs for `/stream/{id}`, and supply full mock JSON dossiers for `/report/{id}`.
   - This allows you to build and polish the entire UI without waiting for backend API branches to merge.
2. **Design System & Asset Layout:** Setup TailwindCSS via CDN or compiled build in `/static/css/styles.css`. Establish typography, color palettes (emerald for solvency, amber for warnings, rose for cash crunches, slate for dark mode), and card layouts.

##### Phase 2 Tasks (Interactive Views & Visualizations)
1. **Interactive Educational Portal (`/docs`):**
   - In `static/docs.html`, implement an interactive SVG/HTML5 Canvas illustrating the **"Profit != Cash" Curve Divergence**.
   - Provide interactive sliders for "Revenue Growth Rate" and "Receivable Delay (Days)". As the user increases receivable delay, render the widening divergence where Accounting Profit trends upwards while Liquid Cash drops below the insolvency line into negative territory.
   - Render an interactive architecture diagram mapping the 9 submodules into their respective risk clusters.
2. **Analysis Wizard (`/analyze/new`):**
   - In `static/analyze_new.html`, build a multi-step form capturing company legal name, tax ID, industry sector, and analysis date.
   - Build 5 designated drag-and-drop file upload zones:
     1. Bank Statement (Transactions Ledger) — *Mandatory*
     2. Commercial Receivables (Invoices Out) — *Recommended*
     3. Commercial Payables (Invoices In) — *Recommended*
     4. Credit Obligations & Debt Schedule — *Optional*
     5. Cap-Table & Shareholder Registry — *Optional*
   - Display real-time warnings if optional files are omitted, notifying the user: *"Submodule 4.9 will run in Degraded Mode (Bypassed) due to missing debt schedule."*
3. **Real-Time Telemetry Terminal (`/analyze/track/{run_id}`):**
   - In `static/analyze_track.html`, create a dark-themed, monospace execution terminal.
   - Connect to `GET /api/v1/analysis/stream/{run_id}` via `EventSource`.
   - Render incoming log lines with color-coded severity badges (`[INFO]`, `[WARN]`, `[ERROR]`).
   - Display 9 submodule progress badges that transition state in real time: `QUEUED` (gray) -> `PROCESSING` (pulsing blue) -> `COMPLETED` (green) or `DEGRADED` (yellow).
   - On `complete` event, automatically redirect the user to `/analyze/report/{run_id}`.
4. **Underwriting Dossier Dashboard (`/analyze/report/{run_id}`):**
   - In `static/analyze_report.html`, build the executive credit dossier:
     - **Hero Section:** Radial gauge displaying composite credit score (0–100), recommendation badge (`APPROVED`, `MANUAL_REVIEW`, `REJECTED`), verdict category badge (`PRIME_LOW_RISK`, `MODERATE_MONITORED`, `HIGH_RISK_REJECT`), and max credit limit in MDL.
     - **AI Synthesis Card:** Markdown-formatted executive summary generated by the LLM.
     - **9 Submodule Detail Cards:** Expandable accordion cards displaying the dry diagnostic text report, individual impact weight, and numerical index meters for each of the canonical 18 indices.
     - **Interactive Sensitivity Sliders:** Allow underwriters to adjust individual index weights and observe real-time re-calculation of the composite score.

##### Phase 3 Tasks (Testing & Integration)
1. **Cross-Browser & Responsiveness Testing:** Verify responsive layout across mobile, tablet, and desktop (1080p and 4K displays).
2. **Full Pipeline Integration:** Disable `mock_service.js`, connect directly to `@egordjundiet`'s backend, and verify live file upload, SSE log streaming, and report rendering.

#### Strict Technical Invariants & Rules
- **No Heavy Frontend Frameworks:** Keep it lightweight and ultra-fast. Use modern ES6+ vanilla JavaScript, HTML5 templates, and TailwindCSS.
- **Graceful Network Degradation:** If the SSE stream disconnects, implement automatic exponential backoff reconnection.
- **XSS Sanitization:** All text rendered from API responses (especially LLM summaries and file names) must be sanitized before insertion into the DOM.

---

### 3.4 DEVELOPER CARD: @ozzyrastamouse
* **Handle:** `@ozzyrastamouse`
* **Domain Role:** Ingestion Engine & Data Processing Specialist
* **Assigned Branch:** `feature/data-parser` (branched off `dev`)

#### High-Level Intuition
Garbage in, garbage out. If a bank statement has unparsed headers, misaligned currency columns, or trailing commas, bad data will corrupt the entire analytical graph. Your mission is to build an intelligent, memory-safe data ingestion engine. You will parse heterogenous CSV files, use fuzzy column mapping to recognize unpredictable bank column names, categorize transaction expenses using keyword intelligence, and produce strictly validated batches ready for direct insertion into PostgreSQL. In accordance with `docs/folders_structure.md`, custom exceptions inherit from `src/fintech_app/core/exceptions.py`.

#### Target File Manifest
- `src/fintech_app/ingestion/schemas.py` (Pydantic validation schemas: `RawBankStatementLine`, `ParsedBankStatementPayload`, `StandardizedTransactionBatch`)
- `src/fintech_app/ingestion/parser.py` (`BankStatementParser`, chunked memory-safe reading)
- `src/fintech_app/ingestion/ai_mapper.py` (`TransactionCategorizationMapper`, fuzzy header mapping & keyword categorization)
- `src/fintech_app/core/exceptions.py` (`ParsingError` hierarchy inheriting from `GraeaeEyeException`)

#### Phased Implementation Tasks

##### Phase 1 Tasks (Contracts & Mocks)
1. **Strict Pydantic Validation Schemas:** In `src/fintech_app/ingestion/schemas.py`, define rigorous validation contracts enforcing `Decimal`, `UUID`, and `date`. Replace all legacy `float` fields:
   ```python
   from decimal import Decimal
   from datetime import date, datetime
   from typing import List, Optional
   from uuid import UUID, uuid4
   from pydantic import BaseModel, Field, field_validator
   from fintech_app.shared.schemas.user_types import (
       TransactionDirection, TransactionCategory, LiquidityClass, InvoiceType, InvoiceStatus
   )

   class RawBankStatementLine(BaseModel):
       date: date
       amount: Decimal
       direction: TransactionDirection
       description: str
       counterparty_raw_name: Optional[str] = None
       counterparty_tax_id: Optional[str] = None
       account_number: str
       currency: str

   class ParsedBankStatementPayload(BaseModel):
       account_id: UUID
       business_id: UUID
       opening_balance: Decimal
       closing_balance: Decimal
       period_start: date
       period_end: date
       lines: List[RawBankStatementLine]

   class NormalizedTransactionRecord(BaseModel):
       transaction_id: UUID = Field(default_factory=uuid4)
       business_id: UUID
       account_id: UUID
       counterparty_id: Optional[UUID] = None
       timestamp: datetime
       amount: Decimal
       direction: TransactionDirection
       category: TransactionCategory
       liquidity_class: LiquidityClass = LiquidityClass.IMMEDIATE_CASH

       @field_validator('amount')
       @classmethod
       def enforce_positive_decimal(cls, v: Decimal) -> Decimal:
           if v <= Decimal('0.00'):
               raise ValueError("Transaction amount must be strictly positive.")
           return v.quantize(Decimal('0.01'))

   class StandardizedTransactionBatch(BaseModel):
       business_id: UUID
       account_id: UUID
       transactions: List[NormalizedTransactionRecord]
       total_count: int
       total_inflow: Decimal
       total_outflow: Decimal
   ```
2. **Mock Parser Output:** Provide mock fixture functions in `parser.py` that generate a synthetic `StandardizedTransactionBatch` so downstream submodules can test against real data shapes immediately.

##### Phase 2 Tasks (Business Logic & Intelligent Ingestion)
1. **Chunked Memory-Safe Parser:** In `src/fintech_app/ingestion/parser.py`:
   - Implement `BankStatementParser` using `pandas.read_csv` with chunked reading (`chunksize=1000`) or standard library `csv.DictReader` to prevent memory blowup on 100MB+ statement files.
   - Detect and strip whitespace, European number formats (e.g. `1.250,50` -> `1250.50`), currency symbols (`MDL`, `EUR`, `$`), and corrupted BOM headers.
   - Raise `ParsingError(message)` (imported directly from `src/fintech_app/core/exceptions.py`) when encountering unrecoverable syntax errors.
2. **Fuzzy Header Mapper:** In `src/fintech_app/ingestion/ai_mapper.py`:
   - Implement `fuzzy_map_headers(columns: List[str]) -> Dict[str, str]`:
     Map disparate bank header variations to canonical fields (`timestamp`, `amount`, `description`, `counterparty_tax_id`, `direction`):
     - Amount: `["suma", "amount", "debit/credit", "valoare", "betrag", "montant"]`
     - Date: `["data", "date", "trans_date", "timestamp", "datum"]`
     - Description: `["detalii", "description", "details", "memo", "verwendungszweck"]`
3. **Keyword-Driven Expense Categorization:** In `src/fintech_app/ingestion/ai_mapper.py`:
   - Implement `categorize_transaction(description: str, direction: TransactionDirection) -> TransactionCategory`:
     - If `direction == INFLOW`: default to `TransactionCategory.REVENUE`.
     - If `direction == OUTFLOW`: inspect description keywords:
       - Payroll: `["salariu", "salary", "remunerare", "payroll", "avans salariu"]` -> `PAYROLL`
       - Taxes: `["fisc", "tva", "impozit", "buget", "tax", "vat", "inspectorat"]` -> `TAX`
       - Debt Service: `["credit", "dobanda", "loan", "leasing", "principal", "rambursare"]` -> `DEBT_SERVICE`
       - Dividends: `["dividend", "distribuire profit"]` -> `DIVIDEND`
       - Fallback: `OPERATING_EXPENSE`
4. **Relational Batch Assembly & DAL Integration:**
   - Coordinate parsing and batch normalization inside `parser.py` and `ai_mapper.py`.
   - Accept the raw uploaded files from `@egordjundiet`'s intake endpoint.
   - Transform parsed lines into `StandardizedTransactionBatch`.
   - Call `@newgopro`'s `db.bulk_insert_transactions` and `db.bulk_insert_invoices` to persist records directly in PostgreSQL.

##### Phase 3 Tasks (Testing & Integration)
1. **Edge Case Fuzzing:** Create automated tests parsing dirty, malformed bank statements:
   - CSV with missing quotes, trailing empty lines, corrupted dates, and mixed UTF-8 / Windows-1251 encodings.
   - Assert that invalid rows are logged with clear warnings and valid rows are preserved.
2. **Financial Precision Assertion:** Verify that the sum of `amount` across 10,000 parsed transactions matches the bank closing balance down to 0.01 MDL without rounding drift.

#### Strict Technical Invariants & Rules
- **ZERO `float` in Financial Schemas:** Every monetary amount must be converted to `Decimal(str(val))` immediately upon parsing.
- **Fail-Safe Sanitization:** Never allow unhandled parsing exceptions to bubble up as raw HTTP 500 errors. Wrap in `ParsingError` from `core/exceptions.py`.
- **Streaming Over In-Memory Buffers:** Never load entire multi-gigabyte files into raw memory arrays without streaming.

---

### 3.5 DEVELOPER CARD: @Mr-Ressentiment
* **Handle:** `@Mr-Ressentiment`
* **Domain Role:** Analytical Core & Quantitative Scoring Architect
* **Assigned Branch:** `feature/analytical-core` (branched off `dev`)

#### High-Level Intuition
You are the intellectual engine of the platform. Raw transactions and invoices are just rows in a database; your algorithms transform them into deep financial insight. Your mission is to implement 9 autonomous, mathematically rigorous analytical submodules that dissect an SME's solvency, liquidity runway, customer concentration, and payment discipline. You normalize these metrics into an 18-element feature vector, compute an investment attractiveness score (0–100) and probability of default via `CreditScoringEngine`, assign canonical verdicts (`PRIME_LOW_RISK`, `MODERATE_MONITORED`, `HIGH_RISK_REJECT`) and recommendations (`APPROVED`, `MANUAL_REVIEW`, `REJECTED`), and construct the prompt that guides the LLM to write an executive underwriting dossier.

#### Target File Manifest
- `src/fintech_app/ml/submodule_ownership.py` (Submodule 4.1: OS)
- `src/fintech_app/ml/submodule_reputation.py` (Submodule 4.2: WPR)
- `src/fintech_app/ml/submodule_macro.py` (Submodule 4.3: MSR)
- `src/fintech_app/ml/submodule_client_dep.py` (Submodule 4.4: CD)
- `src/fintech_app/ml/submodule_supplier_dep.py` (Submodule 4.5: SD)
- `src/fintech_app/ml/submodule_cash_readiness.py` (Submodule 4.6: ICR)
- `src/fintech_app/ml/submodule_cash_stability.py` (Submodule 4.7: CFS)
- `src/fintech_app/ml/submodule_receivables.py` (Submodule 4.8: RQ)
- `src/fintech_app/ml/submodule_credit_discipline.py` (Submodule 4.9: ICDL)
- `src/fintech_app/ml/pipeline.py` (`UnderwritingAnalyticalPipeline`)
- `src/fintech_app/ml/scoring.py` (`CreditScoringEngine`)

#### Phased Implementation Tasks

##### Phase 1 Tasks (Contracts & Mocks)
1. **Universal Submodule Protocol:** Confirm that every submodule evaluator implements a uniform execution interface:
   ```python
   class BaseSubmoduleEvaluator:
       submodule_code: str
       impact_weight: float

       def evaluate(self, snapshot: CompanyDataSnapshot) -> SubmoduleResult:
           """Analyzes the company snapshot and returns structured diagnostic results."""
   ```
2. **SubmoduleResult DTO & Shared Contract:** Declare `SubmoduleResult` inside `src/fintech_app/ml/pipeline.py` (or a shared base module) rather than `submodule_ownership.py`, so individual analytical submodules do not circularly depend on submodule 4.1. Enforce the terminal structure:
   - `submodule_code: str` (e.g. `'OS'`, `'WPR'`, `'MSR'`, `'CD'`, `'SD'`, `'ICR'`, `'CFS'`, `'RQ'`, `'ICDL'`)
   - `status: EvaluationStatus` (`SUCCESS`, `DATA_ABSENT`, `ERROR`)
   - `impact_weight: float`
   - `verdict: str`
   - `indices: Dict[str, Optional[float]]` (Strictly maps each submodule's canonical indices to bounded floats [0.0, 100.0] or `None` when `DATA_ABSENT`)
   - `summary: str`
   - `diagnostic_report: str`
3. **Mock Pipeline Execution:** Provide deterministic mock evaluations across all 9 submodules returning synthetic scores so `@egordjundiet` and `@Xtnray` can immediately render realistic reports.

##### Phase 2 Tasks (Concrete Financial Algorithms & Mathematical Core)

> [!IMPORTANT]
> **Canonical 18D Feature Vector Distribution Rule:** Submodules do NOT all emit 2 indices. The canonical distribution is strictly:
> $$\mathbf{2 + 2 + 1 + 2 + 2 + 2 + 2 + 2 + 3 = 18\text{ indices}}$$
> Every index name and mathematical formula must match `docs/architecture-v3.md` word-for-word.

Implement the concrete mathematical algorithms across all 9 flat submodules in `src/fintech_app/ml/`:

1. **`submodule_ownership.py` (Submodule 4.1: OS | Impact Weight: 0.08):**
   - **Canonical Indices (2):** `Ownership_Dispersion_Index`, `Governance_Independence_Index`
   - **Math & Formulas:**
     - Equity Herfindahl-Hirschman Index: $HHI_{owners} = \sum (s_i)^2$, where $s_i$ is equity share % of shareholder $i$ (scale 0 to 10,000).
     - Management-Ownership Overlap Ratio ($MOOR$):
       $$MOOR = \sum (s_i \text{ WHERE } \text{is\_management\_member} == \text{True}) / 100.0$$
     - Governance Independence Ratio ($GIR$):
       $$GIR = \text{independent\_directors\_count} / \max(\text{total\_board\_seats}, 1.0)$$
     - Consolidated Indices:
       $$\text{Ownership\_Dispersion\_Index} = \text{clamp}(0.0, 100.0, 100.0 - (HHI_{owners} / 100.0))$$
       $$\text{Governance\_Independence\_Index} = \text{clamp}(0.0, 100.0, (GIR \times 70.0) + ((1.0 - MOOR) \times 30.0))$$
   - **Verdicts:** `BALANCED_GOVERNANCE`, `KEY_PERSON_RISK`, `CONCENTRATED_OWNERSHIP`

2. **`submodule_reputation.py` (Submodule 4.2: WPR | Impact Weight: 0.12):**
   - **Canonical Indices (2):** `Legal_Cleanliness_Index`, `Public_Reputation_Index`
   - **Math & Formulas:**
     - Sanctions Check: If `is_in_sanctions_list == True`, immediately set `Legal_Cleanliness_Index = 0.0`.
     - Litigation Exposure Ratio ($LER$):
       $$\text{Liquid\_Cash} = \sum \text{bank\_accounts.current\_balance}$$
       $$LER = \frac{\text{total\_lawsuit\_claims\_amount}}{\max(\text{Liquid\_Cash}, 1.0)}$$
     - Legal Cleanliness:
       $$\text{Base\_Legal} = 100.0 - (\text{active\_lawsuits\_count} \times 15.0) - \min(50.0, LER \times 50.0)$$
       $$\text{Legal\_Cleanliness\_Index} = \text{clamp}(0.0, 100.0, \text{Base\_Legal})$$
     - Public Reputation: If `news_sentiment_score` is `None`: default to `50.0` (neutral fallback); else:
       $$\text{Public\_Reputation\_Index} = \text{clamp}(0.0, 100.0, (\text{news\_sentiment\_score} + 1.0) \times 50.0)$$
   - **Verdicts:** `LEGAL_INTEGRITY_CONFIRMED`, `LITIGATION_EXPOSURE`, `CRITICAL_LEGAL_FLAG`

3. **`submodule_macro.py` (Submodule 4.3: MSR | Impact Weight: 0.05):**
   - **Canonical Indices (EXACTLY 1 index):** `Sector_Vitality_Index`
   - **Math & Formulas:**
     - Growth Score: $\text{Growth\_Score} = \text{clamp}(0.0, 100.0, 50.0 + (\text{sector\_growth\_rate\_yoy} \times 5.0))$
     - Default Safety: $\text{Default\_Safety\_Score} = \text{clamp}(0.0, 100.0, 100.0 - (\text{sector\_default\_rate} \times 5.0))$
     - Macro Outlook: $\text{Macro\_Stability\_Score} = \text{clamp}(0.0, 100.0, 100.0 - ((\text{risk\_outlook\_score} - 1) \times 11.11))$
     - Consolidated:
       $$\text{Sector\_Vitality\_Index} = (0.40 \times \text{Growth\_Score}) + (0.35 \times \text{Default\_Safety\_Score}) + (0.25 \times \text{Macro\_Stability\_Score})$$
   - **Verdicts:** `EXPANDING_SECTOR`, `STABLE_SECTOR`, `HIGH_RISK_SECTOR`

4. **`submodule_client_dep.py` (Submodule 4.4: CD | Impact Weight: 0.10):**
   - **Canonical Indices (2):** `Client_Diversification_Index`, `Top_Client_Exposure_Index`
   - **Math & Formulas:**
     - Customer Concentration HHI: $\text{Customer\_HHI} = \sum (\text{Share}_k)^2$ across all clients over trailing 12 months.
     - Top Client Share: $CR1 = \max(\text{Share}_k)$
     - Top 3 Clients Share: $CR3 = \sum_{k=1}^3 \text{Share}_k$
     - `Client_Diversification_Index = clamp(0.0, 100.0, 100.0 - (Customer_HHI / 100.0))`
     - `Top_Client_Exposure_Index = clamp(0.0, 100.0, 100.0 - CR1)`
   - **Verdicts:** `BROAD_CLIENT_BASE`, `MODERATE_CONCENTRATION`, `SEVERE_CLIENT_DEPENDENCY`

5. **`submodule_supplier_dep.py` (Submodule 4.5: SD | Impact Weight: 0.08):**
   - **Canonical Indices (2):** `Supplier_Diversification_Index`, `Supply_Chain_Robustness_Index`
   - **Math & Formulas:**
     - Vendor Spend HHI: $\text{Vendor\_HHI} = \sum (\text{Spend\_Share}_m)^2$ across all suppliers over trailing 12 months.
     - Primary Vendor Share: $\text{Primary\_Vendor\_Share} = \max(\text{Spend\_Share}_m)$
     - `Supplier_Diversification_Index = clamp(0.0, 100.0, 100.0 - (Vendor_HHI / 100.0))`
     - `Supply_Chain_Robustness_Index = clamp(0.0, 100.0, 100.0 - Primary_Vendor_Share)`
   - **Verdicts:** `DIVERSIFIED_SUPPLY_CHAIN`, `MONOPOLISTIC_SUPPLIER_RISK`

6. **`submodule_cash_readiness.py` (Submodule 4.6: ICR | Impact Weight: 0.15):**
   - **Canonical Indices (2):** `Cash_Readiness_Index`, `Runway_Buffer_Index`
   - **Math & Formulas:**
     - Liquid Cash: $\text{Liquid\_Cash} = \sum \text{current\_balance} + \sum \text{overdraft\_limit}$
     - 30-Day Demand: $\text{Total\_Immediate\_Demand} = \text{Monthly\_Payroll} + \text{Monthly\_Taxes} + \text{Due\_Payables}_{30d}$
     - Cash Ratio ($CR$): $CR = \text{Liquid\_Cash} / \max(\text{Total\_Immediate\_Demand}, 1.0)$
     - Days Cash on Hand ($DCOH$): $DCOH = \text{Liquid\_Cash} / \max((\text{Monthly\_Payroll} + \text{Monthly\_Taxes}) / 30.0, 1.0)$
     - `Cash_Readiness_Index = clamp(0.0, 100.0, CR * 50.0)`  *(Target: CR >= 2.0 = 100.0)*
     - `Runway_Buffer_Index = clamp(0.0, 100.0, (DCOH / 60.0) * 100.0)`  *(Target: 60+ Days = 100.0)*
   - **Verdicts:** `LIQUID_AND_SOLVENT`, `POTENTIAL_CASH_GAP`, `SEVERE_ILLIQUIDITY`

7. **`submodule_cash_stability.py` (Submodule 4.7: CFS | Impact Weight: 0.08):**
   - **Canonical Indices (2):** `Revenue_Predictability_Index`, `Revenue_Trajectory_Index`
   - **Math & Formulas:**
     - 12-Month Inflow Volatility: $CV_{\text{Revenue}} = \sigma_{\text{Revenue}} / \max(\mu_{\text{Revenue}}, 1.0)$
     - Ordinary Least Squares Linear Trend: $\text{Slope} = \frac{\text{Covariance}(t, R_t)}{\text{Variance}(t)}$; $\text{Normalized\_Trend} = \text{Slope} / \max(\mu_{\text{Revenue}}, 1.0)$
     - `Revenue_Predictability_Index = clamp(0.0, 100.0, 100.0 - (CV_Revenue * 100.0))`
     - `Revenue_Trajectory_Index = clamp(0.0, 100.0, 50.0 + (Normalized_Trend * 500.0))`
   - **Verdicts:** `CONSISTENT_FLOWS`, `MODERATE_VOLATILITY`, `HIGHLY_ERRATIC_FLOWS`

8. **`submodule_receivables.py` (Submodule 4.8: RQ | Impact Weight: 0.14):**
   - **Canonical Indices (2):** `Receivables_Safety_Index`, `Client_Payment_Discipline_Index`
   - **Math & Formulas:**
     - Counterparty Exposure Ratio ($CER$):
       $$\text{Total\_Receivables} = \sum \text{gross\_amount (status != PAID)}$$
       $$\text{Delinquent\_Receivables} = \sum \text{gross\_amount (status in [OVERDUE, DEFAULTED])}$$
       $$CER = \text{Delinquent\_Receivables} / \max(\text{Total\_Receivables}, 1.0)$$
     - Behavioral Delay (Slippage): $\text{Mean\_Delay\_Days} = \text{Average}(\max(0, \text{actual\_payment\_date} - \text{due\_date}))$
     - Days Sales Outstanding ($DSO$): $DSO = (\text{Total\_Receivables} / \max(\text{Annual\_Credit\_Sales}, 1.0)) \times 365.0$
     - `Receivables_Safety_Index = clamp(0.0, 100.0, 100.0 - (CER * 100.0))`
     - `Client_Payment_Discipline_Index = clamp(0.0, 100.0, 100.0 - (Mean_Delay_Days * 2.0))`
   - **Verdicts:** `PROMPT_COLLECTIONS`, `MODERATE_SLIPPAGE`, `FROZEN_DEBT_RISK`

9. **`submodule_credit_discipline.py` (Submodule 4.9: ICDL | Impact Weight: 0.16):**
   - **Canonical Indices (EXACTLY 3 indices):** `Debt_Repayment_Discipline_Index`, `Debt_Service_Coverage_Index`, `Solvency_Leverage_Index`
   - **Math & Formulas:**
     - Historical Delinquency Penalty:
       $$\text{DPD\_Penalty} = (\text{past\_due\_30d\_count} \times 10.0) + (\text{past\_due\_90d\_count} \times 25.0) + (\text{historical\_defaults\_count} \times 50.0)$$
       $$\text{Debt\_Repayment\_Discipline\_Index} = \text{clamp}(0.0, 100.0, 100.0 - \text{DPD\_Penalty})$$
     - Debt Service Coverage Ratio ($DSCR$):
       $$\text{Operating\_Cash\_Flow} = \max(0.0, \text{Annual\_Inflows} - \text{Annual\_OpEx})$$
       $$\text{Annual\_Debt\_Service} = \sum (\text{monthly\_payment} \times 12.0)$$
       $$DSCR = \text{Operating\_Cash\_Flow} / \max(\text{Annual\_Debt\_Service}, 1.0)$$
       $$\text{Debt\_Service\_Coverage\_Index} = \text{clamp}(0.0, 100.0, (DSCR / 2.0) \times 100.0) \quad \text{(Target: } DSCR \ge 2.0\text{)}$$
     - Total Debt-to-Cash Flow Leverage ($DCFL$):
       $$DCFL = \text{Total\_Debt} / \max(\text{Operating\_Cash\_Flow}, 1.0)$$
       $$\text{Solvency\_Leverage\_Index} = \text{clamp}(0.0, 100.0, 100.0 - (DCFL \times 20.0))$$
   - **Verdicts:** `PRISTINE_CREDIT`, `MODERATE_LEVERAGE`, `OVERINDEBTED_DELINQUENT`

10. **Graceful Degradation Mechanism:**
    - If a domain entity in `CompanyDataSnapshot` is empty or missing (e.g. no credit obligations uploaded), the evaluator must **NEVER throw an exception**.
    - Return `SubmoduleResult(status=EvaluationStatus.DATA_ABSENT, verdict="BYPASSED", indices={...: None})` setting all respective indices for that submodule to `None`.

11. **Canonical Ordered 18D Feature Vector Assembly:** In `src/fintech_app/ml/pipeline.py`:
    - `UnderwritingAnalyticalPipeline.run_analysis(snapshot, as_of_date)` executes all 9 submodules concurrently.
    - Flattens the submodule results into the canonical ordered 18-element feature vector $V$:
    ```python
    feature_vector: List[Optional[float]] = [
        # Submodule 4.1: OS (2 indices)
        sub_results["OS"].indices.get("Ownership_Dispersion_Index"),
        sub_results["OS"].indices.get("Governance_Independence_Index"),
        # Submodule 4.2: WPR (2 indices)
        sub_results["WPR"].indices.get("Legal_Cleanliness_Index"),
        sub_results["WPR"].indices.get("Public_Reputation_Index"),
        # Submodule 4.3: MSR (1 index)
        sub_results["MSR"].indices.get("Sector_Vitality_Index"),
        # Submodule 4.4: CD (2 indices)
        sub_results["CD"].indices.get("Client_Diversification_Index"),
        sub_results["CD"].indices.get("Top_Client_Exposure_Index"),
        # Submodule 4.5: SD (2 indices)
        sub_results["SD"].indices.get("Supplier_Diversification_Index"),
        sub_results["SD"].indices.get("Supply_Chain_Robustness_Index"),
        # Submodule 4.6: ICR (2 indices)
        sub_results["ICR"].indices.get("Cash_Readiness_Index"),
        sub_results["ICR"].indices.get("Runway_Buffer_Index"),
        # Submodule 4.7: CFS (2 indices)
        sub_results["CFS"].indices.get("Revenue_Predictability_Index"),
        sub_results["CFS"].indices.get("Revenue_Trajectory_Index"),
        # Submodule 4.8: RQ (2 indices)
        sub_results["RQ"].indices.get("Receivables_Safety_Index"),
        sub_results["RQ"].indices.get("Client_Payment_Discipline_Index"),
        # Submodule 4.9: ICDL (3 indices)
        sub_results["ICDL"].indices.get("Debt_Repayment_Discipline_Index"),
        sub_results["ICDL"].indices.get("Debt_Service_Coverage_Index"),
        sub_results["ICDL"].indices.get("Solvency_Leverage_Index"),
    ]
    ```

12. **Scoring Engine & Canonical Verdict Assignment:** In `src/fintech_app/ml/scoring.py`:
    - Implement `CreditScoringEngine.calculate_score(feature_vector, compiled_dossier_text)`:
      - Computes composite investment attractiveness score bounded strictly in `[0.0, 100.0]`.
      - Computes estimated probability of default $PD \in [0.001, 0.999]$.
      - Assigns canonical verdicts strictly matching `docs/architecture-v3.md` Section 6.5:
        * **Score >= 75.0:** `verdict_category = "PRIME_LOW_RISK"`, `recommendation = "APPROVED"`
        * **55.0 <= Score < 75.0:** `verdict_category = "MODERATE_MONITORED"`, `recommendation = "MANUAL_REVIEW"`
        * **Score < 55.0:** `verdict_category = "HIGH_RISK_REJECT"`, `recommendation = "REJECTED"`
    - Constructs structured prompt feeding dry reports to the LLM for executive dossier generation.

##### Phase 3 Tasks (Testing & Integration)
1. **Mathematical Invariant Testing:** Verify with unit tests that all output indices are strictly clamped between `0.0` and `100.0`.
2. **Dynamic Weight Normalization Test:** Test pipeline execution when 2 submodules are `DATA_ABSENT`. Verify that the remaining 7 active submodules normalize their impact weights to sum exactly to `1.00`.
3. **Canonical Feature Vector Length Assertion:** Ensure `len(result.feature_vector) == 18` always, maintaining exact index alignment across missing submodules.

#### Strict Technical Invariants & Rules
- **Pure Functions / Deterministic Math:** All financial algorithms must be deterministic; identical `CompanyDataSnapshot` inputs must produce bitwise identical feature vectors.
- **Zero Div-by-Zero Exceptions:** All division operations must use protective maximum denominators: `val / max(denom, 1.0)`.
- **Boundary Clamping:** Every numerical index returned to the pipeline must pass through `min(100.0, max(0.0, float(score)))`.
- **Exact Nomenclature:** Index keys in dictionaries and feature vector slots must match the canonical casing and naming in `docs/architecture-v3.md` without exception.

---

## 4. ACCEPTANCE CRITERIA & CI/CD VERIFICATION

Before opening a Pull Request into `dev`, or before tagging a milestone release, developers must execute and pass the following quality and integrity gates.

### 4.1 Strict Type Checking & Bytecode Compilation
All Python files must compile cleanly under Python 3.12 without syntax errors or unresolvable imports:
```bash
python3 -m py_compile src/fintech_app/**/*.py
```
*Expected Result:* Exit code `0` with zero error messages.

---

### 4.2 Linter & Formatter Quality Gates (`ruff`)
All source code must adhere strictly to PEP 8 standards with a 100-character line limit:
```bash
ruff check . --fix
ruff format .
```
*Expected Result:* Zero lint errors or unresolved formatting issues.

---

### 4.3 Automated Verification Script & Invariant Assertions
Run the following verification one-liner to assert that no forbidden architectural patterns have leaked into the codebase or documentation:
```bash
# Assert: ZERO occurrences of SQLAlchemy, CompanyModel, ContractModel, ContractType, or python:3.10
grep -rnE "SQLAlchemy|CompanyModel|ContractModel|ContractType|python:3.10" src/ docs/ || echo "ALL INVARIANTS CLEAN"
```
*Expected Result:* Output reads `ALL INVARIANTS CLEAN`.

---

### 4.4 Automated Invariant Assertion Matrix

| Verification Target | Command / Check | Acceptance Criterion |
| :--- | :--- | :--- |
| **Financial Fields Precision** | Inspect `src/fintech_app/shared/schemas/` & `db/models.py` | 100% `decimal.Decimal` / `DECIMAL(18,2)`. **Zero `float`**. |
| **Entity Identifiers** | Inspect database models and DAL signatures | 100% `uuid.UUID` primary & foreign keys. |
| **Domain Enums** | Inspect `user_types.py` | 100% inherit from `enum.StrEnum` (Python 3.12). |
| **Analytical Core Layout** | `ls -la src/fintech_app/ml/` | **Exactly 9 flat submodules** + `pipeline.py` + `scoring.py`. |
| **18D Feature Vector** | Inspect `pipeline.py` and `scoring.py` | Exactly 18 items (2+2+1+2+2+2+2+2+3). |
| **Scoring Verdicts** | Inspect `scoring.py` and API/UI | `PRIME_LOW_RISK`, `MODERATE_MONITORED`, `HIGH_RISK_REJECT`; `APPROVED`, `MANUAL_REVIEW`, `REJECTED`. |
| **DAL Implementation** | Inspect `src/fintech_app/db/connection.py` | Uses `psycopg_pool.AsyncConnectionPool` returning `DatabaseReport`. |
| **Mock Stub Mandate** | Search for unhandled placeholders | **Zero `NotImplementedError`** in shared integration paths. |
| **Logging Discipline** | Search for standard prints in `src/` | **Zero raw `print()` statements**; standard library `logging` only. |

---

### 4.5 PR Merge Readiness Checklist (The Lead Architect's Gate)
Before merging any feature branch (`feature/*`) into `dev`, `@newgopro` must verify:
- [ ] PR branch branched cleanly off latest `dev`.
- [ ] PR title adheres to Conventional Commits (e.g. `feat(dal): implement bulk transaction copy`).
- [ ] No merge conflicts with `dev`.
- [ ] `py_compile` passes across all modified files.
- [ ] `ruff check .` passes with zero warnings.
- [ ] All cross-module contracts return valid mock stubs or concrete schemas.
- [ ] Zero forbidden keywords (`SQLAlchemy`, `CompanyModel`, `ContractModel`).

---
**Document Approved by:** Lead Architect & Engineering Management  
**Status:** Active Execution Directive | Version 3.0  
**Repository:** `GraeaeEye`
