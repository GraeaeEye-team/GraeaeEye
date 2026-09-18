================================================================================
SMART CREDIT SYSTEM: ENGINEERING STANDARDS, TEAM WORKFLOW & DEVELOPMENT RULES
TECHNICAL SPECIFICATION & TEAM WORKFLOW GOVERNANCE (V2.1)
================================================================================

1. ONBOARDING & DEVELOPER ORIENTATION: THE ARCHITECTURAL PHILOSOPHY
--------------------------------------------------------------------------------
1.1 The Fundamental Problem: Why SMEs Fail ("Profit != Cash")
Small and Medium Enterprises (SMEs) are the backbone of emerging economies such
as Moldova, yet they face chronic hurdles accessing credit[cite: 2, 4]. Traditional
underwriting relies almost exclusively on static annual accounting statements[cite: 2, 4].
These financial statements suffer from a critical flaw: they act as a rear-view
mirror[cite: 3]. 

In operational reality, accounting profit does not equal liquid cash[cite: 3]. An
enterprise can win a lucrative commercial contract and record immense paper profit,
yet simultaneously slide into catastrophic default because payment is deferred by
60 days while payroll, taxes, and server costs must be settled in 5 days[cite: 3].
Traditional bank scoring notices this distress only after loan installments fail[cite: 2, 3].
The Smart Credit System replaces this retrospective view with a forward-looking
early-warning radar that identifies cash gaps, customer payment slippage, and
structural insolvency risks weeks before they materialize[cite: 2, 3].

1.2 How The System Works: From Raw Records to Investment Verdict
The engine does not treat financial data as flat spreadsheets[cite: 3]. It operates as
an integrated, multi-stage intelligence pipeline:
1. Ingestion & Graph Construction: Raw CSV tables covering bank statements, accounts,
   commercial trade invoices, and credit facilities are mapped into an interconnected
   PostgreSQL entity graph[cite: 3, 4, 5]. Instead of viewing transactions in isolation,
   the graph links each transfer to its underlying invoice, counterparty, and contractual
   terms[cite: 3, 5].
2. Decoupled Submodule Evaluation: Rather than feeding messy raw tables directly into
   a machine learning model, the analytical core divides evaluation into 9 autonomous,
   single-responsibility submodules[cite: 1, 5]. Each submodule examines a distinct
   operational facet (e.g., immediate cash readiness, supplier dependency, shareholder
   concentration)[cite: 1, 5].
3. Dual-Output Production: Every active submodule yields two outputs:
   - A dry, structured human-readable text report detailing verdicts and weights[cite: 1, 5].
   - Standardized numerical indices bounded strictly between 0.0 and 100.0[cite: 1, 5].
4. Aggregation & Synthesis: The normalized indices form an 18-element feature vector
   consumed downstream by supervised gradient-boosted decision trees to predict default
   probabilities[cite: 1, 4, 5]. Simultaneously, an integrated LLM synthesizes the
   submodule text reports into a coherent, executive-level Underwriting Dossier for
   credit analysts[cite: 2, 3, 5].

1.3 The Four Golden Rules of Team Engineering
To develop this platform concurrently across 5 engineers without friction, every
contributor must commit to four core operating principles:
* Rule 1: Never Block a Teammate (The Functional Mock Stub Mandate).
  If your module depends on a function or table that another team member has not
  finished writing, DO NOT raise `NotImplementedError` and DO NOT wait idly[cite: 5].
  Implement a deterministic mock stub returning synthetic, schema-valid data[cite: 3, 5].
  Your code, the web interface, and ingestion pipelines must always run cleanly[cite: 3, 5].
* Rule 2: Single Relational Source of Truth.
  PostgreSQL is the sole persistence authority[cite: 1, 5]. Modules do not exchange
  loose CSV files or global Python variables[cite: 3, 5]. All data writes and reads
  must execute exclusively through the asynchronous `Database` class methods in
  `db/connection.py`, returning standardized `DatabaseReport` containers[cite: 5].
