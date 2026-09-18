================================================================================
SMART CREDIT SYSTEM: CORE INVESTMENT & UNDERWRITING ANALYTICAL ENGINE
TECHNICAL ARCHITECTURE & SPECIFICATION DOCUMENT (V2.0)
================================================================================

1. SYSTEM EXECUTIVE SUMMARY & ARCHITECTURAL PHILOSOPHY
--------------------------------------------------------------------------------
1.1 Mission and Objectives
The Core Analytical Engine evaluates the financial resilience, operational health,
and investment attractiveness of Small and Medium Enterprises (SMEs). Traditional
underwriting relies on historical financial statements ("rear-view mirror" metrics).
This engine is designed as a forward-looking early-warning system that synthesizes
internal operational cash flows, contractual B2B transaction graphs, historical
credit discipline, and external open-source intelligence.

1.2 Core Architectural Principles
* Decoupled Domain Isolation: The core engine is decomposed into 9 autonomous,
  single-responsibility submodules. Each submodule evaluates a distinct dimension
  of investment and credit risk.
* Fault-Tolerant Graceful Degradation: Submodules possess zero inter-submodule
  runtime dependencies. If underlying database records or external web scraping
  data are missing, corrupted, or incomplete for a specific domain, only the
  associated submodule safely skips execution (yielding null indicators). The
  remaining submodules continue uninterrupted.
* Dual-Output Contract: Every submodule executes deterministic financial,
  statistical, and heuristic algorithms to output:
  1. A standardized set of normalized numerical indices (bounded strictly 0.0 to 100.0).
  2. A structured, human-readable plain-text diagnostic report containing explicit
     verdicts, impact weight factors, and granular analytical breakdowns.
* Downstream ML Integration (Feature Space Provisioning): The normalized numerical
  indices across all active submodules form an aggregated feature vector. This
  feature vector is consumed downstream by supervised machine learning models
  (e.g., Gradient Boosted Decision Trees / LightGBM) to compute a unified Investment
  Attractiveness Score and Probability of Default (PD). ML training and model
  inference are decoupled from this analytical feature-extraction layer.


2. RELATIONAL DATA LAYER: POSTGRESQL GRAPH SCHEMA
--------------------------------------------------------------------------------
The data layer maps raw accounting records, bank ledgers, and external feeds into
a connected entity graph. Primary identifiers use RFC-4122 UUIDs. Monetary amounts
are stored as fixed-point DECIMAL(18,2) to eliminate floating-point rounding errors.

--------------------------------------------------------------------------------
CLUSTER 2.1: CORE CORPORATE IDENTITY & GOVERNANCE
--------------------------------------------------------------------------------
* Table: businesses
  Represents foundational corporate identity, incorporation status, and governance.
  - business_id (UUID, PK): Unique enterprise identifier.
  - tax_id (VARCHAR(32), UNIQUE, NOT NULL): State tax registration number.
  - legal_name (VARCHAR(255), NOT NULL): Registered corporate legal title.
  - industry_code (VARCHAR(16), NOT NULL): Standard sector classification (NACE/SIC).
  - registration_date (DATE, NOT NULL): Official date of legal establishment.
  - total_board_seats (INT, DEFAULT 1): Total seats on the board of directors.
  - independent_directors_count (INT, DEFAULT 0): Non-executive, external directors.

* Table: shareholders
  Represents equity cap-table distribution and managerial overlap.
  - ownership_id (UUID, PK): Unique record identifier.
  - business_id (UUID, FK -> businesses.business_id, NOT NULL): Target company.
  - shareholder_name (VARCHAR(255), NOT NULL): Individual or institutional entity.
  - equity_percentage (DECIMAL(5,2), NOT NULL): Equity holding (0.00% to 100.00%).
  - is_management_member (BOOLEAN, NOT NULL): Flags if owner holds executive roles.

--------------------------------------------------------------------------------
CLUSTER 2.2: EXTERNAL INTELLIGENCE & OPEN DATA
--------------------------------------------------------------------------------
* Table: web_reputation
  Time-stamped snapshots gathered by background scraping agents and external APIs.
  - record_id (UUID, PK): Unique snapshot identifier.
  - business_id (UUID, FK -> businesses.business_id, NOT NULL): Target company.
  - scan_timestamp (TIMESTAMP WITH TIME ZONE, NOT NULL): Time data was captured.
  - active_lawsuits_count (INT, DEFAULT 0): Open court/litigation cases (as defendant).
  - total_lawsuit_claims_amount (DECIMAL(18,2), DEFAULT 0.00): Monetary claims against firm.
  - is_in_sanctions_list (BOOLEAN, DEFAULT FALSE): Binary hit on AML/sanction watchlists.
  - news_sentiment_score (DECIMAL(4,3), NULL): NLP sentiment score (-1.000 to +1.000).
  - web_traffic_monthly_visits (INT, NULL): Estimated web portal traffic.

* Table: macro_sector_metrics
  Industry-level macroeconomic reference data linked via sector codes.
  - metric_id (UUID, PK): Unique record identifier.
  - industry_code (VARCHAR(16), NOT NULL): Target sector classification.
  - reference_date (DATE, NOT NULL): Period of statistical calculation.
  - sector_growth_rate_yoy (DECIMAL(5,2), NOT NULL): Sector annual GDP/output growth %.
  - sector_default_rate (DECIMAL(5,2), NOT NULL): Baseline loan default rate in sector.
  - risk_outlook_score (INT, NOT NULL): Regulatory/macro threat level (Scale 1 to 10).

--------------------------------------------------------------------------------
CLUSTER 2.3: COMMERCIAL GRAPH & CASH FLOW LEDGER
--------------------------------------------------------------------------------
* Table: counterparties
  The entity ledger of all trading partners identified in invoices and transfers.
  - counterparty_id (UUID, PK): Unique counterparty identifier.
  - business_id (UUID, FK -> businesses.business_id, NOT NULL): Relationship owner.
  - tax_id (VARCHAR(32), NULL): Counterparty national tax registration number.
  - legal_name (VARCHAR(255), NOT NULL): Name of client or supplier.
  - counterparty_role (VARCHAR(16), NOT NULL): Enum ('CLIENT', 'SUPPLIER', 'MIXED').

