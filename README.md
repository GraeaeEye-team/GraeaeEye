# GraeaeEye: Explainable SME Underwriting Engine

## What It Is
GraeaeEye is a rule-based underwriting scorecard that evaluates SME financing readiness through modular financial analysis. It identifies liquidity, debt, receivables, and concentration risks, explains contributing factors, and flags incomplete cases for human review.

**Current implementation:** deterministic rule-based scoring (not ML/AI). Weights and thresholds are expert-defined. No trained models, no ground truth validation yet.

---

## Architecture (Phase 1-2 Complete)

### Core Components (DONE)
- **9 Financial Submodules** (OS, WPR, MSR, CD, SD, ICR, CFS, RQ, ICDL): evaluate ownership structure, web reputation, macro risk, client/supplier dependency, cash readiness/stability, receivables quality, credit discipline
- **18D Feature Vector**: canonical financial indices (liquidity, leverage, concentration, coverage, and stability metrics)
- **Scoring Engine**: weighted average with dynamic renormalization for missing data
- **PostgreSQL DAL**: 57-method async interface with parameterized queries and in-memory mock fallback
- **Real Auth**: Argon2id password hashing, JWT session tokens, secure HttpOnly cookies, and seed dev user
- **Real Orchestration**: CSV ingestion → DB → ML analytical pipeline → SSE telemetry → persisted report
- **Regression Shield**: 57 automated tests (contract, integration, fixtures) + GitHub Actions CI

### Two Modes
- `USE_MOCK_ENGINE=true` (dev/demo): synthetic data, fast iteration, in-memory fixtures
- `USE_MOCK_ENGINE=false` (production): real PostgreSQL + analytical pipeline execution

---

## Quick Start

### Option 1: Local Development (Recommended)

```bash
# Clone
git clone https://github.com/GraeaeEye-team/GraeaeEye.git
cd GraeaeEye

# Install dependencies
python -m venv venv
source venv/bin/activate  # Windows: .\venv\Scripts\activate
pip install -r requirements.txt

# Set environment
export PYTHONPATH=src
export USE_MOCK_ENGINE=true
export SECRET_KEY=dev-secret-change-in-production

# Seed dev user
python -m scripts.seed_dev_user

# Run server
uvicorn fintech_app.main:app --reload --port 8000

# Open Swagger UI
open http://localhost:8000/docs
```

### Option 2: Docker Compose

```bash
# Build and start services (PostgreSQL + Backend + Backup Daemon)
docker compose up -d --build

# Health check
curl -f http://localhost:8000/health

# View live logs
docker compose logs -f backend

# Stop services
docker compose down
```

---

## API Endpoints

All primary application routes are versioned under `/api/v1`:

### Authentication (`/api/v1/auth`)
- `POST /api/v1/auth/register` — Register a new analyst account (Argon2id password hashing, email validation).
- `POST /api/v1/auth/token` — Authenticate analyst credentials, set `session_token` HttpOnly cookie.

### Analysis (`/api/v1/analysis`)
- `POST /api/v1/analysis/start` — Initiate underwriting run with up to 5 financial CSV files (multipart form upload).
- `GET /api/v1/analysis/stream/{run_id}` — Real-time Server-Sent Events (SSE) progress telemetry.
- `GET /api/v1/analysis/report/{run_id}` — Full structured underwriting report with 18D canonical feature vector and subscores.

### Health
- `GET /health` — Service health check endpoint.

---

## Fixture Data

The repository includes contrasting financial profiles under `data/fixtures/` designed to validate the scoring engine across distinct risk tiers:

- **`GOOD_SME`** (`data/fixtures/good_sme/`):
  - Strong liquidity (Cash Ratio ≈ 5.0, Current Assets: 1.5M, Current Liabilities: 300k).
  - Clean receivables, negligible aging/overdue accounts.
  - Flawless credit discipline (0 past-due counts, 0 historical defaults).
  - Target Score: `universal_score >= 75` (`PRIME_LOW_RISK`, `APPROVED`).
- **`RISKY_SME`** (`data/fixtures/risky_sme/`):
  - Severe liquidity strain (Cash Ratio ≈ 0.25, Current Assets: 200k, Current Liabilities: 800k).
  - High client concentration (>70%), frequent negative bank balances.
  - Chronic past-due receivables, historical defaults, high debt service load.
  - Target Score: `universal_score <= 55` (`HIGH_RISK_REJECT`, `REJECTED`).

### Seeding Fixtures
To populate the database with these profiles idempotently:
```bash
python -m scripts.seed_fixtures
```

