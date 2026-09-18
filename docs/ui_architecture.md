```text
================================================================================
SMART CREDIT SYSTEM: WEB INTERFACE & ORCHESTRATION LAYER
TECHNICAL ARCHITECTURE & SPECIFICATION DOCUMENT (V2.0)
================================================================================

1. SYSTEM OVERVIEW, STACK & ARCHITECTURAL FOUNDATION
--------------------------------------------------------------------------------
1.1 System Role & Mission
The Web Interface & Orchestration Layer provides the human-in-the-loop frontend,
job pipeline coordination, and visualization dashboard for the Smart Credit
Underwriting Engine. The module orchestrates incoming SME data intake, triggers
the independent submodules, monitors processing pipelines in real time, and renders
the final underwriting diagnostic reports alongside LLM synthesis.

1.2 Production Technology Stack
* ASGI Application Engine: Python 3.12+, FastAPI, Uvicorn (multi-worker configuration).
* Client Rendering Layer: Lightweight Single-Page Architecture / Progressive HTML
  leveraging TailwindCSS for styling and Alpine.js / HTMX for reactive DOM mutation,
  lightweight canvas/SVG state transitions, and event-driven data streaming.
* Real-Time Event Transport: Server-Sent Events (SSE) via FastAPI's `StreamingResponse`
  for non-blocking, uni-directional runtime log and stage telemetries.
* Persistence & Storage Layer: PostgreSQL 16 via native asynchronous `psycopg_pool.AsyncConnectionPool` & `Database` DAL.
* Security & State: HTTP-only, secure, SameSite JSON Web Tokens (JWT) for stateless
  session authorization; passlib (Argon2 / bcrypt) for credential hashing.

1.3 API-First Development Principle
Because the central analytical core and external parsers are developed concurrently,
the web module establishes immutable contract interfaces early. All analytical
computation and file ingestion APIs will operate through modular adapter interfaces.
During active development, these adapters toggle between deterministic Mock Stubs
and concrete background workers without modifying the web application core.


2. RELATIONAL DATA LAYER: SHARED POSTGRESQL EXTENSION
--------------------------------------------------------------------------------
The Web Module shares the primary PostgreSQL instance with the Analytical Engine,
enforcing referential integrity between user identities, execution jobs, and
enterprise records.

--------------------------------------------------------------------------------
CLUSTER 2.1: IDENTITY, AUTHORIZATION & PREFERENCES
--------------------------------------------------------------------------------
* Table: users
  Stores user credentials, organizational affiliations, and RBAC states.
  - user_id (UUID, PK): Unique user identifier (RFC-4122).
  - email (VARCHAR(255), UNIQUE, NOT NULL): Corporate email address.
  - password_hash (VARCHAR(255), NOT NULL): Cryptographic password digest.
  - full_name (VARCHAR(128), NOT NULL): Legal name of underwriter or analyst.
  - role (VARCHAR(32), DEFAULT 'ANALYST'): Enum ('ADMIN', 'UNDERWRITER', 'ANALYST').
  - is_active (BOOLEAN, DEFAULT TRUE): Account status flag.
  - created_at (TIMESTAMP WITH TIME ZONE, DEFAULT NOW()): Registration timestamp.

* Table: user_settings
  Persists client workspace preferences.
  - setting_id (UUID, PK): Unique preferences record.
  - user_id (UUID, FK -> users.user_id ON DELETE CASCADE, UNIQUE, NOT NULL).
  - ui_theme (VARCHAR(16), DEFAULT 'system'): Enum ('light', 'dark', 'system').
  - terminal_sound_effects (BOOLEAN, DEFAULT FALSE): Audio toggle for live console logs.
  - auto_expand_reports (BOOLEAN, DEFAULT TRUE): Viewport state preference.

--------------------------------------------------------------------------------
CLUSTER 2.2: PIPELINE EXECUTION LIFECYCLE & PERSISTENCE
--------------------------------------------------------------------------------
* Table: analysis_runs
  Tracks every evaluation lifecycle, ingested payloads, and final output dossiers.
  - run_id (UUID, PK): Unique evaluation job identifier.
  - user_id (UUID, FK -> users.user_id, NOT NULL): Requesting user.
  - business_id (UUID, FK -> businesses.business_id, NULL): Link to business entity.
  - status (VARCHAR(32), NOT NULL): Enum ('QUEUED', 'PARSING', 'PROCESSING',
                                           'COMPLETED', 'FAILED', 'DEGRADED').
  - input_company_name (VARCHAR(255), NOT NULL): As declared in the wizard.
  - input_tax_id (VARCHAR(32), NOT NULL): As declared in the wizard.
  - input_industry_code (VARCHAR(16), NOT NULL): Declared sector code.
  - files_manifest (JSONB, NOT NULL): Map of uploaded file names, sizes, and formats.
  - active_submodules (JSONB, NOT NULL): Array of submodule IDs enabled for this run.
  - raw_indices_payload (JSONB, NULL): The aggregated 18-element numerical feature vector.
  - submodules_reports (JSONB, NULL): Structured verdicts, weights, and dry reports.
  - llm_final_summary (TEXT, NULL): Generated narrative synthesis from LLM.
  - universal_score (DECIMAL(5,2), NULL): Normalized overall score (0.00 to 100.00).
  - failure_reason (TEXT, NULL): Captured stack trace or fatal pipeline error.
  - created_at (TIMESTAMP WITH TIME ZONE, DEFAULT NOW()): Execution invocation time.
  - completed_at (TIMESTAMP WITH TIME ZONE, NULL): Pipeline termination time.

* Table: analysis_logs
  Ephemeral diagnostic messages emitted during submodule and data graph execution.
  - log_id (BIGSERIAL, PK): Incrementing event ID.
  - run_id (UUID, FK -> analysis_runs.run_id ON DELETE CASCADE, NOT NULL).
  - timestamp (TIMESTAMP WITH TIME ZONE, DEFAULT NOW()): Event timestamp.
  - severity (VARCHAR(16), NOT NULL): Enum ('DEBUG', 'INFO', 'WARN', 'ERROR').
  - stage (VARCHAR(32), NOT NULL): Stage emitting event ('INGESTION', 'SUBMODULE_4_1', etc.).
  - message (TEXT, NOT NULL): Descriptive telemetry log message.


3. USER INTERACTION ARCHITECTURE & DETAILED PAGE SPECIFICATIONS
--------------------------------------------------------------------------------

3.1 Authentication & Session Gateway (`/login`, `/register`)
* User Experience: Clean, distraction-free card interface. Form inputs validate
  email format and password entropy in real time.
* Functionality: Submits JSON payloads to `/api/v1/auth/token`. On success, receives
  JWT within an `HttpOnly`, `SameSite=Lax`, `Secure` cookie. An active session
  redirects immediately to the Interactive Documentation page if first login, or
  to the Analysis Wizard otherwise.

3.2 Interactive Documentation & Methodology Portal (`/docs`)
* Visual & Interactive Design:
  - Dynamic Hero Animation: Visual interactive canvas illustrating the "Profit != Cash"
    paradox: an animated line chart rendering divergent paths between accrued paper
    earnings versus dwindling operational cash reserves.
  - Relational Entity Graph Visualizer: Lightweight SVG graph showing how businesses,
    shareholders, bank accounts, invoices, and counterparties connect. Nodes react
    with subtle hover states explaining each entity's analytical significance.
  - Submodule Matrix: An exploratory grid detailing all 9 analytical submodules,
    displaying domain scope, indices evaluated, and required CSV inputs.
  - Data Standard & Templates: Downloadable, pre-validated CSV templates for all
    supported datasets, with inline modal schema viewers displaying exact column headers,
    nullability rules, and data formatting definitions.

3.3 Global Navigation Bar
* Persistent Top-Level Header with dynamic active-state indicators:
  - Brand identity & current environment badge (e.g., `MOCK_SANDBOX` vs `PRODUCTION`).
  - Navigation Links:
    * `New Analysis`: Takes user directly to the evaluation wizard.
    * `Report History`: Historical audit trail of prior evaluations.
    * `Documentation`: Quick reference to methodology and data formats.
  - Right-Hand Controls:
    * Workspace Theme Switcher (Light / Dark / Auto toggling CSS root variables).
    * User Profile Dropdown: Displays user name, role, and logout trigger.

3.4 Guided Analysis Wizard & File Ingestion Gateway (`/analyze/new`)
* Architecture: Multi-step, client-state-managed form validating constraints prior
  to submitting the multipart file payload.
* Step 1: Enterprise Metadata:
  - Input fields: Company Legal Name, National Tax ID (validated by sector-specific regex),
    Industry Classification (NACE/SIC searchable dropdown), Registration Date.
* Step 2: Relational Data File Provisioning:
  - Drag-and-Drop file intake zones. Each zone corresponds to an exact relational entity:
    * Zone A: Bank Accounts Ledger (`accounts.csv`)
    * Zone B: Transaction Journal (`transactions.csv`)
    * Zone C: Trade Invoices & Counterparties (`invoices.csv`)
    * Zone D: Historical & Existing Credit Obligations (`obligations.csv`)
    * Zone E: Equity Cap Table & Governance (`shareholders.csv`)
  - Permissive Upload Architecture: No file upload is strictly mandatory except for
    basic company identity. Underneath each drop zone, the UI displays dynamic
    submodule indicators:
    * E.g., Leaving Zone D (`obligations.csv`) empty displays a visible amber notice:
      `[Notice: Submodule 4.9 (Credit Discipline & Leverage) will be bypassed]`.
  - Client-side Pre-Validation: Verifies file extension (`.csv`), file size (< 50MB),
    and validates header rows against expected CSV schemas before submission.
* Step 3: Execution Initiation:
  - Action button: "Initialize Analysis Engine". Posts `multipart/form-data` to
    `/api/v1/analysis/start`. Receives `{ "run_id": "UUID" }` and routes browser
    instantly to the Live Execution Console.

3.5 Live Execution Console & Streaming Telemetry (`/analyze/track/{run_id}`)
* User Experience: High-density mission-control interface.
* Layout:
  - Header: Target company name, Tax ID, generated `run_id`, and dynamic execution status.
  - Pipeline Progress Bar: Segmented visual meter progressing through 4 stages:
    (1) File Ingestion & Parsing -> (2) Entity Graph Persistence -> (3) Parallel Submodule
    Evaluation (1 to 9) -> (4) LLM Synthesis & Scoring.
  - Active Submodule Grid: 9 interactive badges displaying real-time status:
    `PENDING` (dimmed), `RUNNING` (pulsing blue), `SUCCESS` (green checkmark),
    `BYPASSED` (amber warning), `FAILED` (red cross).
  - Virtual Terminal Window: Monospace, dark-canvas streaming terminal. Emits real-time
    telemetry strings:
    * `[14:23:01.102] [INFO] [INGEST] Parsing transactions.csv (4,120 rows verified).`
    * `[14:23:01.405] [INFO] [GRAPH] Constructing commercial counterparty graph.`
    * `[14:23:01.810] [INFO] [EXEC] Submodule 4.1 (Ownership Structure): Executing.`
    * `[14:23:02.115] [WARN] [EXEC] Obligations file absent. Submodule 4.9 BYPASSED.`
    * `[14:23:03.020] [INFO] [LLM] Streaming inference from Narrative Synthesizer...`
* Transition: Upon receiving the SSE terminal event `PIPELINE_COMPLETE`, the client
  waits 1.5 seconds and transitions dynamically to the Final Diagnostic Dossier.

3.6 Final Underwriting Dossier & Diagnostic Report (`/analyze/report/{run_id}`)
* Executive Summary Banner:
  - Universal Investment Attractiveness Score: Prominent circular radial gauge (0 to 100).
  - Categorical Verdict Tag: `PRIME / LOW_RISK`, `MODERATE_MONITORED`, `HIGH_RISK_REJECT`.
  - Export Controls: Action button to trigger headless print-ready PDF compilation.
* LLM Synthesis & Narrative Summary Card:
  - Polished prose synthesizing cross-submodule findings, highlighting primary operational
    risks, cash gap timelines, and structural concentration liabilities.
* Interactive Submodule Diagnostic Grid:
  - 9 expandable responsive cards grouped by domain (Governance, Commercial, Liquidity, Debt).
  - Collapsed Card State: Shows Submodule Name, Status (`ACTIVE` / `BYPASSED`), Status Verdict,
    Impact Weight Factor, and primary Numerical Indices (visual slider meters 0-100).
  - Expanded Card State: Renders the raw text diagnostic report formatted cleanly inside
    a code block or semantic typography container, displaying granular calculations
    (e.g., exact HHI scores, Cash Ratios, DCOH days, Delinquency penalties).
* Missing Data & Degradation Explanations:
  - Bypassed submodule cards display clear structural explanations:
    `Data Omitted: Underwriting proceeded without Credit History data. Model confidence penalized.`

3.7 Historical Runs Repository (`/history`)
* Overview Table:
  - Displays all historical evaluations executed by the user/organization.
  - Columns: Execution Date, Enterprise Legal Name, Tax ID, Status, Overall Score, Actions.
* Controls: Search input (filtering by company name or tax ID), date-range filters,
  and quick-view action buttons to inspect cached reports or re-download diagnostic logs.


4. REAL-TIME TELEMETRY PROTOCOL: SERVER-SENT EVENTS (SSE)
--------------------------------------------------------------------------------
4.1 Event Stream Endpoint
* Route: `GET /api/v1/analysis/stream/{run_id}`
* Media Type: `text/event-stream`
* Cache-Control: `no-cache`, `Connection: keep-alive`

4.2 Wire Format Protocol
All SSE events conform to standard event-stream framing:

```