* Table: invoices
  Commercial trade receivables and trade payables tracking actual cash flow discipline.
  - invoice_id (UUID, PK): Unique invoice identifier.
  - business_id (UUID, FK -> businesses.business_id, NOT NULL): Originating firm.
  - counterparty_id (UUID, FK -> counterparties.counterparty_id, NOT NULL): Counterparty.
  - invoice_type (VARCHAR(16), NOT NULL): Enum ('RECEIVABLE', 'PAYABLE').
  - gross_amount (DECIMAL(18,2), NOT NULL): Nominal invoice monetary total.
  - issue_date (DATE, NOT NULL): Issuance date.
  - due_date (DATE, NOT NULL): Contractual payment deadline.
  - actual_payment_date (DATE, NULL): Actual date full settlement was recorded.
  - status (VARCHAR(16), NOT NULL): Enum ('PAID', 'OUTSTANDING', 'OVERDUE', 'DEFAULTED').

* Table: bank_accounts
  Real-time operating cash balances and credit limits across banking institutions.
  - account_id (UUID, PK): Unique bank account identifier.
  - business_id (UUID, FK -> businesses.business_id, NOT NULL): Account holder.
  - currency (VARCHAR(3), NOT NULL): Standard ISO currency ('MDL', 'EUR', 'USD').
  - current_balance (DECIMAL(18,2), NOT NULL): Cleared cash balance.
  - overdraft_limit (DECIMAL(18,2), DEFAULT 0.00): Approved revolving credit line.

* Table: transactions
  Granular bank statement ledger lines linking flows to categories and invoices.
  - transaction_id (UUID, PK): Unique transaction identifier.
  - business_id (UUID, FK -> businesses.business_id, NOT NULL): Account owner.
  - account_id (UUID, FK -> bank_accounts.account_id, NOT NULL): Bank account used.
  - counterparty_id (UUID, FK -> counterparties.counterparty_id, NULL): Identified partner.
  - invoice_id (UUID, FK -> invoices.invoice_id, NULL): Relational invoice link.
  - timestamp (TIMESTAMP WITH TIME ZONE, NOT NULL): Execution timestamp.
  - amount (DECIMAL(18,2), NOT NULL): Monetary value.
  - direction (VARCHAR(8), NOT NULL): Enum ('INFLOW', 'OUTFLOW').
  - category (VARCHAR(32), NOT NULL): Enum ('REVENUE', 'OPERATING_EXPENSE', 'PAYROLL', 
                                            'TAX', 'DEBT_SERVICE', 'DIVIDEND', 'OTHER').
  - liquidity_class (VARCHAR(24), NOT NULL): Enum ('IMMEDIATE_CASH', 'RESTRICTED_ESCROW',
                                                  'TERM_DEPOSIT').

--------------------------------------------------------------------------------
CLUSTER 2.4: LIABILITIES & REPAYMENT TRACK RECORD
--------------------------------------------------------------------------------
* Table: credit_obligations
  Direct facilities, bank credits, factoring lines, and equipment leasing.
  - obligation_id (UUID, PK): Unique facility identifier.
  - business_id (UUID, FK -> businesses.business_id, NOT NULL): Borrower.
  - lender_name (VARCHAR(255), NOT NULL): Financial institution or debt holder.
  - facility_type (VARCHAR(32), NOT NULL): Enum ('TERM_LOAN', 'LEASING', 'LINE_OF_CREDIT').
  - principal_amount (DECIMAL(18,2), NOT NULL): Original facility size.
  - outstanding_balance (DECIMAL(18,2), NOT NULL): Current unpaid principal balance.
  - monthly_payment (DECIMAL(18,2), NOT NULL): Contractual monthly debt service cost.
  - past_due_30d_count (INT, DEFAULT 0): Historical delinquency instances (1-30 DPD).
  - past_due_90d_count (INT, DEFAULT 0): Historical delinquency instances (31-90 DPD).
  - historical_defaults_count (INT, DEFAULT 0): Severe defaults (90+ DPD / charge-offs).

--------------------------------------------------------------------------------
CLUSTER 2.5: WEB APPLICATION IDENTITY & EXECUTION TELEMETRY
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

* Table: analysis_runs
  Tracks evaluation lifecycle, ingested payloads, feature vectors, and LLM output.
  - run_id (UUID, PK): Unique evaluation job identifier.
  - user_id (UUID, FK -> users.user_id, NOT NULL): Requesting user.
  - business_id (UUID, FK -> businesses.business_id, NULL): Link to business entity.
  - status (VARCHAR(32), NOT NULL): Enum ('QUEUED', 'PARSING', 'PROCESSING', 'COMPLETED', 'FAILED', 'DEGRADED').
  - input_company_name (VARCHAR(255), NOT NULL): Declared enterprise name.
  - input_tax_id (VARCHAR(32), NOT NULL): Declared national tax ID.
  - input_industry_code (VARCHAR(16), NOT NULL): Sector classification code.
  - files_manifest (JSONB, NOT NULL): Uploaded file metadata.
  - active_submodules (JSONB, NOT NULL): Enabled submodule codes.
  - raw_indices_payload (JSONB, NULL): Aggregated 18-element numerical feature vector.
  - submodules_reports (JSONB, NULL): Structured submodule verdicts and reports.
  - llm_final_summary (TEXT, NULL): Generated narrative synthesis from LLM.
  - universal_score (DECIMAL(5,2), NULL): Normalized overall score (0.00 to 100.00).
  - failure_reason (TEXT, NULL): Stack trace or error message.
  - created_at (TIMESTAMP WITH TIME ZONE, DEFAULT NOW()): Creation timestamp.
  - completed_at (TIMESTAMP WITH TIME ZONE, NULL): Termination timestamp.

* Table: analysis_logs
  Console diagnostic messages emitted during submodule and pipeline execution.
  - log_id (BIGSERIAL, PK): Incrementing event ID.
  - run_id (UUID, FK -> analysis_runs.run_id ON DELETE CASCADE, NOT NULL).
  - timestamp (TIMESTAMP WITH TIME ZONE, DEFAULT NOW()): Event timestamp.
  - severity (VARCHAR(16), NOT NULL): Enum ('DEBUG', 'INFO', 'WARN', 'ERROR').
  - stage (VARCHAR(32), NOT NULL): Stage emitting event.
  - message (TEXT, NOT NULL): Telemetry log message.