* Rule 3: Continuous Integration Over "Big Bang" Merges.
  Never hoard code in an isolated personal branch for days[cite: 3]. Large delayed
  merges generate irreconcilable merge conflicts and logic regressions[cite: 3].
  Commit small, atomic changes and submit daily Pull Requests into the shared `dev`
  branch[cite: 3].
* Rule 4: Git as the Sole Communication Channel.
  Never share function signatures, models, or snippets via private chat messages[cite: 3].
  If an interface must change, declare the change in code, push a branch, and open
  a pull request[cite: 3]. If it is not in the Git repository, it does not exist.


2. TEAM ROSTER & SUBSYSTEM OWNERSHIP MATRIX
--------------------------------------------------------------------------------
Each developer maintains primary ownership over a designated module while conforming
to shared cross-module contracts[cite: 3].

+-------------------+----------------------+-----------------------------------+
| Developer Handle  | Core Domain          | Primary Technical Responsibilities|
+-------------------+----------------------+-----------------------------------+
| @newgopro         | Lead Architect,      | PostgreSQL schema design,         |
|                   | Database & DevOps    | `db/connection.py` DAL, Docker,   |
|                   |                      | PR merges, system integration[cite: 3, 5].   |
+-------------------+----------------------+-----------------------------------+
| @egordjundiet     | Web Backend &        | FastAPI orchestration, session    |
|                   | Pipeline Runtime     | auth, SSE log streaming, module   |
|                   |                      | invocation background tasks[cite: 3, 5].      |
+-------------------+----------------------+-----------------------------------+
| @Xtnray           | Web Frontend &       | UI templates, JS interactivity,   |
|                   | Client UX            | CSS/Tailwind layouts, animations, |
|                   |                      | client-side mock service (/static)|
+-------------------+----------------------+-----------------------------------+
| @ozzyrastamouse   | Ingestion Engine     | Raw CSV parsers, schema mapping,  |
|                   | & Data Processing    | validation, writing ingested      |
|                   |                      | batches to DB via DAL[cite: 3, 4, 5].         |
+-------------------+----------------------+-----------------------------------+
| @Mr-Ressentiment  | Analytical Core &    | Submodules 4.1-4.9 financial      |
|                   | Quantitative Scoring | algorithms, HHI/cash calculations,|
|                   |                      | LLM prompt synthesis pipeline[cite: 1, 5].    |
+-------------------+----------------------+-----------------------------------+


3. STANDARDIZED TECHNICAL STACK & RUNTIME ENVIRONMENT
--------------------------------------------------------------------------------
To eliminate environmental divergence ("it works on my machine"), all team members
must execute within an identical runtime boundary[cite: 3].

3.1 Runtime Baseline
* Python Version: Python 3.12.x (Mandatory: utilizes native `StrEnum`, enhanced
  AsyncIO speed, and refined type hinting).
* Dependency Manager: Centralized `requirements.txt` placed at the project root.
* Container Engine: Docker and Docker Compose (`Dockerfile`, `docker-compose.yml`)[cite: 3].

3.2 Central Dependency Manifest (`requirements.txt`)
All dependencies are pinned to compatible minor versions:
```text
# Web Framework & Networking
fastapi>=0.110.0,<0.111.0
uvicorn[standard]>=0.28.0,<0.29.0
python-multipart>=0.0.9

# Asynchronous Database Driver & Pool
psycopg[binary]>=3.1.18,<3.2.0
psycopg-pool>=3.2.1,<3.3.0

# Mathematical Modeling, DataFrames & Parsing
pandas>=2.2.1,<2.3.0
numpy>=1.26.4,<1.27.0
scipy>=1.12.0,<1.13.0

# LLM Integrations & AI Middleware
openai>=1.14.1,<1.15.0
ollama>=0.1.7,<0.2.0

# Code Quality & Tooling
ruff>=0.3.2,<0.4.0
pydantic>=2.6.4,<2.7.0

```

