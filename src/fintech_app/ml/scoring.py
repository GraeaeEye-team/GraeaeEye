"""
Credit Scoring Engine and LLM Synthesis Core.

Consumes the canonical 18-element feature vector and submodule diagnostic reports,
calculates the overall Investment Attractiveness Score (0-100) via dynamic weight renormalization,
derives probability of default (PD) via logistic modeling, produces pseudo-SHAP factor attributions,
and generates structured synthesis prompts for LLM underwriting memoranda.
"""
from dataclasses import dataclass, field
import math

from .base import clamp


@dataclass
class CreditScoringResult:
    """
    Consolidated credit scoring and risk verdict result.

    Attributes:
        investment_attractiveness_score: Overall credit score bounded in [0.0, 100.0].
        probability_of_default: Estimated probability of default in [0.001, 0.999].
        verdict_category: High-level risk category ('PRIME_LOW_RISK',
            'MODERATE_MONITORED', 'HIGH_RISK_REJECT').
        recommendation: Action recommendation ('APPROVED', 'MANUAL_REVIEW', 'REJECTED').
        shap_attributions: Factor contribution breakdown (pseudo-SHAP) relative to 50.0.
        executive_summary: High-level executive synthesis of underwriting metrics.
        llm_synthesis_prompt: Synthesis prompt for LLM underwriting memo generation.
    """

    investment_attractiveness_score: float  # [0.0, 100.0]
    probability_of_default: float  # [0.001, 0.999]
    verdict_category: str  # PRIME_LOW_RISK, MODERATE_MONITORED, HIGH_RISK_REJECT
    recommendation: str  # APPROVED, MANUAL_REVIEW, REJECTED
    shap_attributions: dict[str, float] = field(default_factory=dict)
    executive_summary: str = ""
    llm_synthesis_prompt: str = ""

    @property
    def universal_score(self) -> float:
        """Alias for investment_attractiveness_score for domain parity."""
        return self.investment_attractiveness_score