3. EXTERNAL DATA ACQUISITION & OPEN-SOURCE SEARCH PIPELINE
--------------------------------------------------------------------------------
The external search engine acts as an asynchronous enrichment pipeline that runs
prior to submodule evaluation. It populates `web_reputation` and `macro_sector_metrics`.

3.1 Pipeline Ingestion Workflow
1. Identification Layer: The engine extracts the `tax_id` and `legal_name` of the
   enterprise and initiates targeted workers.
2. Judicial & State Registry Scraping:
   - Worker queries national public court registries and debt-enforcement portals.
   - Parses open litigation records via headless browser scraping or open REST APIs.
   - Extracts: active defendant lawsuits count and aggregate monetary claims.
3. Sanctions & AML Watchlists:
   - Queries open AML, PEP, and international sanctions registries via fuzzy string
     matching on entity and board member names.
   - Flags binary matches (`is_in_sanctions_list`).
4. News & Digital Presence Scraping:
   - Search workers query global and regional news syndications using search APIs
     (`"{legal_name}" AND (court OR debt OR fraud OR expansion OR contract)`).
   - Scraped text snippets and news articles pass through a distilled LLM/NLP
     sentiment classification prompt.
   - Returns a bounded float `news_sentiment_score` (-1.000 for highly negative,
     0.000 for neutral, +1.000 for strongly positive).
5. Macroeconomic Enrichment:
   - Pulls current industry statistics from national bureaus and economic outlook
     databases mapped directly to the company's `industry_code`.


4. CORE ANALYTICAL ENGINE: 9 DECOUPLED SUBMODULES
--------------------------------------------------------------------------------

================================================================================
GROUP 1: GOVERNANCE & EXTERNAL RISK
================================================================================

--------------------------------------------------------------------------------
SUBMODULE 4.1: OWNERSHIP STRUCTURE (OS)
--------------------------------------------------------------------------------
Domain Scope & Business Rationale:
Examines capital stability, key-person risk, and governance integrity. Extreme equity
concentration in a single individual who also serves as executive director introduces
conflicts of interest and operational fragility. Conversely, balanced shareholding
paired with independent oversight promotes transparent strategic decisions.

Data Inputs:
* businesses (total_board_seats, independent_directors_count)
* shareholders (shareholder_name, equity_percentage, is_management_member)

Algorithmic Steps:
1. Shareholder Concentration (Herfindahl-Hirschman Index - HHI_Shareholders):
   HHI_Shareholders = Sum( (equity_percentage_i)^2 ) for all shareholders i = 1..N
   (Normalized scale: 0 to 10,000, where 10,000 indicates 100% single ownership).
2. Management-Ownership Overlap Ratio (MOOR):
   MOOR = Sum( equity_percentage_i WHERE is_management_member == TRUE ) / 100.0
3. Governance Independence Ratio (GIR):
   GIR = independent_directors_count / max(total_board_seats, 1)

Mathematical Output Indices:
* Ownership_Dispersion_Index = clamp(0.0, 100.0, 100.0 - (HHI_Shareholders / 100.0))
* Governance_Independence_Index = clamp(0.0, 100.0, (GIR * 70.0) + ((1.0 - MOOR) * 30.0))

Diagnostic Report Schema:
[SUBMODULE 4.1: OWNERSHIP STRUCTURE]
VERDICT: [BALANCED_GOVERNANCE | KEY_PERSON_RISK | CONCENTRATED_OWNERSHIP]
IMPACT WEIGHT: 0.08
NUMERICAL INDICES:
- Ownership Dispersion Index: <Score> / 100.0
- Governance Independence Index: <Score> / 100.0
SUMMARY: HHI_Shareholders calculated at <HHI>. Management holds <MOOR*100>% of equity.
Independent directors occupy <independent_directors_count> of <total_board_seats> seats.

--------------------------------------------------------------------------------
SUBMODULE 4.2: WEB PRESENCE & LEGAL REPUTATION (WPR)
--------------------------------------------------------------------------------
Domain Scope & Business Rationale:
Uncovers hidden off-balance-sheet liabilities and systemic reputational risks. Active
lawsuits against the company threaten unexpected capital outflows, while adverse news
mentions often precede contractual defaults or fraud revelations.

Data Inputs:
* web_reputation (active_lawsuits_count, total_lawsuit_claims_amount,
                  is_in_sanctions_list, news_sentiment_score)
* bank_accounts (Sum of current_balance across accounts)

Algorithmic Steps:
1. Sanctions Check:
   If is_in_sanctions_list == TRUE, Legal_Cleanliness_Index = 0.0 immediately.
2. Litigation Exposure Ratio (LER):
   Liquid_Cash = Sum(bank_accounts.current_balance)
   LER = total_lawsuit_claims_amount / max(Liquid_Cash, 1.0)
3. Legal Cleanliness Calculation:
   Base_Legal = 100.0 - (active_lawsuits_count * 15.0) - min(50.0, LER * 50.0)
   Legal_Cleanliness_Index = clamp(0.0, 100.0, Base_Legal)
4. Reputational Risk Calculation:
   If news_sentiment_score is NULL:
     Public_Reputation_Index = 50.0 (Neutral fallback)
   Else:
     Public_Reputation_Index = clamp(0.0, 100.0, (news_sentiment_score + 1.0) * 50.0)

Mathematical Output Indices:
* Legal_Cleanliness_Index = [0.0 to 100.0]
* Public_Reputation_Index = [0.0 to 100.0]

Diagnostic Report Schema:
[SUBMODULE 4.2: WEB PRESENCE & LEGAL REPUTATION]
VERDICT: [LEGAL_INTEGRITY_CONFIRMED | LITIGATION_EXPOSURE | CRITICAL_LEGAL_FLAG]
IMPACT WEIGHT: 0.12
NUMERICAL INDICES:
- Legal Cleanliness Index: <Score> / 100.0
- Public Reputation Index: <Score> / 100.0
SUMMARY: Identified <active_lawsuits_count> active lawsuits totaling <claims_amount> MDL.
Sanctions check: <PASS/FAIL>. News sentiment classified at <news_sentiment_score>.

