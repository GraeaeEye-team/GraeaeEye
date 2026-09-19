-- =============================================================================
-- SMART CREDIT SYSTEM: CANONICAL RELATIONAL SCHEMA (PostgreSQL 16)
-- Target: src/fintech_app/db/schema.sql
-- Specification: docs/database_architecture-v2.md
-- =============================================================================

-- Включение расширения для генерации UUID v4 (в PG 16 функция gen_random_uuid() доступна из коробки)
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- =============================================================================
-- КЛАСТЕР 1: ЮРИДИЧЕСКАЯ ИДЕНТИЧНОСТЬ И СТРУКТУРА ВЛАДЕНИЯ (GOVERNANCE)
-- =============================================================================

-- 1. Предприятия / Заемщики
CREATE TABLE IF NOT EXISTS businesses (
    business_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tax_id VARCHAR(32) NOT NULL UNIQUE,
    legal_name VARCHAR(255) NOT NULL,
    industry_code VARCHAR(16) NOT NULL,
    registration_date DATE NOT NULL,
    total_board_seats INT NOT NULL DEFAULT 1 CHECK (total_board_seats >= 1),
    independent_directors_count INT NOT NULL DEFAULT 0 CHECK (independent_directors_count >= 0)
);

-- 2. Структура акционеров (Cap-Table)
CREATE TABLE IF NOT EXISTS shareholders (
    ownership_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    business_id UUID NOT NULL REFERENCES businesses(business_id) ON DELETE CASCADE,
    shareholder_name VARCHAR(255) NOT NULL,
    equity_percentage DECIMAL(5,2) NOT NULL CHECK (equity_percentage >= 0.00 AND equity_percentage <= 100.00),
    is_management_member BOOLEAN NOT NULL DEFAULT FALSE
);
CREATE INDEX IF NOT EXISTS idx_shareholders_biz ON shareholders(business_id);

-- =============================================================================
-- КЛАСТЕР 2: ВНЕШНЯЯ РАЗВЕДКА И МАКРОЭКОНОМИКА (EXTERNAL INTELLIGENCE)
-- =============================================================================

-- 3. Цифровая репутация и юридические риски (Срезы веб-сканирования)
CREATE TABLE IF NOT EXISTS web_reputation (
    record_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    business_id UUID NOT NULL REFERENCES businesses(business_id) ON DELETE CASCADE,
    scan_timestamp TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    active_lawsuits_count INT NOT NULL DEFAULT 0 CHECK (active_lawsuits_count >= 0),
    total_lawsuit_claims_amount DECIMAL(18,2) NOT NULL DEFAULT 0.00 CHECK (total_lawsuit_claims_amount >= 0.00),
    is_in_sanctions_list BOOLEAN NOT NULL DEFAULT FALSE,
    news_sentiment_score DECIMAL(4,3) CHECK (news_sentiment_score >= -1.000 AND news_sentiment_score <= 1.000),
    web_traffic_monthly_visits INT CHECK (web_traffic_monthly_visits >= 0)
);
CREATE INDEX IF NOT EXISTS idx_reputation_biz_time ON web_reputation(business_id, scan_timestamp DESC);

-- 4. Отраслевые макроэкономические метрики
CREATE TABLE IF NOT EXISTS macro_sector_metrics (
    metric_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    industry_code VARCHAR(16) NOT NULL,
    reference_date DATE NOT NULL,
    sector_growth_rate_yoy DECIMAL(5,2) NOT NULL,
    sector_default_rate DECIMAL(5,2) NOT NULL CHECK (sector_default_rate >= 0.00),
    risk_outlook_score INT NOT NULL CHECK (risk_outlook_score BETWEEN 1 AND 10)
);
CREATE INDEX IF NOT EXISTS idx_macro_sector_date ON macro_sector_metrics(industry_code, reference_date DESC);

-- =============================================================================
-- КЛАСТЕР 3: КОММЕРЧЕСКИЙ ГРАФ И ОПЕРАЦИОННЫЙ ДЕНЕЖНЫЙ ПОТОК (COMMERCIAL GRAPH)
-- =============================================================================