---

## Testing

GraeaeEye features a 57-test regression shield validating contracts, business logic, and in-process orchestration:

```bash
# Run the complete test suite
pytest -q

# Contract tests (18D feature vector order, P10 error envelope, status codes)
pytest tests/test_contracts.py -v

# Integration tests (GOOD_SME vs RISKY_SME contrast, degraded mode, idempotent seeding)
pytest tests/test_integration.py -v

# Authentication and security tests
pytest tests/test_gate4_auth.py -v

# Orchestration and SSE pipeline tests
pytest tests/test_gate3_orchestration.py -v

# Static analysis
ruff check src/ tests/
```

### Continuous Integration (CI)
GitHub Actions workflow in [`.github/workflows/ci.yml`](.github/workflows/ci.yml) validates every pull request:
1. **`test` Job**: Runs Ruff linting and the complete Pytest suite with zero warnings allowed.
2. **`docker-smoke` Job**: Builds the docker container stack and verifies container health.

---

## Roadmap

- [x] **Phase 1: Architecture & Mock Engine (DONE)**:
  - Canonical 18D financial feature vector definition.
  - Strict P10 error envelopes (`{"detail": str, "code": str}`).
  - 9 rule-based financial analysis submodules with dynamic renormalization.
  - In-memory mock provider with synthetic telemetry and reports.
- [x] **Phase 2: Real In-Process Integration (DONE)**:
  - 57-method PostgreSQL Data Access Layer (DAL) with parameterized queries.
  - Real Argon2id authentication and signed HS256 JWT session management.
  - Multipart CSV ingestion pipeline (accounts, transactions, invoices, credit obligations, shareholders).
  - Real orchestration wiring: Ingestion → DAL → Scoring Engine → SSE Telemetry → Report.
  - `GOOD_SME` / `RISKY_SME` contrasting benchmark fixtures with automated seed script.
  - 57-test regression shield + GitHub Actions CI workflow.
- [ ] **Phase 3: Advanced Capabilities & Machine Learning (FUTURE)**:
  - **Empirical ML Training**: Transition from expert-defined rules to supervised ML models (e.g. LightGBM, CatBoost) trained on empirical default outcomes.
  - **Advanced Explainability**: Calibrated SHAP / Integrated Gradients on trained models.
  - **Cash Flow Forecasting**: Time-series predictive models with confidence intervals on 30/60/90-day horizons.
  - **Interactive Scenario Engine**: What-If stress simulations for payment delays and macroeconomic shocks.
  - **Security & Multi-Tenancy**: CSRF protection, rate limiting, and tenant-isolated database schemas.
  - **Frontend Interface**: Dedicated web UI with real-time SSE chart rendering.

---

## Limitations (Honest Disclosure)

In alignment with engineering integrity and transparent system positioning, the current limitations of the system are explicitly acknowledged:

1. **No Trained ML Model Yet**: The current analytical pipeline uses deterministic, expert-crafted arithmetic rules. There are no weights learned from empirical training data.
2. **No Ground-Truth Validation**: Risk score bands (`PRIME_LOW_RISK`, `MODERATE_RISK_REVIEW`, `HIGH_RISK_REJECT`) and threshold cutoffs have not yet been calibrated against historical SME default datasets or verified by external rating agencies.
3. **Pseudo-SHAP (Not Real SHAP)**: Feature importance values and directional impacts are currently calculated using normalized heuristic distance-from-median metrics rather than true Shapley values computed over game-theoretic model predictions.
4. **Limited Production Ingestion**: Ingestion currently handles structured CSV tables. OCR for scanned PDF bank statements, semi-structured Excel spreadsheets, and direct banking API integrations are not yet implemented.
5. **No Frontend**: The platform currently operates strictly as a backend service accessible via REST API and Swagger UI.
6. **Mock Mode Default**: `USE_MOCK_ENGINE` defaults to `true` in local development configurations to allow instant demonstration without an active PostgreSQL instance.

---

## Team

- **Team Lead & DevOps**: CI/CD pipelines, Docker infrastructure, architecture alignment, code review.
- **Backend Developer**: FastAPI application, DAL implementation, PostgreSQL schema, authentication & session management.
- **Data Engineer**: Data ingestion pipeline, file format parsing, data normalization, database fixtures.
- **ML / Quant Engineer**: Financial submodule metrics, 18D feature vector design, rule-based scorecard algorithms, explanation heuristics.
- **Frontend / Integration Engineer**: Contract mapping, API client integration, UI mockups, and reporting specifications.

---

## License

MIT License