--------------------------------------------------------------------------------
SUBMODULE 4.3: MACRO & SECTOR RISK (MSR)
--------------------------------------------------------------------------------
Domain Scope & Business Rationale:
Isolates systemic market headwinds from company-specific execution. A profitable SME
operating in a declining, highly leveraged industry faces elevated structural default
risks beyond its immediate financial control.

Data Inputs:
* businesses (industry_code)
* macro_sector_metrics (sector_growth_rate_yoy, sector_default_rate, risk_outlook_score)

Algorithmic Steps:
1. Sector Growth Rescaling:
   Growth_Score = clamp(0.0, 100.0, 50.0 + (sector_growth_rate_yoy * 5.0))
2. Sector Default Penalty:
   Default_Safety_Score = clamp(0.0, 100.0, 100.0 - (sector_default_rate * 5.0))
3. Outlook Transformation:
   Macro_Stability_Score = clamp(0.0, 100.0, 100.0 - ((risk_outlook_score - 1) * 11.11))
4. Consolidated Index:
   Sector_Vitality_Index = (0.40 * Growth_Score) + (0.35 * Default_Safety_Score) + 
                           (0.25 * Macro_Stability_Score)

Mathematical Output Indices:
* Sector_Vitality_Index = [0.0 to 100.0]

Diagnostic Report Schema:
[SUBMODULE 4.3: MACRO & SECTOR RISK]
VERDICT: [EXPANDING_SECTOR | STABLE_SECTOR | HIGH_RISK_SECTOR]
IMPACT WEIGHT: 0.05
NUMERICAL INDICES:
- Sector Vitality Index: <Score> / 100.0
SUMMARY: Industry code <industry_code> exhibits YoY growth of <growth>% and average default
rate of <default_rate>%. Macro sector threat index is rated <risk_outlook_score>/10.


================================================================================
GROUP 2: COMMERCIAL DIVERSIFICATION
================================================================================

--------------------------------------------------------------------------------
SUBMODULE 4.4: CLIENT DEPENDENCY (CD)
--------------------------------------------------------------------------------
Domain Scope & Business Rationale:
Quantifies customer concentration and single-point-of-failure revenue risk. If an SME
derives over 50% of its revenues from a single buyer, the commercial failure or
delayed payment from that buyer directly imperils the SME's solvency.

Data Inputs:
* counterparties (counterparty_id, counterparty_role == 'CLIENT')
* invoices (counterparty_id, invoice_type == 'RECEIVABLE', gross_amount, status == 'PAID')
  Evaluated over trailing 12 months.

Algorithmic Steps:
1. Aggregate Revenue per Client:
   Client_Revenue_k = Sum(gross_amount) for each unique client k.
   Total_Revenue = Sum(Client_Revenue_k) across all clients.
2. Market Share per Client:
   Share_k = (Client_Revenue_k / Total_Revenue) * 100.0
3. Customer Herfindahl-Hirschman Index (Customer_HHI):
   Customer_HHI = Sum( (Share_k)^2 ) for all k = 1..M
4. Top-1 and Top-3 Concentration Ratios:
   CR1 = max(Share_k)
   CR3 = Sum of top 3 largest Share_k

Mathematical Output Indices:
* Client_Diversification_Index = clamp(0.0, 100.0, 100.0 - (Customer_HHI / 100.0))
* Top_Client_Exposure_Index = clamp(0.0, 100.0, 100.0 - CR1)

Diagnostic Report Schema:
[SUBMODULE 4.4: CLIENT DEPENDENCY]
VERDICT: [BROAD_CLIENT_BASE | MODERATE_CONCENTRATION | SEVERE_CLIENT_DEPENDENCY]
IMPACT WEIGHT: 0.10
NUMERICAL INDICES:
- Client Diversification Index: <Score> / 100.0
- Top Client Exposure Index: <Score> / 100.0
SUMMARY: Customer HHI is <Customer_HHI>. Primary client accounts for <CR1>%, and top 3
clients represent <CR3>% of total trailing 12-month commercial revenue.

--------------------------------------------------------------------------------
SUBMODULE 4.5: SUPPLIER DEPENDENCY (SD)
--------------------------------------------------------------------------------
Domain Scope & Business Rationale:
Evaluates supply chain stability and single-source supplier vulnerability. Heavy
reliance on a single vendor leaves an enterprise vulnerable to raw material supply
shocks, pricing extortion, and sudden contractual margin compression.

Data Inputs:
* counterparties (counterparty_id, counterparty_role == 'SUPPLIER')
* invoices (counterparty_id, invoice_type == 'PAYABLE', gross_amount, status == 'PAID')
* transactions (counterparty_id, category == 'OPERATING_EXPENSE', amount, direction == 'OUTFLOW')
  Evaluated over trailing 12 months.

Algorithmic Steps:
1. Aggregate Spend per Supplier:
   Vendor_Spend_m = Sum(gross_amount) for each unique supplier m.
   Total_Vendor_Spend = Sum(Vendor_Spend_m) across all suppliers.
2. Spend Concentration per Supplier:
   Spend_Share_m = (Vendor_Spend_m / Total_Vendor_Spend) * 100.0
3. Vendor Herfindahl-Hirschman Index (Vendor_HHI):
   Vendor_HHI = Sum( (Spend_Share_m)^2 ) for all m = 1..P
4. Primary Vendor Dependency Ratio:
   Primary_Vendor_Share = max(Spend_Share_m)

Mathematical Output Indices:
* Supplier_Diversification_Index = clamp(0.0, 100.0, 100.0 - (Vendor_HHI / 100.0))
* Supply_Chain_Robustness_Index = clamp(0.0, 100.0, 100.0 - Primary_Vendor_Share)

Diagnostic Report Schema:
[SUBMODULE 4.5: SUPPLIER DEPENDENCY]
VERDICT: [DIVERSIFIED_SUPPLY_CHAIN | MONOPOLISTIC_SUPPLIER_RISK]
IMPACT WEIGHT: 0.08
NUMERICAL INDICES:
- Supplier Diversification Index: <Score> / 100.0
- Supply Chain Robustness Index: <Score> / 100.0
SUMMARY: Vendor HHI is <Vendor_HHI>. Largest supplier consumes <Primary_Vendor_Share>%
of total procurement expenditures across <P> active operational suppliers.


================================================================================
GROUP 3: LIQUIDITY & CASH FLOW
================================================================================