-- 5. Контрагенты (Покупатели и Поставщики)
CREATE TABLE IF NOT EXISTS counterparties (
    counterparty_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    business_id UUID NOT NULL REFERENCES businesses(business_id) ON DELETE CASCADE,
    tax_id VARCHAR(32),
    legal_name VARCHAR(255) NOT NULL,
    counterparty_role VARCHAR(16) NOT NULL CHECK (counterparty_role IN ('CLIENT', 'SUPPLIER', 'MIXED'))
);
CREATE INDEX IF NOT EXISTS idx_counterparties_biz ON counterparties(business_id);

-- 6. Коммерческие счета-фактуры (Дебиторская и Кредиторская задолженность)
CREATE TABLE IF NOT EXISTS invoices (
    invoice_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    business_id UUID NOT NULL REFERENCES businesses(business_id) ON DELETE CASCADE,
    counterparty_id UUID NOT NULL REFERENCES counterparties(counterparty_id) ON DELETE CASCADE,
    invoice_type VARCHAR(16) NOT NULL CHECK (invoice_type IN ('RECEIVABLE', 'PAYABLE')),
    gross_amount DECIMAL(18,2) NOT NULL CHECK (gross_amount >= 0.00),
    issue_date DATE NOT NULL,
    due_date DATE NOT NULL,
    actual_payment_date DATE,
    status VARCHAR(16) NOT NULL CHECK (status IN ('PAID', 'OUTSTANDING', 'OVERDUE', 'DEFAULTED'))
);
CREATE INDEX IF NOT EXISTS idx_invoices_biz_status ON invoices(business_id, status);
CREATE INDEX IF NOT EXISTS idx_invoices_due_date ON invoices(due_date);
CREATE INDEX IF NOT EXISTS idx_invoices_counterparty ON invoices(counterparty_id);

-- 7. Банковские расчетные счета
CREATE TABLE IF NOT EXISTS bank_accounts (
    account_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    business_id UUID NOT NULL REFERENCES businesses(business_id) ON DELETE CASCADE,
    currency VARCHAR(3) NOT NULL DEFAULT 'MDL',
    current_balance DECIMAL(18,2) NOT NULL,
    overdraft_limit DECIMAL(18,2) NOT NULL DEFAULT 0.00 CHECK (overdraft_limit >= 0.00)
);
CREATE INDEX IF NOT EXISTS idx_accounts_biz ON bank_accounts(business_id);