event: <EVENT_TYPE>
data: <JSON_PAYLOAD>

```

4.3 Supported Event Types & Schemas
* `PIPELINE_STAGE_CHANGED`:
  Payload: `{ "stage": "PROCESSING_SUBMODULES", "progress_percentage": 45 }`
* `LOG_EMITTED`:
  Payload: `{ "timestamp": "2026-09-17T17:12:00.102Z", "severity": "INFO", 
              "stage": "SUBMODULE_4_6", "message": "Cash Ratio computed: 1.42. Runway: 48 days." }`
* `SUBMODULE_STATUS_UPDATED`:
  Payload: `{ "submodule_id": "ICR_4_6", "status": "SUCCESS", "verdict": "LIQUID_AND_SOLVENT" }`
* `PIPELINE_COMPLETE`:
  Payload: `{ "run_id": "UUID", "universal_score": 84.50, "redirect_url": "/analyze/report/UUID" }`
* `PIPELINE_FAILED`:
  Payload: `{ "run_id": "UUID", "error": "Invalid CSV Schema in invoices.csv: missing 'gross_amount'" }`


5. INTEGRATION STUBBING & MOCK SPECIFICATION
--------------------------------------------------------------------------------
To decouple the Web Layer development from the Core Analytical Engine, Database
Ingestion Workers, and LLM services, the backend includes an integrated Mock
Adapter Layer.

5.1 Architecture of the Mock Adapter
The backend utilizes an abstract processing interface:
`AnalysisExecutionProvider (ABC)`
* `ConcreteImplementation`: `ProductionAnalysisProvider` (Interacts with PostgreSQL,
  Celery/RQ workers, ML models, and LLM APIs).
* `MockImplementation`: `MockAnalysisProvider` (Generates deterministic delays, simulates
  streaming logs, produces standard dummy feature vectors, and returns synthetic reports).

A configuration flag in `.env` (`USE_MOCK_ENGINE=true`) switches implementations
via FastAPI dependency injection without changing a single line of web routing code.

5.2 Mock Ingestion Engine Stub
* Behavior: Accepts uploaded CSV files without writing them to disk.
* Validation Simulation: Checks filenames. If a file is uploaded, the mock marks its
  corresponding domain as active. If a file is omitted (e.g., `obligations.csv`),
  the mock flags that domain as bypassed.
* Delay Emulation: Uses `asyncio.sleep(0.4)` to simulate non-blocking disk parsing.

5.3 Mock SSE Telemetry Generator Stub
When the browser connects to `GET /api/v1/analysis/stream/{run_id}`, the mock generator
yields a deterministic sequence of events over an 8-second execution profile:
```python
# Pseudo-code specification for Mock SSE Generator
async def mock_event_stream(run_id: UUID, active_domains: dict):
    yield sse_event("LOG_EMITTED", {"severity": "INFO", "message": "Validating CSV file schemas..."})
    await asyncio.sleep(1.0)
    
    yield sse_event("PIPELINE_STAGE_CHANGED", {"stage": "GRAPH_PERSISTENCE", "progress_percentage": 25})
    yield sse_event("LOG_EMITTED", {"severity": "INFO", "message": "Populating relational entity graph in PostgreSQL..."})
    await asyncio.sleep(1.5)
    
    yield sse_event("PIPELINE_STAGE_CHANGED", {"stage": "SUBMODULE_EVALUATION", "progress_percentage": 50})
    
    # Iterate through Submodules 4.1 to 4.9
    submodules = [
        ("OS_4_1", "Ownership Structure", active_domains.get("shareholders", True)),
        ("WPR_4_2", "Web Reputation", True),
        ("MSR_4_3", "Macro Sector Risk", True),
        ("CD_4_4", "Client Dependency", active_domains.get("invoices", True)),
        ("SD_4_5", "Supplier Dependency", active_domains.get("invoices", True)),
        ("ICR_4_6", "Immediate Cash Readiness", active_domains.get("accounts", True)),
        ("CFS_4_7", "Cash Flow Stability", active_domains.get("transactions", True)),
        ("RQ_4_8", "Receivables Quality", active_domains.get("invoices", True)),
        ("ICDL_4_9", "Credit Discipline & Leverage", active_domains.get("obligations", True)),
    ]
    
    for sub_id, name, is_active in submodules:
        if is_active:
            yield sse_event("LOG_EMITTED", {"severity": "INFO", "message": f"Executing Submodule {name}..."})
            await asyncio.sleep(0.4)
            yield sse_event("SUBMODULE_STATUS_UPDATED", {"submodule_id": sub_id, "status": "SUCCESS", "verdict": "NOMINAL"})
        else:
            yield sse_event("LOG_EMITTED", {"severity": "WARN", "message": f"Data absent. Bypassing Submodule {name}."})
            yield sse_event("SUBMODULE_STATUS_UPDATED", {"submodule_id": sub_id, "status": "BYPASSED", "verdict": "DATA_ABSENT"})
            await asyncio.sleep(0.2)
            
    yield sse_event("PIPELINE_STAGE_CHANGED", {"stage": "LLM_SYNTHESIS", "progress_percentage": 85})
    yield sse_event("LOG_EMITTED", {"severity": "INFO", "message": "Synthesizing full underwriter dossier via LLM..."})
    await asyncio.sleep(2.0)
    
    yield sse_event("PIPELINE_COMPLETE", {
        "run_id": str(run_id),
        "universal_score": 78.45,
        "redirect_url": f"/analyze/report/{run_id}"
    })