--------------------------------------------------------------------------------
SUBMODULE 4.6: IMMEDIATE CASH READINESS (ICR)
--------------------------------------------------------------------------------
Domain Scope & Business Rationale:
Detects imminent cash gap and insolvency risks. Operational profit on paper does
not equate to cash; companies collapse when immediate liquid reserves fail to meet
due dates for employee payroll, statutory tax payments, and short-term vendor bills.

Data Inputs:
* bank_accounts (current_balance, overdraft_limit WHERE currency == 'MDL')
* transactions (amount, category, timestamp)
* invoices (invoice_type == 'PAYABLE', gross_amount, status == 'OUTSTANDING', due_date)

Algorithmic Steps:
1. Total Available Liquidity:
   Liquid_Cash = Sum(current_balance) + Sum(overdraft_limit)
2. Imminent 30-Day Operational Commitments:
   Monthly_Payroll = Average_Trailing_3M(Outflows WHERE category == 'PAYROLL')
   Monthly_Taxes = Average_Trailing_3M(Outflows WHERE category == 'TAX')
   Due_Payables_30D = Sum(gross_amount WHERE status == 'OUTSTANDING' 
                          AND due_date <= CURRENT_DATE + INTERVAL '30 days')
   Total_Immediate_Demand = Monthly_Payroll + Monthly_Taxes + Due_Payables_30D
3. Classical Liquidity Ratios:
   - Cash Ratio (CR) = Liquid_Cash / max(Total_Immediate_Demand, 1.0)
   - Days Cash on Hand (DCOH) = Liquid_Cash / max((Monthly_Payroll + Monthly_Taxes)/30.0, 1.0)

Mathematical Output Indices:
* Cash_Readiness_Index = clamp(0.0, 100.0, CR * 50.0)  (Target: CR >= 2.0 = 100.0)
* Runway_Buffer_Index = clamp(0.0, 100.0, (DCOH / 60.0) * 100.0) (Target: 60+ Days = 100.0)

Diagnostic Report Schema:
[SUBMODULE 4.6: IMMEDIATE CASH READINESS]
VERDICT: [LIQUID_AND_SOLVENT | POTENTIAL_CASH_GAP | SEVERE_ILLIQUIDITY]
IMPACT WEIGHT: 0.15
NUMERICAL INDICES:
- Cash Readiness Index: <Score> / 100.0
- Runway Buffer Index: <Score> / 100.0
SUMMARY: Available liquidity: <Liquid_Cash> MDL. Immediate 30-day obligations:
<Total_Immediate_Demand> MDL. Cash Ratio is <CR>. Company maintains <DCOH> days cash runway.

--------------------------------------------------------------------------------
SUBMODULE 4.7: CASH FLOW STABILITY (CFS)
--------------------------------------------------------------------------------
Domain Scope & Business Rationale:
Evaluates revenue volatility, seasonality, and incoming cash predictability over time.
High revenue volatility introduces unexpected debt servicing shortfalls during trough
months, requiring higher liquidity safety margins.

Data Inputs:
* transactions (amount, direction == 'INFLOW', category == 'REVENUE', timestamp)
  Evaluated across 12 monthly rolling buckets.

Algorithmic Steps:
1. Aggregate Monthly Inflows:
   R_t = Sum(amount) for each month t = 1..12.
2. Mean and Standard Deviation:
   Mean_R = (1/12) * Sum(R_t)
   Std_R = sqrt( (1/11) * Sum( (R_t - Mean_R)^2 ) )
3. Coefficient of Variation (CV):
   CV_Revenue = Std_R / max(Mean_R, 1.0)
4. Inflow Trend Trajectory (Linear Slope via Ordinary Least Squares):
   Slope = Covariance(t, R_t) / Variance(t)
   Normalized_Trend = Slope / max(Mean_R, 1.0)

Mathematical Output Indices:
* Revenue_Predictability_Index = clamp(0.0, 100.0, 100.0 - (CV_Revenue * 100.0))
* Revenue_Trajectory_Index = clamp(0.0, 100.0, 50.0 + (Normalized_Trend * 500.0))

Diagnostic Report Schema:
[SUBMODULE 4.7: CASH FLOW STABILITY]
VERDICT: [CONSISTENT_FLOWS | MODERATE_VOLATILITY | HIGHLY_ERRATIC_FLOWS]
IMPACT WEIGHT: 0.08
NUMERICAL INDICES:
- Revenue Predictability Index: <Score> / 100.0
- Revenue Trajectory Index: <Score> / 100.0
SUMMARY: Mean monthly revenue: <Mean_R> MDL. Coefficient of Variation: <CV_Revenue>.
Revenue growth trajectory slope is <Slope> per month.


================================================================================
GROUP 4: DEBT & ASSET QUALITY
================================================================================

--------------------------------------------------------------------------------
SUBMODULE 4.8: RECEIVABLES QUALITY (RQ)
--------------------------------------------------------------------------------
Domain Scope & Business Rationale:
Examines trapped working capital and client repayment delinquency. High nominal
accounts receivable balances can conceal bad debts where customers consistently delay
or default on payments, creating severe hidden asset degradation.

Data Inputs:
* invoices (invoice_type == 'RECEIVABLE', gross_amount, issue_date, due_date,
            actual_payment_date, status)

Algorithmic Steps:
1. Receivables Aging & Delinquency Exposure:
   Total_Receivables = Sum(gross_amount WHERE status != 'PAID')
   Delinquent_Receivables = Sum(gross_amount WHERE status IN ('OVERDUE', 'DEFAULTED'))
   Counterparty_Exposure_Ratio (CER) = Delinquent_Receivables / max(Total_Receivables, 1.0)
2. Average Behavioral Payment Delay (Slippage):
   Delay_Days_i = max(0, actual_payment_date - due_date) for settled invoices.
   Mean_Delay_Days = Average(Delay_Days_i) across settled invoices in trailing 12 months.
3. Days Sales Outstanding (DSO):
   Annual_Credit_Sales = Sum(gross_amount WHERE invoice_type == 'RECEIVABLE' 
                             AND issue_date >= CURRENT_DATE - INTERVAL '365 days')
   DSO = (Total_Receivables / max(Annual_Credit_Sales, 1.0)) * 365.0