-- 8. Банковские выписки (Транзакции)
CREATE TABLE IF NOT EXISTS transactions (
    transaction_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    business_id UUID NOT NULL REFERENCES businesses(business_id) ON DELETE CASCADE,
    account_id UUID NOT NULL REFERENCES bank_accounts(account_id) ON DELETE CASCADE,
    counterparty_id UUID REFERENCES counterparties(counterparty_id) ON DELETE SET NULL,
    invoice_id UUID REFERENCES invoices(invoice_id) ON DELETE SET NULL,
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
    amount DECIMAL(18,2) NOT NULL CHECK (amount >= 0.00),
    direction VARCHAR(8) NOT NULL CHECK (direction IN ('INFLOW', 'OUTFLOW')),
    category VARCHAR(32) NOT NULL CHECK (category IN (
        'REVENUE', 'OPERATING_EXPENSE', 'PAYROLL', 'TAX', 'DEBT_SERVICE', 'DIVIDEND', 'OTHER'
    )),
    liquidity_class VARCHAR(24) NOT NULL DEFAULT 'IMMEDIATE_CASH' CHECK (liquidity_class IN (
        'IMMEDIATE_CASH', 'RESTRICTED_ESCROW', 'TERM_DEPOSIT'
    ))
);
CREATE INDEX IF NOT EXISTS idx_trans_biz_time ON transactions(business_id, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_trans_cat ON transactions(category);
CREATE INDEX IF NOT EXISTS idx_trans_account ON transactions(account_id);

-- =============================================================================
-- КЛАСТЕР 4: КРЕДИТНЫЕ ОБЯЗАТЕЛЬСТВА И ДОЛГОВАЯ ДИСЦИПЛИНА (LIABILITIES)
-- =============================================================================

-- 9. Кредиты, лизинги и кредитные линии
CREATE TABLE IF NOT EXISTS credit_obligations (
    obligation_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    business_id UUID NOT NULL REFERENCES businesses(business_id) ON DELETE CASCADE,
    lender_name VARCHAR(255) NOT NULL,
    facility_type VARCHAR(32) NOT NULL CHECK (facility_type IN ('TERM_LOAN', 'LEASING', 'LINE_OF_CREDIT')),
    principal_amount DECIMAL(18,2) NOT NULL CHECK (principal_amount >= 0.00),
    outstanding_balance DECIMAL(18,2) NOT NULL CHECK (outstanding_balance >= 0.00),
    monthly_payment DECIMAL(18,2) NOT NULL CHECK (monthly_payment >= 0.00),
    past_due_30d_count INT NOT NULL DEFAULT 0 CHECK (past_due_30d_count >= 0),
    past_due_90d_count INT NOT NULL DEFAULT 0 CHECK (past_due_90d_count >= 0),
    historical_defaults_count INT NOT NULL DEFAULT 0 CHECK (historical_defaults_count >= 0)
);
CREATE INDEX IF NOT EXISTS idx_obligations_biz ON credit_obligations(business_id);

-- =============================================================================
-- КЛАСТЕР 5: ВЕБ-ПРИЛОЖЕНИЕ, ПОЛЬЗОВАТЕЛИ И ТЕЛЕМЕТРИЯ (ORCHESTRATION & RUNS)
-- =============================================================================

-- 10. Пользователи системы (Андеррайтеры / Аналитики)
CREATE TABLE IF NOT EXISTS users (
    user_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    full_name VARCHAR(128) NOT NULL,
    role VARCHAR(32) NOT NULL DEFAULT 'ANALYST' CHECK (role IN ('ADMIN', 'UNDERWRITER', 'ANALYST')),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- 11. Пользовательские настройки интерфейса
CREATE TABLE IF NOT EXISTS user_settings (
    setting_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL UNIQUE REFERENCES users(user_id) ON DELETE CASCADE,
    ui_theme VARCHAR(16) NOT NULL DEFAULT 'system' CHECK (ui_theme IN ('light', 'dark', 'system')),
    terminal_sound_effects BOOLEAN NOT NULL DEFAULT FALSE,
    auto_expand_reports BOOLEAN NOT NULL DEFAULT TRUE
);

-- 12. Сессии и задачи анализа (Analysis Runs)
CREATE TABLE IF NOT EXISTS analysis_runs (
    run_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    business_id UUID REFERENCES businesses(business_id) ON DELETE SET NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'QUEUED' CHECK (status IN (
        'QUEUED', 'PARSING', 'PROCESSING', 'COMPLETED', 'FAILED', 'DEGRADED'
    )),
    input_company_name VARCHAR(255) NOT NULL,
    input_tax_id VARCHAR(32) NOT NULL,
    input_industry_code VARCHAR(16) NOT NULL,
    files_manifest JSONB NOT NULL DEFAULT '{}'::jsonb,
    active_submodules JSONB NOT NULL DEFAULT '[]'::jsonb,
    raw_indices_payload JSONB,
    submodules_reports JSONB,
    llm_final_summary TEXT,
    universal_score DECIMAL(5,2) CHECK (universal_score >= 0.00 AND universal_score <= 100.00),
    failure_reason TEXT,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMP WITH TIME ZONE
);
CREATE INDEX IF NOT EXISTS idx_runs_user_date ON analysis_runs(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_runs_status ON analysis_runs(status);

-- 13. Логи выполнения пайплайна (SSE Streaming Telemetry)
CREATE TABLE IF NOT EXISTS analysis_logs (
    log_id BIGSERIAL PRIMARY KEY,
    run_id UUID NOT NULL REFERENCES analysis_runs(run_id) ON DELETE CASCADE,
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    severity VARCHAR(16) NOT NULL CHECK (severity IN ('DEBUG', 'INFO', 'WARN', 'ERROR')),
    stage VARCHAR(32) NOT NULL,
    message TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_logs_run_seq ON analysis_logs(run_id, timestamp ASC);