```

5.4 Mock Submodule Results & Feature Vector Payload
When the frontend fetches `/api/v1/analysis/report/{run_id}`, the stub returns this
comprehensive mock JSON payload matching the target production contract:

```json
{
  "run_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "company_name": "Moldova Agrotech Solutions S.R.L.",
  "tax_id": "1003600045123",
  "industry_code": "A.01.11",
  "execution_status": "COMPLETED",
  "universal_score": 78.45,
  "verdict_category": "MODERATE_MONITORED",
  "created_at": "2026-09-17T14:30:00Z",
  "completed_at": "2026-09-17T14:30:08Z",
  "feature_vector": {
    "ownership_dispersion_index": 65.0,
    "governance_independence_index": 45.0,
    "legal_cleanliness_index": 92.0,
    "public_reputation_index": 80.0,
    "sector_vitality_index": 71.5,
    "client_diversification_index": 48.0,
    "top_client_exposure_index": 52.0,
    "supplier_diversification_index": 84.0,
    "supply_chain_robustness_index": 76.0,
    "cash_readiness_index": 82.5,
    "runway_buffer_index": 75.0,
    "revenue_predictability_index": 88.0,
    "revenue_trajectory_index": 62.0,
    "receivables_safety_index": 70.0,
    "client_payment_discipline_index": 64.0,
    "debt_repayment_discipline_index": 95.0,
    "debt_service_coverage_index": 85.0,
    "solvency_leverage_index": 77.0
  },
  "llm_synthesis": {
    "headline": "Financially resilient enterprise with isolated counterparty concentration risk.",
    "summary_markdown": "The enterprise exhibits **robust operating cash flow** and strong baseline liquidity, maintaining approximately 45 days of operational runway. Debt servicing discipline remains exemplary with zero 90-day defaults. However, the business is structurally vulnerable to **client revenue concentration**: the top client accounts for 48% of annual B2B receivables, introducing severe cash gap vulnerability if contractual settlements slip past 30 days.",
    "critical_flags": [
      "Top customer represents 48% of total gross receivables.",
      "Board governance lacks independent non-executive directors."
    ],
    "positive_indicators": [
      "Cash Ratio is 1.65, comfortably covering short-term operational liabilities.",
      "Debt Service Coverage Ratio (DSCR) is sustained at 2.1x."
    ]
  },
  "submodules": [
    {
      "submodule_id": "OS_4_1",
      "name": "Ownership Structure",
      "status": "SUCCESS",
      "verdict": "CONCENTRATED_OWNERSHIP",
      "impact_weight": 0.08,
      "indices": {
        "Ownership Dispersion Index": 65.0,
        "Governance Independence Index": 45.0
      },
      "dry_report": "[SUBMODULE 4.1: OWNERSHIP STRUCTURE]\nVERDICT: CONCENTRATED_OWNERSHIP\nIMPACT WEIGHT: 0.08\nNUMERICAL INDICES:\n- Ownership Dispersion Index: 65.0 / 100.0\n- Governance Independence Index: 45.0 / 100.0\nSUMMARY: HHI_Shareholders calculated at 3500. Management holds 80% of equity. Independent directors occupy 0 of 3 seats."
    },
    {
      "submodule_id": "WPR_4_2",
      "name": "Web Presence & Legal Reputation",
      "status": "SUCCESS",
      "verdict": "LEGAL_INTEGRITY_CONFIRMED",
      "impact_weight": 0.12,
      "indices": {
        "Legal Cleanliness Index": 92.0,
        "Public Reputation Index": 80.0
      },
      "dry_report": "[SUBMODULE 4.2: WEB PRESENCE & LEGAL REPUTATION]\nVERDICT: LEGAL_INTEGRITY_CONFIRMED\nIMPACT WEIGHT: 0.12\nNUMERICAL INDICES:\n- Legal Cleanliness Index: 92.0 / 100.0\n- Public Reputation Index: 80.0 / 100.0\nSUMMARY: Identified 0 active lawsuits. Sanctions check: PASS. News sentiment classified at +0.600."
    },
    {
      "submodule_id": "ICR_4_6",
      "name": "Immediate Cash Readiness",
      "status": "SUCCESS",
      "verdict": "LIQUID_AND_SOLVENT",
      "impact_weight": 0.15,
      "indices": {
        "Cash Readiness Index": 82.5,
        "Runway Buffer Index": 75.0
      },
      "dry_report": "[SUBMODULE 4.6: IMMEDIATE CASH READINESS]\nVERDICT: LIQUID_AND_SOLVENT\nIMPACT WEIGHT: 0.15\nNUMERICAL INDICES:\n- Cash Readiness Index: 82.5 / 100.0\n- Runway Buffer Index: 75.0 / 100.0\nSUMMARY: Available liquidity: 1,450,000 MDL. Immediate 30-day obligations: 880,000 MDL. Cash Ratio is 1.65. Company maintains 45 days cash runway."
    },
    {
      "submodule_id": "ICDL_4_9",
      "name": "Internal Credit Discipline & Leverage",
      "status": "BYPASSED",
      "verdict": "DATA_ABSENT",
      "impact_weight": 0.16,
      "indices": {
        "Debt Repayment Discipline Index": null,
        "Debt Service Coverage Index": null,
        "Solvency Leverage Index": null
      },
      "dry_report": "[SUBMODULE 4.9: INTERNAL CREDIT DISCIPLINE & LEVERAGE]\nSTATUS: DATA_ABSENT\nVERDICT: BYPASSED\nSUMMARY: No credit obligations file provided. Submodule execution skipped."
    }
  ]
}