Mathematical Output Indices:
* Receivables_Safety_Index = clamp(0.0, 100.0, 100.0 - (CER * 100.0))
* Client_Payment_Discipline_Index = clamp(0.0, 100.0, 100.0 - (Mean_Delay_Days * 2.0))

Diagnostic Report Schema:
[SUBMODULE 4.8: RECEIVABLES QUALITY]
VERDICT: [PROMPT_COLLECTIONS | MODERATE_SLIPPAGE | FROZEN_DEBT_RISK]
IMPACT WEIGHT: 0.14
NUMERICAL INDICES:
- Receivables Safety Index: <Score> / 100.0
- Client Payment Discipline Index: <Score> / 100.0
SUMMARY: Delinquent receivables represent <CER*100>% of total book receivables. Average
payment delay past contractual due date is <Mean_Delay_Days> days. DSO stands at <DSO> days.

--------------------------------------------------------------------------------
SUBMODULE 4.9: INTERNAL CREDIT DISCIPLINE & LEVERAGE (ICDL)
--------------------------------------------------------------------------------
Domain Scope & Business Rationale:
Evaluates the firm's historical repayment integrity and debt service leverage. Chronic
delinquencies (30+ and 90+ DPD) signify institutional distress. Excessive debt-to-cash-flow
multiples make external investment hazardous by draining free operating margins into
fixed interest and principal payments.

Data Inputs:
* credit_obligations (principal_amount, outstanding_balance, monthly_payment,
                      past_due_30d_count, past_due_90d_count, historical_defaults_count)
* transactions (amount, direction, timestamp)

Algorithmic Steps:
1. Debt Repayment Discipline Index (DRDI):
   DPD_Penalty = (past_due_30d_count * 10.0) + (past_due_90d_count * 25.0) + 
                 (historical_defaults_count * 50.0)
   DRDI = clamp(0.0, 100.0, 100.0 - DPD_Penalty)
2. Debt Service Coverage Ratio (DSCR):
   Annual_Inflows = Sum(amount WHERE direction == 'INFLOW' AND timestamp >= NOW() - INTERVAL '1 year')
   Annual_OpEx = Sum(amount WHERE direction == 'OUTFLOW' AND category != 'DEBT_SERVICE' 
                     AND timestamp >= NOW() - INTERVAL '1 year')
   Operating_Cash_Flow = max(0.0, Annual_Inflows - Annual_OpEx)
   Annual_Debt_Service = Sum(monthly_payment * 12.0)
   DSCR = Operating_Cash_Flow / max(Annual_Debt_Service, 1.0)
3. Total Debt-to-Cash Flow Leverage (DCFL):
   Total_Debt = Sum(outstanding_balance)
   DCFL = Total_Debt / max(Operating_Cash_Flow, 1.0)

Mathematical Output Indices:
* Debt_Repayment_Discipline_Index = DRDI
* Debt_Service_Coverage_Index = clamp(0.0, 100.0, (DSCR / 2.0) * 100.0) (Target: DSCR >= 2.0)
* Solvency_Leverage_Index = clamp(0.0, 100.0, 100.0 - (DCFL * 20.0))

Diagnostic Report Schema:
[SUBMODULE 4.9: INTERNAL CREDIT DISCIPLINE & LEVERAGE]
VERDICT: [PRISTINE_CREDIT | MODERATE_LEVERAGE | OVERINDEBTED_DELINQUENT]
IMPACT WEIGHT: 0.16
NUMERICAL INDICES:
- Debt Repayment Discipline Index: <Score> / 100.0
- Debt Service Coverage Index: <Score> / 100.0
- Solvency Leverage Index: <Score> / 100.0
SUMMARY: Historical defaults: <historical_defaults_count>, 90-day DPD: <past_due_90d_count>,
30-day DPD: <past_due_30d_count>. Calculated DSCR is <DSCR>, with Total Debt / OCF at <DCFL>x.


5. EXECUTION LIFECYCLE, FEATURE VECTOR AGGREGATION & ML HAND-OFF
--------------------------------------------------------------------------------

5.1 Orchestration Workflow
1. Request Reception: The engine receives an evaluation request targeting a `business_id`
   and reference cutoff timestamp (supporting strict point-in-time underwriting discipline).
2. Data Pre-Fetch & Cache: The engine extracts connected entities from PostgreSQL
   (businesses, shareholders, web_reputation, counterparties, invoices, transactions,
   credit_obligations).
3. Concurrent Submodule Execution: Submodules 4.1 through 4.9 execute in parallel worker
   threads. Each submodule runs pure mathematical evaluations on in-memory representations
   of the retrieved records.
4. Error Handling & Missing Data Isolation:
   - If a table returns zero rows (e.g., no external web data found), the respective
     submodule returns an explicit `STATUS: DATA_ABSENT` report and sets its indices to `NULL`.
   - Remaining submodules continue unhindered.

5.2 Feature Vector Aggregation Schema
The analytical core concatenates the output scores into a standardized 18-element
numerical feature vector:

V = [
  Ownership_Dispersion_Index,          // Submodule 4.1
  Governance_Independence_Index,       // Submodule 4.1
  Legal_Cleanliness_Index,             // Submodule 4.2
  Public_Reputation_Index,             // Submodule 4.2
  Sector_Vitality_Index,               // Submodule 4.3
  Client_Diversification_Index,        // Submodule 4.4
  Top_Client_Exposure_Index,           // Submodule 4.4
  Supplier_Diversification_Index,      // Submodule 4.5
  Supply_Chain_Robustness_Index,       // Submodule 4.5
  Cash_Readiness_Index,                // Submodule 4.6
  Runway_Buffer_Index,                 // Submodule 4.6
  Revenue_Predictability_Index,        // Submodule 4.7
  Revenue_Trajectory_Index,            // Submodule 4.7
  Receivables_Safety_Index,            // Submodule 4.8
  Client_Payment_Discipline_Index,     // Submodule 4.8
  Debt_Repayment_Discipline_Index,     // Submodule 4.9
  Debt_Service_Coverage_Index,         // Submodule 4.9
  Solvency_Leverage_Index              // Submodule 4.9
]

5.3 Downstream ML Aggregator Hand-Off
* The numerical vector V is fed into a supervised Gradient Boosting Classifier (LightGBM/XGBoost).
* Missing indicators (`NULL`) are passed natively to the gradient boosting algorithm
  without synthetic zero-filling, allowing the tree splits to treat missingness as an
  independent signal.