class CreditScoringEngine:
    """
    Analytical scoring engine aggregating 18 canonical feature vector indices
    into an investment attractiveness score, probability of default, and LLM synthesis prompt.
    """

    # Submodule base weights (sum = 1.00)
    SUBMODULE_WEIGHTS: dict[str, float] = {
        "OS": 0.08,
        "WPR": 0.12,
        "MSR": 0.05,
        "CD": 0.10,
        "SD": 0.08,
        "ICR": 0.15,
        "CFS": 0.08,
        "RQ": 0.14,
        "ICDL": 0.16,
    }

    # Slice boundaries [start_idx, end_idx) in the canonical 18-element feature vector
    SUBMODULE_SLICES: dict[str, tuple[int, int]] = {
        "OS": (0, 2),
        "WPR": (2, 4),
        "MSR": (4, 5),
        "CD": (5, 7),
        "SD": (7, 9),
        "ICR": (9, 11),
        "CFS": (11, 13),
        "RQ": (13, 15),
        "ICDL": (15, 18),
    }

    # Canonical 18 feature names corresponding to feature_vector positions
    FEATURE_NAMES: list[str] = [
        "Ownership_Dispersion_Index",
        "Governance_Independence_Index",
        "Legal_Cleanliness_Index",
        "Public_Reputation_Index",
        "Sector_Vitality_Index",
        "Client_Diversification_Index",
        "Top_Client_Exposure_Index",
        "Supplier_Diversification_Index",
        "Supply_Chain_Robustness_Index",
        "Cash_Readiness_Index",
        "Runway_Buffer_Index",
        "Revenue_Predictability_Index",
        "Revenue_Trajectory_Index",
        "Receivables_Safety_Index",
        "Client_Payment_Discipline_Index",
        "Debt_Repayment_Discipline_Index",
        "Debt_Service_Coverage_Index",
        "Solvency_Leverage_Index",
    ]

    def _get_submodule_for_index(self, idx: int) -> str:
        """Returns the submodule code corresponding to a canonical feature vector index."""
        for code, (start, end) in self.SUBMODULE_SLICES.items():
            if start <= idx < end:
                return code
        return ""

    def calculate_score(
        self,
        feature_vector: list[float | None],
        compiled_dossier_text: str = "",
    ) -> CreditScoringResult:
        """
        Calculates credit score, probability of default, risk categories,
        pseudo-SHAP attributions, and LLM synthesis prompt from the canonical
        18-element feature vector.

        :param feature_vector: Standardized 18-element feature vector [0..100.0 or None].
        :param compiled_dossier_text: Concatenated diagnostic text reports from all submodules.
        :return: Consolidated CreditScoringResult.
        """
        # Step 1: Calculate submodule-level average scores for active submodules
        active_submodules: dict[str, float] = {}
        submodule_raw_values: dict[str, list[float | None]] = {}

        for code, (start_idx, end_idx) in self.SUBMODULE_SLICES.items():
            slice_vals = [
                feature_vector[i] if i < len(feature_vector) else None
                for i in range(start_idx, end_idx)
            ]
            submodule_raw_values[code] = slice_vals
            valid_vals = [v for v in slice_vals if v is not None]
            if valid_vals:
                active_submodules[code] = sum(valid_vals) / len(valid_vals)

        # Step 2: Dynamic weight renormalization over active submodules
        total_active_weight = sum(
            self.SUBMODULE_WEIGHTS[code] for code in active_submodules
        )

        renormalized_weights: dict[str, float] = {}
        if total_active_weight > 0.0:
            for code in active_submodules:
                renormalized_weights[code] = (
                    self.SUBMODULE_WEIGHTS[code] / total_active_weight
                )
            raw_score = sum(
                renormalized_weights[code] * active_submodules[code]
                for code in active_submodules
            )
        else:
            raw_score = 50.0

        score = clamp(raw_score, 0.0, 100.0)
        score = round(score, 2)

        # Step 3: Probability of Default (PD) via logistic transformation
        # PD = 1.0 / (1.0 + exp((score - 50.0) / 12.0))
        # At score=50.0 -> PD=0.5000; at score=100.0 -> PD≈0.0153; at score=0.0 -> PD≈0.9847
        try:
            pd_exponent = (score - 50.0) / 12.0
            pd_raw = 1.0 / (1.0 + math.exp(pd_exponent))
        except OverflowError:
            pd_raw = 0.001 if score > 50.0 else 0.999

        pd_val = clamp(pd_raw, 0.001, 0.999)
        pd_val = round(pd_val, 4)

        # Step 4: Decision verdicts and credit recommendations
        if score >= 75.0:
            verdict_category = "PRIME_LOW_RISK"
            recommendation = "APPROVED"
        elif score >= 55.0:
            verdict_category = "MODERATE_MONITORED"
            recommendation = "MANUAL_REVIEW"
        else:
            verdict_category = "HIGH_RISK_REJECT"
            recommendation = "REJECTED"

        # Step 5: Pseudo-SHAP feature and submodule attributions relative to 50.0 baseline
        shap_attributions: dict[str, float] = {}

        # Submodule-level attributions
        for code in self.SUBMODULE_WEIGHTS:
            if code in active_submodules:
                w_prime = renormalized_weights[code]
                sm_score = active_submodules[code]
                shap_attributions[code] = round((sm_score - 50.0) * w_prime, 4)
            else:
                shap_attributions[code] = 0.0

        # Feature-level attributions (both canonical PascalCase and snake_case keys)
        for idx, feat_name in enumerate(self.FEATURE_NAMES):
            val = feature_vector[idx] if idx < len(feature_vector) else None
            code = self._get_submodule_for_index(idx)
            if val is not None and code in active_submodules:
                w_prime = renormalized_weights[code]
                valid_count = len([v for v in submodule_raw_values[code] if v is not None])
                feat_weight = w_prime / max(valid_count, 1)
                feat_attr = round((val - 50.0) * feat_weight, 4)
            else:
                feat_attr = 0.0

            shap_attributions[feat_name] = feat_attr
            shap_attributions[feat_name.lower()] = feat_attr

        # Step 6: Executive summary narrative
        active_count = len(active_submodules)
        executive_summary = (
            f"Enterprise evaluated with an overall Investment Attractiveness "
            f"Score of {score:.1f}/100.0 ({verdict_category}). "
            f"Underwriting Recommendation: {recommendation}. "
            f"Estimated Probability of Default (PD): {pd_val * 100:.2f}%. "
            f"Active submodules: {active_count}/9."
        )

        # Step 7: LLM Synthesis Prompt generation for underwriting memorandum
        attribution_lines: list[str] = []
        for code, base_w in self.SUBMODULE_WEIGHTS.items():
            if code in active_submodules:
                sm_score = active_submodules[code]
                sm_attr = shap_attributions.get(code, 0.0)
                sign = "+" if sm_attr >= 0 else ""
                renorm_w = renormalized_weights[code]
                attribution_lines.append(
                    f"  - [{code}] Base Weight: {base_w:.2f} | Renorm Weight: {renorm_w:.2f} | "
                    f"Submodule Score: {sm_score:.1f} | SHAP Impact: {sign}{sm_attr:.2f} pts"
                )
            else:
                attribution_lines.append(
                    f"  - [{code}] Base Weight: {base_w:.2f} | "
                    f"Status: INACTIVE (DATA_ABSENT/ERROR) | SHAP Impact: 0.00 pts"
                )
        formatted_attributions = "\n".join(attribution_lines)

        clean_dossier = (
            compiled_dossier_text.strip()
            if compiled_dossier_text and compiled_dossier_text.strip()
            else "[No submodule diagnostic reports provided]"
        )

        llm_synthesis_prompt = f"""You are a Senior Credit Risk Underwriting Officer at a \
commercial SME fintech lender.
Your task is to synthesize the quantitative underwriting evaluation, feature scores, \
and submodule diagnostic reports into a comprehensive, professional Credit Underwriting Dossier.

### 1. EXECUTIVE UNDERWRITING METRICS:
- Investment Attractiveness Score: {score:.1f} / 100.0
- Verdict Category: {verdict_category}
- Underwriting Recommendation: {recommendation}
- Estimated Probability of Default (PD): {pd_val * 100:.2f}%
- Active Risk Submodules: {active_count}/9

### 2. RISK FACTOR SHAP ATTRIBUTIONS (Impact relative to 50.0 neutral baseline):
{formatted_attributions}

### 3. COMPILED SUBMODULE DIAGNOSTIC DOSSIER:
{clean_dossier}

### 4. INSTRUCTIONS FOR DOSSIER SYNTHESIS:
Produce a structured Credit Committee Underwriting Memorandum with the following sections:
1. Executive Summary & Core Verdict: Concise review of the enterprise, core strengths, \
and credit decision.
2. Pillar-by-Pillar Risk Breakdown:
   - Corporate Governance & Ownership Stability (OS, WPR)
   - Macroeconomic & Sector Resilience (MSR)
   - Commercial Counterparty Concentration & Supply Chain Robustness (CD, SD)
   - Liquidity, Runway & Cashflow Predictability (ICR, CFS)
   - Credit Repayment Discipline, Receivables Aging & Leverage (RQ, ICDL)
3. Key Risk Factors & Early Warnings: Identify specific vulnerabilities, adverse trends, \
or data gaps.
4. Mitigating Factors & Compensating Controls: Justify strengths that counterbalance weaknesses.
5. Underwriting Decision, Covenants & Monitoring Terms:
   - Final Loan Decision ({recommendation})
   - Required Covenants (e.g., minimum DSCR, cash runway maintenance, concentration limits)
   - Collateral or personal guarantee requirements if applicable
   - Early warning triggers and monitoring cadence.

Maintain an institutional, evidence-based, and rigorous tone appropriate for an \
investment credit committee."""

        return CreditScoringResult(
            investment_attractiveness_score=score,
            probability_of_default=pd_val,
            verdict_category=verdict_category,
            recommendation=recommendation,
            shap_attributions=shap_attributions,
            executive_summary=executive_summary,
            llm_synthesis_prompt=llm_synthesis_prompt,
        )


def evaluate_counterparty_risk(
    feature_vector: list[float | None],
    compiled_dossier_text: str = "",
) -> CreditScoringResult:
    """Convenience helper for counterparty credit risk scoring."""
    engine = CreditScoringEngine()
    return engine.calculate_score(feature_vector, compiled_dossier_text)


__all__ = [
    "CreditScoringEngine",
    "CreditScoringResult",
    "evaluate_counterparty_risk",
]
