"""
Pluggable LLM Clients: Base interface, Gemini API Client, Heuristic Local Matcher, and Mock Client.
"""

from __future__ import annotations
import json
import os
import re
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
import httpx


class BaseLLMClient(ABC):
    """Abstract interface for LLM calls."""

    @abstractmethod
    def generate_mapping(self, prompt: str, system_instruction: str) -> str:
        """Invokes LLM and returns raw response string (expected to be JSON)."""
        pass


class MockLLMClient(BaseLLMClient):
    """Deterministic Mock client for unit and integration testing."""

    def __init__(self, responses: Optional[List[str]] = None, default_response: Optional[str] = None):
        self.responses = responses or []
        self.default_response = default_response or "{}"
        self.calls_count = 0
        self.history: List[Dict[str, str]] = []

    def generate_mapping(self, prompt: str, system_instruction: str) -> str:
        self.calls_count += 1
        self.history.append({"prompt": prompt, "system": system_instruction})
        if self.responses:
            return self.responses.pop(0)
        return self.default_response


class HeuristicLLMClient(BaseLLMClient):
    """
    Intelligent local heuristic mapper.
    Matches multi-lingual and varying column names to schema.sql columns using token similarity.
    Enables instant offline execution, test runs, and fallback when no API key is available.
    """

    MULTILINGUAL_MAP = {
        # businesses
        "tax_id": ["инн", "фискальный", "idno", "cod_fiscal", "fiscal_code", "tax_number", "cui", "company_tax_id", "vat_id", "business_id"],
        "legal_name": ["название", "наименование", "компания", "denumire", "nume", "company_name", "enterprise_name", "business_name"],
        "industry_code": ["отрасль", "сектор", "код_отрасли", "ramura", "sector", "domain", "activity_code", "nace", "caen"],
        "registration_date": ["дата_регистрации", "дата_создания", "дата_основания", "основания", "основание", "data_inregistrarii", "founded_date", "creation_date", "company_age_years", "year_founded", "год_основания"],
        "total_board_seats": ["совет_директоров", "мест_в_совете", "совете_директоров", "board_seats", "directors", "numar_directori", "board_members"],
        "independent_directors_count": ["независимые_директора", "независимых_директоров", "независимых", "independent_directors"],
        # counterparties
        "counterparty_role": ["роль", "тип_контрагента", "rol", "counterparty_type", "partner_role", "client_or_supplier"],
        # invoices
        "invoice_type": ["тип_документа", "тип_счета", "направление_счета", "тип", "вид_документа", "вид_счета", "invoice_direction", "direction", "tip_factura", "operation_type", "document_type"],
        "gross_amount": ["сумма", "сумма_счета", "общая_сумма", "amount", "amount_mdl", "suma", "total_amount", "valoare", "total"],
        "issue_date": ["дата_выставления", "дата_счета", "data_emiterii", "data_facturii", "created_date", "invoice_date"],
        "due_date": ["дата_оплаты", "срок_оплаты", "data_scadenta", "term_date", "due", "expiration_date"],
        "actual_payment_date": ["фактическая_оплата", "paid_date", "data_achitarii", "payment_date", "settled_date"],
        "status": ["статус", "состояние", "stare", "statut", "payment_status", "invoice_status"],
        # bank_accounts
        "account_number": ["номер_счета", "счет", "iban", "cont_bancar", "account_no", "acc_num"],
        "currency": ["валюта", "valuta", "curr", "moneda"],
        "current_balance": ["баланс", "остаток", "closing_balance_mdl", "opening_balance_mdl", "sold", "balance"],
        "overdraft_limit": ["овердрафт", "лимит", "overdraft_limit_mdl", "overdraft"],
        # transactions
        "timestamp": ["время", "дата_транзакции", "transaction_date", "data_tranzactiei", "date", "datetime"],
        "amount": ["сумма_транзакции", "amount_mdl_equivalent", "valoare_tranzactie"],
        "direction": ["направление", "дебет_кредит", "sens", "flow", "debit_credit"],
        "category": ["категория", "назначение", "destinatie", "description", "details"],
        # credit_obligations
        "lender_name": ["банк", "кредитор", "banca", "creditor", "lender", "institution"],
        "facility_type": ["тип_кредита", "obligation_type", "tip_credit", "loan_type"],
        "principal_amount": ["сумма_кредита", "original_amount_mdl", "original_principal_mdl", "credit_amount"],
        "outstanding_balance": ["остаток_долга", "outstanding_amount_mdl", "sold_datorie", "debt_balance"],
        "monthly_payment": ["ежемесячный_платеж", "monthly_payment_mdl", "rata_lunara", "installment"],
    }

    def generate_mapping(self, prompt: str, system_instruction: str) -> str:
        # Extract headers and sample from prompt
        headers_match = re.search(r"Input Format / Headers:\s*(\[.*?\])", prompt, re.DOTALL)
        if not headers_match:
            return json.dumps({"target_table": "unknown", "mappings": [], "unmapped_source_columns": [], "unmapped_required_columns": []})

        headers = json.loads(headers_match.group(1))

        # Guess best target table
        table_scores: Dict[str, int] = {
            "businesses": 0,
            "invoices": 0,
            "transactions": 0,
            "bank_accounts": 0,
            "credit_obligations": 0,
            "counterparties": 0,
        }

        header_tokens = [re.sub(r"[^\w]", "_", h.lower()).strip("_") for h in headers]
        for ht in header_tokens:
            for col_name, synonyms in self.MULTILINGUAL_MAP.items():
                if ht == col_name or any(syn in ht or ht in syn for syn in synonyms):
                    if col_name in ("tax_id", "legal_name", "industry_code"):
                        table_scores["businesses"] += 3
                    elif col_name in ("invoice_type", "gross_amount", "issue_date", "due_date"):
                        table_scores["invoices"] += 3
                    elif col_name in ("timestamp", "direction", "category", "liquidity_class"):
                        table_scores["transactions"] += 3
                    elif col_name in ("account_number", "current_balance", "overdraft_limit"):
                        table_scores["bank_accounts"] += 3
                    elif col_name in ("lender_name", "facility_type", "outstanding_balance"):
                        table_scores["credit_obligations"] += 3

        # If prompt has a preferred table hint
        hint_match = re.search(r"PREFERRED TARGET TABLE:\s*([a-zA-Z0-9_]+)", prompt)
        preferred_table = hint_match.group(1).strip() if hint_match else None
        if preferred_table and preferred_table != "None" and preferred_table in table_scores:
            target_table = preferred_table
        else:
            target_table = max(table_scores, key=table_scores.get)
            if table_scores[target_table] == 0:
                target_table = "businesses"

        # Map headers
        mappings = []
        unmapped_src = []
        mapped_target_cols = set()

        for raw_h in headers:
            h_clean = re.sub(r"[^\w]", "_", raw_h.lower()).strip("_")
            best_col = None
            best_score = 0.0
            reason = "Exact match"

            for col_name, synonyms in self.MULTILINGUAL_MAP.items():
                if h_clean == col_name:
                    best_col = col_name
                    best_score = 1.0
                    reason = f"Exact canonical match '{col_name}'"
                    break
                for syn in synonyms:
                    if syn == h_clean:
                        best_col = col_name
                        best_score = 0.95
                        reason = f"Multilingual synonym match '{syn}' -> '{col_name}'"
                        break
                    elif syn in h_clean or h_clean in syn:
                        score = 0.85
                        if score > best_score:
                            best_score = score
                            best_col = col_name
                            reason = f"Partial match '{syn}' in '{h_clean}'"

            if best_col and best_col not in mapped_target_cols:
                mappings.append({
                    "source_column": raw_h,
                    "target_column": best_col,
                    "confidence": best_score,
                    "reasoning": reason,
                })
                mapped_target_cols.add(best_col)
            else:
                unmapped_src.append(raw_h)

        return json.dumps({
            "target_table": target_table,
            "mappings": mappings,
            "unmapped_source_columns": unmapped_src,
            "unmapped_required_columns": [],
        }, ensure_ascii=False)


class GeminiAPIClient(BaseLLMClient):
    """Google Gemini API client using standard HTTP requests."""

    def __init__(self, api_key: Optional[str] = None, model: str = "gemini-2.0-flash"):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.model = model
        self.endpoint = (
            f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
        )

    def generate_mapping(self, prompt: str, system_instruction: str) -> str:
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY is not set.")

        headers = {"Content-Type": "application/json"}
        payload = {
            "system_instruction": {"parts": [{"text": system_instruction}]},
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.0,
                "response_mime_type": "application/json",
            },
        }

        with httpx.Client(timeout=30.0) as client:
            resp = client.post(
                f"{self.endpoint}?key={self.api_key}",
                headers=headers,
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
            candidates = data.get("candidates", [])
            if not candidates:
                raise RuntimeError(f"Gemini API returned no candidates: {data}")
            text = candidates[0]["content"]["parts"][0]["text"]
            return text


def get_default_llm_client() -> BaseLLMClient:
    """Returns Gemini client if API key is present, otherwise intelligent Heuristic client."""
    if os.getenv("GEMINI_API_KEY"):
        return GeminiAPIClient()
    return HeuristicLLMClient()