* Text reports are combined into an Underwriting Dossier alongside SHAP (Shapley Additive
  exPlanations) attribution values, providing human credit officers and investment analysts
  with full interpretability behind every automated recommendation.
================================================================================
END OF BASIC LOGIC SPECIFICATION
================================================================================



================================================================================
6. SYSTEM COMPONENT BOUNDARIES, TERMINAL CLASSES & API CONTRACTS
================================================================================
This section establishes the strict terminal contracts, public class interfaces,
and Data Transfer Objects (DTOs) mapped directly to the codebase structure in
`src/fintech_app/`. It isolates architectural layers so that Frontend, Data Ingestion,
Risk Modeling, and API engineers can work concurrently against deterministic signatures.

All monetary amounts are represented as Python `decimal.Decimal` to prevent floating
point inaccuracies. Identifiers use standard `uuid.UUID`. All numerical indices output
by the analytical layer are bounded floats [0.0, 100.0] or None (null in JSON) when
evaluating with missing underlying records.

---

## 6.1 SHARED DOMAIN ENUMS & VALUE OBJECTS (src/fintech_app/shared/schemas/user_types.py)

Enums representing fixed domain states across all application boundaries (Python 3.12 `StrEnum`):

* Enum: EvaluationStatus
* SUCCESS: Submodule calculation completed normally.
* DATA_ABSENT: Required records missing; indices safely defaulted to null.
* ERROR: Operational or parsing failure during evaluation.

* Enum: CounterpartyRole
* CLIENT, SUPPLIER, MIXED

* Enum: InvoiceType
* RECEIVABLE, PAYABLE

* Enum: InvoiceStatus
* PAID, OUTSTANDING, OVERDUE, DEFAULTED

* Enum: TransactionDirection
* INFLOW, OUTFLOW

* Enum: TransactionCategory
* REVENUE, OPERATING_EXPENSE, PAYROLL, TAX, DEBT_SERVICE, DIVIDEND, OTHER

* Enum: LiquidityClass
* IMMEDIATE_CASH, RESTRICTED_ESCROW, TERM_DEPOSIT

* Enum: FacilityType
* TERM_LOAN, LEASING, LINE_OF_CREDIT

* Enum: AnalysisStatus
* QUEUED, PARSING, PROCESSING, COMPLETED, FAILED, DEGRADED


---

## 6.2 INGESTION & NORMALIZATION BOUNDARY (src/fintech_app/ingestion/)

This layer accepts unstructured or semi-structured bank statements, judicial extracts,
and registries, returning strictly typed normalized DTOs ready for DB insertion.

## FILE: src/fintech_app/ingestion/schemas.py

Terminal Pydantic DTOs for parsed external feeds:

* Class: RawBankStatementLine
* date: datetime.date
* amount: Decimal
* direction: TransactionDirection
* description: str
* counterparty_raw_name: Optional[str]
* counterparty_tax_id: Optional[str]
* account_number: str
* currency: str


* Class: ParsedBankStatementPayload
* account_id: UUID
* business_id: UUID
* opening_balance: Decimal
* closing_balance: Decimal
* period_start: datetime.date
* period_end: datetime.date
* lines: List[RawBankStatementLine]


* Class: ParsedJudicialRecord
* case_number: str
* filing_date: datetime.date
* role: str  # DEFENDANT, PLAINTIFF, THIRD_PARTY
* claim_amount: Decimal
* case_status: str  # OPEN, CLOSED, APPEALED


* Class: StandardizedTransactionBatch
* business_id: UUID
* account_id: UUID
* transactions: List[Dict[str, Any]] # Pre-mapped fields for DB insertion



## FILE: src/fintech_app/ingestion/parser.py

Terminal parser classes extracting structured records from file bytes:

* Class: BankStatementParser
Terminal Methods:
* parse_csv(file_content: bytes, account_id: UUID, business_id: UUID) -> ParsedBankStatementPayload
* parse_pdf(file_content: bytes, account_id: UUID, business_id: UUID) -> ParsedBankStatementPayload


* Class: JudicialRegistryParser
Terminal Methods:
* parse_court_registry_response(raw_response: dict) -> List[ParsedJudicialRecord]



## FILE: src/fintech_app/ingestion/ai_mapper.py

Semantic classification and category assignment for raw bank lines:

* Class: TransactionCategorizationMapper
Terminal Methods:
* map_categories_and_counterparties(payload: ParsedBankStatementPayload) -> StandardizedTransactionBatch
Transforms unstructured transaction descriptions into standard TransactionCategory
enums and links or creates Counterparty entities.



---

## 6.3 DATA ACCESS & EVALUATION SNAPSHOT LAYER (src/fintech_app/db/)

The analytical core must never execute ad-hoc SQL queries inside mathematical submodules.
All data persistence and access executes asynchronously via `psycopg_pool.AsyncConnectionPool`
and the `Database` class (`db/connection.py`), returning standardized `DatabaseReport` objects.

## FILE: src/fintech_app/db/models.py

Pure Python Dataclasses mapping strictly to Section 2 Database Tables:

* BusinessRecord
* ShareholderRecord
* WebReputationRecord
* MacroSectorMetricRecord
* CounterpartyRecord
* InvoiceRecord
* BankAccountRecord
* TransactionRecord
* CreditObligationRecord
* UserRecord
* UserSettingsRecord
* AnalysisRunRecord
* AnalysisLogRecord

## FILE: src/fintech_app/db/connection.py & Repository Interface

* Class: CompanyDataSnapshot (Pure In-Memory Evaluation Context)
Attributes:
* business_id: UUID
* as_of_date: datetime.date
* business: BusinessRecord
* shareholders: List[ShareholderRecord]
* web_reputation: Optional[WebReputationRecord]
* macro_metrics: Optional[MacroSectorMetricRecord]
* counterparties: List[CounterpartyRecord]
* invoices: List[InvoiceRecord]
* bank_accounts: List[BankAccountRecord]
* transactions: List[TransactionRecord]
* credit_obligations: List[CreditObligationRecord]