3.3 Configuration Management (`.env` & `.env.example`)
All environment configurations must be loaded via Pydantic Settings or `os.getenv`.
No secret credentials or database connection strings may be hardcoded.
Standard `.env.example` contract:

```ini
# Application Runtime Configuration
APP_ENV=development
LOG_LEVEL=INFO
SECRET_KEY=change_me_in_production
USE_MOCK_ENGINE=true

# PostgreSQL Connection Parameters
POSTGRES_SERVER=localhost
POSTGRES_PORT=5432
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres
POSTGRES_DB=graeae_eye_db

# External LLM Engine Settings
OPENAI_API_KEY=your_api_key_here
LLM_MODEL=gpt-4o-mini
OLLAMA_HOST=http://localhost:11434

```

3.4 Frontend Asset Topology

* Architecture: Vanilla HTML5, modern vanilla JavaScript (ES6+), and utility-first CSS.
* Static Path: Assets must reside strictly within the `/static` root directory.
* `/static/css/`: Global stylesheets and framework dists.
* `/static/js/`: Modular scripts (e.g., `api_client.js`, `mock_service.js`, `telemetry.js`).
* `/static/assets/`: Fonts, brand graphics, SVG entity icons.



4. GIT WORKFLOW, BRANCHING STRATEGY & COLLABORATION DISCIPLINE

---

4.1 Branch Topology
The repository employs a two-tier trunk model with strict isolation:

* `main`: Protected production trunk. Represents demonstrably stable, demo-ready code.
Direct pushes and broken builds are strictly forbidden.


* `dev`: Primary integration trunk. All feature branches merge here via validated
Pull Requests (PRs).


* Feature Branches: Created exclusively off `dev` using standard taxonomic naming:
* `feature/ui-frontend`       (@Xtnray)
* `feature/backend-api`       (@egordjundiet)
* `feature/data-parser`       (@ozzyrastamouse)
* `feature/analytical-core`   (@Mr-Ressentiment)
* `feature/database-dal`      (@newgopro)



4.2 Integration Cadence & Pull Request Policy

* Merge Frequency: Developers must sync with `dev` daily and open small, incremental
PRs rather than staging massive end-of-project merges.


* PR Validation: Every PR must:
1. Pass the code linter (`ruff check .`).
2. Contain no broken dependencies or merge conflicts.
3. Be reviewed and approved by the Lead Architect (@newgopro) or a relevant module peer.





4.3 Conventional Commits Standard
Commit messages must convey semantic purpose using conventional formatting:
`<type>(<scope>): <short imperative description>`

Allowed `<type>` prefixes:

* `feat`: A new end-user or architectural feature.
* `fix`: A bug fix in existing logic.
* `mock`: Implementing or expanding a mock stub or dummy dataset.
* `refactor`: Code modification that neither fixes a bug nor adds a feature.
* `docs`: Documentation, architecture notes, or README modifications.
* `chore`: Maintenance tasks, dependency updates, or git configuration.

Examples:

* `feat(dal): add asynchronous bulk insert for transactions`
* `mock(analytical-core): stub submodule 4.6 cash readiness output`
* `fix(parser): handle trailing empty commas in invoices.csv`

5. CONTRACT-FIRST DESIGN & MOCK STUB PROTOCOL

---

5.1 Absolute Prohibition of `NotImplementedError`
In an asynchronous, concurrent architecture, raising `NotImplementedError` inside
shared code paths crashes downstream callers with unhandled exceptions.

* RULE: When declaring an unwritten method in a shared module (such as `db/connection.py`),
developers MUST implement a functional Mock Stub that returns a valid, schema-compliant
contract object (`DatabaseReport`).