```

6. FRONTEND MOCK CLIENT SPECIFICATION (JS/ALPINE.JS)

When running in UI development mode without a running FastAPI backend, the
frontend implements an in-memory client mock service.

6.1 Client Mock Service Implementation (/static/js/mock_service.js)

    Intercepts fetch('/api/v1/analysis/start') via service worker or wrapper method:
    Immediately stores mock company data in sessionStorage and returns a static UUID.

    Mock EventSource Replacement:
    Replaces browser EventSource with a synthetic timer emitting DOM CustomEvents
    matching the exact event signatures defined in Section 4.3.

    Static Dossier Binding:
    Loads the JSON payload defined in Section 5.4 directly into Alpine.js store
    Alpine.store('reportData'), allowing complete UI styling, gauge rendering,
    card collapsing, and CSS layout polish prior to backend completion.

    SECURITY, ERROR RECOVERY & PRODUCTION READINESS

7.1 CSRF & CORS Policy

    Cross-Origin Resource Sharing is restricted strictly to designated internal origins.

    CSRF Double-Submit Cookie patterns are enforced for all state-changing endpoints
    (/api/v1/analysis/start, /api/v1/auth/login).

7.2 Ingestion Boundaries & DoS Prevention

    File upload streams are throttled by StreamingUploadMiddleware to prevent memory
    exhaustion. Maximum individual file ceiling is fixed at 50 megabytes.

    CSV parser reads chunks into temporary spool files rather than buffering full
    datasets into heap RAM.

7.3 Graceful Pipeline Abort

    If the user closes the browser during execution, the frontend sends a navigator.sendBeacon
    signal to /api/v1/analysis/abort/{run_id}.

    The backend terminates running async child processes and marks the job status
    in analysis_runs as ABORTED_BY_USER, releasing database connection pool workers.
    ================================================================================
    END OF SPECIFICATION
    ================================================================================