* Class: CompanyEvaluationRepository
Terminal Methods:
* async get_evaluation_snapshot(business_id: UUID, as_of_date: datetime.date) -> CompanyDataSnapshot
Queries all connected relational clusters via `Database` methods and constructs
the immutable snapshot.
* async persist_underwriting_result(run_id: UUID, dossier: Dict[str, Any]) -> DatabaseReport



---

## 6.4 CORE ANALYTICAL SUBMODULE CONTRACTS (src/fintech_app/ml/)

All 9 submodules reside directly inside `src/fintech_app/ml/` as flat files and adhere to a single
unified execution protocol: receiving `CompanyDataSnapshot` and producing `SubmoduleResult`.

Terminal DTO: SubmoduleResult

* submodule_code: str  # e.g., 'OS', 'WPR', 'MSR', 'CD', 'SD', 'ICR', 'CFS', 'RQ', 'ICDL'
* status: EvaluationStatus
* impact_weight: float
* verdict: str
* indices: Dict[str, Optional[float]]  # Standardized 0.0 to 100.0 values
* summary: str
* diagnostic_report: str

Flat Submodule Evaluator Files & Classes:

* FILE: `src/fintech_app/ml/submodule_ownership.py`
  Class: `OwnershipStructureEvaluator` (Submodule 4.1: OS)
  Indices: `Ownership_Dispersion_Index`, `Governance_Independence_Index`

* FILE: `src/fintech_app/ml/submodule_reputation.py`
  Class: `WebReputationEvaluator` (Submodule 4.2: WPR)
  Indices: `Legal_Cleanliness_Index`, `Public_Reputation_Index`

* FILE: `src/fintech_app/ml/submodule_macro.py`
  Class: `MacroSectorRiskEvaluator` (Submodule 4.3: MSR)
  Indices: `Sector_Vitality_Index`

* FILE: `src/fintech_app/ml/submodule_client_dep.py`
  Class: `ClientDependencyEvaluator` (Submodule 4.4: CD)
  Indices: `Client_Diversification_Index`, `Top_Client_Exposure_Index`

* FILE: `src/fintech_app/ml/submodule_supplier_dep.py`
  Class: `SupplierDependencyEvaluator` (Submodule 4.5: SD)
  Indices: `Supplier_Diversification_Index`, `Supply_Chain_Robustness_Index`

* FILE: `src/fintech_app/ml/submodule_cash_readiness.py`
  Class: `ImmediateCashReadinessEvaluator` (Submodule 4.6: ICR)
  Indices: `Cash_Readiness_Index`, `Runway_Buffer_Index`

* FILE: `src/fintech_app/ml/submodule_cash_stability.py`
  Class: `CashflowStabilityEvaluator` (Submodule 4.7: CFS)
  Indices: `Revenue_Predictability_Index`, `Revenue_Trajectory_Index`

* FILE: `src/fintech_app/ml/submodule_receivables.py`
  Class: `ReceivablesQualityEvaluator` (Submodule 4.8: RQ)
  Indices: `Receivables_Safety_Index`, `Client_Payment_Discipline_Index`

* FILE: `src/fintech_app/ml/submodule_credit_discipline.py`
  Class: `CreditDisciplineLeverageEvaluator` (Submodule 4.9: ICDL)
  Indices: `Debt_Repayment_Discipline_Index`, `Debt_Service_Coverage_Index`, `Solvency_Leverage_Index`



---

## 6.5 PIPELINE & PREDICTIVE SCORING CONTRACTS (src/fintech_app/ml/)

## FILE: src/fintech_app/ml/pipeline.py

Orchestrates concurrent execution of all 9 submodules and compiles the 18-element feature vector.

* Class: UnderwritingPipelineResult
* business_id: UUID
* as_of_date: datetime.date
* feature_vector: List[Optional[float]]  # Exactly 18 items in canonical order specified in Section 5.2
* submodule_results: Dict[str, SubmoduleResult]
* compiled_dossier_text: str


* Class: UnderwritingAnalyticalPipeline
Terminal Methods:
* run_analysis(snapshot: CompanyDataSnapshot, as_of_date: Optional[date] = None) -> UnderwritingPipelineResult



## FILE: src/fintech_app/ml/scoring.py

Executes decision scoring and LLM synthesis on the feature vector.

* Class: CreditScoringResult
* investment_attractiveness_score: float  # [0.0 to 100.0]
* probability_of_default: float  # [0.000 to 1.000]
* verdict_category: str  # PRIME_LOW_RISK, MODERATE_MONITORED, HIGH_RISK_REJECT
* recommendation: str  # APPROVED, MANUAL_REVIEW, REJECTED
* shap_attributions: Dict[str, float]  # Metric name -> impact on score
* executive_summary: str


* Class: CreditScoringEngine
Terminal Methods:
* calculate_score(feature_vector: List[Optional[float]], compiled_dossier_text: str = "") -> CreditScoringResult



---

## 6.6 API PRESENTATION CONTRACTS (src/fintech_app/api/ & shared/schemas/)

These request and response DTOs govern the FastAPI routing layer.

## FILE: src/fintech_app/api/endpoints/analysis.py (or router.py)

Endpoints:

* POST /api/v1/analysis/start
Accepts multipart form with enterprise metadata and package of CSV files, creates `analysis_runs` record in DB, and initializes background pipeline.
Request:
* input_company_name: str (form field)
* input_tax_id: str (form field)
* input_industry_code: str (form field)
* files: List[UploadFile] (multipart/form-data)

Response DTO: AnalysisStartResponse
* run_id: UUID
* status: AnalysisStatus  # QUEUED
* message: str


* GET /api/v1/analysis/stream/{run_id}
Streams live execution telemetry logs and stage transition events in real time via Server-Sent Events (SSE).
Media Type: `text/event-stream`


* GET /api/v1/analysis/report/{run_id}
Returns complete Underwriting Diagnostic Dossier including universal score, 18 indices, 9 submodule reports, and LLM summary.
Response DTO: AnalysisReportResponse
* run_id: UUID
* company_name: str
* tax_id: str
* execution_status: AnalysisStatus
* universal_score: float
* verdict_category: str
* feature_vector: Dict[str, Optional[float]]
* llm_synthesis: Dict[str, Any]
* submodules: List[Dict[str, Any]]
================================================================================
END OF SYSTEM SPECIFICATION
================================================================================