5.2 Standard Mock Stub Implementation Pattern
When a developer requires a new method from the Database module before it is officially
implemented by @newgopro:

```python
# CORRECT PATTERN: Functional Mock Stub in db/connection.py
async def add_record_to_bank_accounts(
    self,
    business_id: UUID,
    currency: str,
    current_balance: Decimal,
    overdraft_limit: Decimal = Decimal('0.00'),
    account_id: Optional[UUID] = None
) -> DatabaseReport:
    """
    STUB: Awaiting full SQL implementation by @newgopro.
    Currently returns a synthetic successful DatabaseReport.
    """
    mock_payload = {
        "account_id": account_id or uuid4(),
        "business_id": business_id,
        "currency": currency,
        "current_balance": current_balance,
        "overdraft_limit": overdraft_limit
    }
    
    # Return valid DatabaseReport to prevent downstream pipeline crashes
    return DatabaseReport(
        success=True,
        data=mock_payload,
        affected_rows=1,
        operation="INSERT",
        table_name="bank_accounts"
    )

# FORBIDDEN PATTERN: Unsafe stubbing
async def add_record_to_bank_accounts(self, *args, **kwargs):
    # THIS CRASHES FASTAPI RUNTIMES AND INGESTION WORKERS
    raise NotImplementedError("Egor/newgopro: write this later")

```

5.3 Cross-Module Contract Change Protocol
If a developer requires a structural change in an external module's interface:

1. Do NOT communicate the requirement solely via external chat.


2. Open the interface file in your local feature branch.
3. Declare the method signature accompanied by a functional mock stub.


4. Push the branch and open a draft PR against `dev` with the title:
`chore(contract): propose new DAL signature for bank account ingestion`.


5. Tag the responsible developer in the PR description.


6. CODE QUALITY, FORMATTING & TYPING STANDARDS

---

6.1 Static Typing Discipline

* All public functions, coroutines, and class methods must possess complete type
annotations for both arguments and return values.
* Ambiguous types (`Any`) are strictly reserved for unparsed raw JSON payloads.
Everywhere else, use explicit primitives, `UUID`, `Decimal`, `datetime`, or dataclasses.



6.2 Linter and Formatter Rules (`ruff`)
Code must adhere to PEP 8 standards enforced automatically via `ruff`.
Before committing code, developers must run:

```bash
ruff check . --fix
ruff format .

```

Line length limit is fixed at 100 characters.

6.3 Logging Discipline vs. Standard Output

* The use of standard `print()` statements in production code is strictly forbidden.
`print()` operations block asynchronous event loops and bypass structured logging sinks.
* All telemetry, informational status messages, and caught exceptions must utilize
the Python standard library `logging` module:

```python
import logging

logger = logging.getLogger("smart_credit.backend")

# CORRECT:
logger.info("Parsing initiated for business_id=%s", business_id)
logger.warning("Unmapped invoice category encountered: %s", raw_category)
logger.error("Database connection dropped during pipeline execution", exc_info=True)

```

7. DEVELOPER RUNBOOK & LOCAL ONBOARDING PROTOCOL

---

Every developer must follow this baseline protocol to establish an operational
local workspace:

1. Clone Repository and Switch to Integration Branch:
```bash
git clone <repository_url>
cd smart-credit-system
git checkout dev

```


2. Initialize Virtual Environment (Python 3.12):
```bash
python3.12 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install --upgrade pip
pip install -r requirements.txt

```


3. Environment Setup:
```bash
cp .env.example .env
# Modify local variables as necessary

```


4. Launch Database Infrastructure (via Docker Compose):
```bash
docker-compose up -d postgres

```


5. Launch Local Web Server:
```bash
uvicorn web.app:app --host 0.0.0.0 --port 8000 --reload

```


6. Create Personal Feature Branch:
```bash
git checkout -b feature/<your-assigned-subsystem>

```



# ================================================================================
END OF GOVERNANCE SPECIFICATION

```

```