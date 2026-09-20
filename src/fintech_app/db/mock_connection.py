"""
In-memory Mock Database implementation for offline testing and development.
Target: ./mock_connection.py
Specification: docs/database_architecture-v2.md (Section 8)
"""

from __future__ import annotations

import copy
from datetime import date, datetime
from decimal import Decimal
import logging
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from .models import DatabaseReport

logger = logging.getLogger("smart_credit.db.mock_connection")


class MockDatabase:
    """
    In-memory mock database providing the complete interface of Database
    for offline development, CI pipelines, and unit testing.
    """

    _instance: Optional[MockDatabase] = None

    @classmethod
    def get_instance(cls) -> MockDatabase:
        """Returns or creates the singleton MockDatabase instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self) -> None:
        self._storage: Dict[str, List[Dict[str, Any]]] = {
            "businesses": [],
            "shareholders": [],
            "web_reputation": [],
            "macro_sector_metrics": [],
            "counterparties": [],
            "invoices": [],
            "bank_accounts": [],
            "transactions": [],
            "credit_obligations": [],
            "users": [],
            "user_settings": [],
            "analysis_runs": [],
            "analysis_logs": [],
        }
        self.is_open: bool = False

    async def open(self) -> None:
        """Simulates opening database connection pool."""
        self.is_open = True

    async def close(self) -> None:
        """Simulates closing database connection pool."""
        self.is_open = False

    async def health_check(self) -> bool:
        """Returns True if mock database is healthy."""
        return True

    async def __aenter__(self) -> MockDatabase:
        await self.open()
        return self

    async def __aexit__(
        self,
        exc_type: Optional[type],
        exc_val: Optional[BaseException],
        exc_tb: Optional[Any],
    ) -> None:
        await self.close()

    def reset(self) -> None:
        """Clears all in-memory tables."""
        for table in self._storage:
            self._storage[table].clear()

    # =========================================================================
    # GENERIC IN-MEMORY STORAGE PRIMITIVES
    # =========================================================================

    def _matches_filters(self, row: Dict[str, Any], filters: Dict[str, Any]) -> bool:
        for k, v in filters.items():
            if v is not None:
                row_val = row.get(k)
                if hasattr(v, "value") and isinstance(v.value, str):
                    target_val = v.value
                else:
                    target_val = v

                if hasattr(row_val, "value") and isinstance(row_val.value, str):
                    compare_row_val = row_val.value
                else:
                    compare_row_val = row_val

                if compare_row_val != target_val:
                    return False
        return True

    def _mock_insert(self, table_name: str, data: Dict[str, Any]) -> DatabaseReport:
        record = copy.deepcopy(data)
        self._storage[table_name].append(record)
        return DatabaseReport(
            success=True,
            data=copy.deepcopy(record),
            affected_rows=1,
            operation="INSERT",
            table_name=table_name,
        )

    def _mock_select(
        self,
        table_name: str,
        filters: Dict[str, Any],
        find_only_first: bool = False,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
    ) -> DatabaseReport:
        matches = [
            copy.deepcopy(row)
            for row in self._storage[table_name]
            if self._matches_filters(row, filters)
        ]

        if offset is not None:
            matches = matches[offset:]
        if limit is not None:
            matches = matches[:limit]

        if find_only_first:
            res = matches[0] if matches else None
            return DatabaseReport(
                success=True,
                data=res,
                affected_rows=1 if res else 0,
                operation="SELECT",
                table_name=table_name,
            )
        return DatabaseReport(
            success=True,
            data=matches,
            affected_rows=len(matches),
            operation="SELECT",
            table_name=table_name,
        )

    async def select_records(
        self,
        table_name: str,
        conditions: Optional[Dict[str, Any]] = None,
        find_only_first: bool = False,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        order_by: Optional[str] = None,
    ) -> DatabaseReport:
        """Generic select helper for dynamic table queries in mock database."""
        return self._mock_select(
            table_name=table_name,
            filters=conditions or {},
            find_only_first=find_only_first,
            limit=limit,
            offset=offset,
        )

    def _mock_update(
        self,
        table_name: str,
        updates: Dict[str, Any],
        filters: Dict[str, Any],
    ) -> DatabaseReport:
        updated_rows: List[Dict[str, Any]] = []
        for row in self._storage[table_name]:
            if self._matches_filters(row, filters):
                for k, v in updates.items():
                    row[k] = copy.deepcopy(v)
                updated_rows.append(copy.deepcopy(row))
        return DatabaseReport(
            success=True,
            data=updated_rows,
            affected_rows=len(updated_rows),
            operation="UPDATE",
            table_name=table_name,
        )

    def _mock_delete(
        self,
        table_name: str,
        filters: Dict[str, Any],
        delete_only_first: bool = False,
    ) -> DatabaseReport:
        original = self._storage[table_name]
        remaining: List[Dict[str, Any]] = []
        deleted_count = 0

        for row in original:
            if self._matches_filters(row, filters):
                if delete_only_first and deleted_count > 0:
                    remaining.append(row)
                else:
                    deleted_count += 1
            else:
                remaining.append(row)

        self._storage[table_name] = remaining
        return DatabaseReport(
            success=True,
            affected_rows=deleted_count,
            operation="DELETE",
            table_name=table_name,
        )

    # =========================================================================
    # CLUSTER 1: CORPORATE IDENTITY & GOVERNANCE
    # =========================================================================

    async def add_record_to_businesses(
        self,
        tax_id: str,
        legal_name: str,
        industry_code: str,
        registration_date: date,
        business_id: Optional[UUID] = None,
        total_board_seats: int = 1,
        independent_directors_count: int = 0,
    ) -> DatabaseReport:
        data = {
            "business_id": business_id or uuid4(),
            "tax_id": tax_id,
            "legal_name": legal_name,
            "industry_code": industry_code,
            "registration_date": registration_date,
            "total_board_seats": total_board_seats,
            "independent_directors_count": independent_directors_count,
        }
        return self._mock_insert("businesses", data)

    async def get_records_from_businesses(
        self,
        find_only_first: bool = False,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        **filters: Any,
    ) -> DatabaseReport:
        return self._mock_select(
            "businesses",
            filters,
            find_only_first=find_only_first,
            limit=limit,
            offset=offset,
        )

    async def update_records_in_businesses(
        self,
        updates: Dict[str, Any],
        **filters: Any,
    ) -> DatabaseReport:
        return self._mock_update("businesses", updates, filters)

    async def delete_records_from_businesses(
        self,
        delete_only_first: bool = False,
        **filters: Any,
    ) -> DatabaseReport:
        return self._mock_delete(
            "businesses", filters, delete_only_first=delete_only_first
        )

    async def add_record_to_shareholders(
        self,
        business_id: UUID,
        shareholder_name: str,
        equity_percentage: Decimal,
        is_management_member: bool = False,
        ownership_id: Optional[UUID] = None,
    ) -> DatabaseReport:
        data = {
            "ownership_id": ownership_id or uuid4(),
            "business_id": business_id,
            "shareholder_name": shareholder_name,
            "equity_percentage": equity_percentage,
            "is_management_member": is_management_member,
        }
        return self._mock_insert("shareholders", data)

    async def get_records_from_shareholders(
        self,
        find_only_first: bool = False,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        **filters: Any,
    ) -> DatabaseReport:
        return self._mock_select(
            "shareholders",
            filters,
            find_only_first=find_only_first,
            limit=limit,
            offset=offset,
        )

    async def update_records_in_shareholders(
        self,
        updates: Dict[str, Any],
        **filters: Any,
    ) -> DatabaseReport:
        return self._mock_update("shareholders", updates, filters)

    async def delete_records_from_shareholders(
        self,
        delete_only_first: bool = False,
        **filters: Any,
    ) -> DatabaseReport:
        return self._mock_delete(
            "shareholders", filters, delete_only_first=delete_only_first
        )

    # =========================================================================
    # CLUSTER 2: EXTERNAL INTELLIGENCE & MACRO DATA
    # =========================================================================

    async def add_record_to_web_reputation(
        self,
        business_id: UUID,
        scan_timestamp: Optional[datetime] = None,
        active_lawsuits_count: int = 0,
        total_lawsuit_claims_amount: Decimal = Decimal("0.00"),
        is_in_sanctions_list: bool = False,
        news_sentiment_score: Optional[Decimal] = None,
        web_traffic_monthly_visits: Optional[int] = None,
        record_id: Optional[UUID] = None,
    ) -> DatabaseReport:
        data = {
            "record_id": record_id or uuid4(),
            "business_id": business_id,
            "scan_timestamp": scan_timestamp or datetime.now(),
            "active_lawsuits_count": active_lawsuits_count,
            "total_lawsuit_claims_amount": total_lawsuit_claims_amount,
            "is_in_sanctions_list": is_in_sanctions_list,
            "news_sentiment_score": news_sentiment_score,
            "web_traffic_monthly_visits": web_traffic_monthly_visits,
        }
        return self._mock_insert("web_reputation", data)

    async def get_records_from_web_reputation(
        self,
        find_only_first: bool = False,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        **filters: Any,
    ) -> DatabaseReport:
        return self._mock_select(
            "web_reputation",
            filters,
            find_only_first=find_only_first,
            limit=limit,
            offset=offset,
        )

    async def update_records_in_web_reputation(
        self,
        updates: Dict[str, Any],
        **filters: Any,
    ) -> DatabaseReport:
        return self._mock_update("web_reputation", updates, filters)

    async def delete_records_from_web_reputation(
        self,
        delete_only_first: bool = False,
        **filters: Any,
    ) -> DatabaseReport:
        return self._mock_delete(
            "web_reputation", filters, delete_only_first=delete_only_first
        )

    async def add_record_to_macro_sector_metrics(
        self,
        industry_code: str,
        reference_date: date,
        sector_growth_rate_yoy: Decimal,
        sector_default_rate: Decimal,
        risk_outlook_score: int,
        metric_id: Optional[UUID] = None,
    ) -> DatabaseReport:
        data = {
            "metric_id": metric_id or uuid4(),
            "industry_code": industry_code,
            "reference_date": reference_date,
            "sector_growth_rate_yoy": sector_growth_rate_yoy,
            "sector_default_rate": sector_default_rate,
            "risk_outlook_score": risk_outlook_score,
        }
        return self._mock_insert("macro_sector_metrics", data)

    async def get_records_from_macro_sector_metrics(
        self,
        find_only_first: bool = False,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        **filters: Any,
    ) -> DatabaseReport:
        return self._mock_select(
            "macro_sector_metrics",
            filters,
            find_only_first=find_only_first,
            limit=limit,
            offset=offset,
        )

    async def update_records_in_macro_sector_metrics(
        self,
        updates: Dict[str, Any],
        **filters: Any,
    ) -> DatabaseReport:
        return self._mock_update("macro_sector_metrics", updates, filters)

    async def delete_records_from_macro_sector_metrics(
        self,
        delete_only_first: bool = False,
        **filters: Any,
    ) -> DatabaseReport:
        return self._mock_delete(
            "macro_sector_metrics", filters, delete_only_first=delete_only_first
        )

    # =========================================================================
    # CLUSTER 3: COMMERCIAL GRAPH & CASH FLOW LEDGER
    # =========================================================================

    async def add_record_to_counterparties(
        self,
        business_id: UUID,
        legal_name: str,
        counterparty_role: str,
        tax_id: Optional[str] = None,
        counterparty_id: Optional[UUID] = None,
    ) -> DatabaseReport:
        data = {
            "counterparty_id": counterparty_id or uuid4(),
            "business_id": business_id,
            "tax_id": tax_id,
            "legal_name": legal_name,
            "counterparty_role": counterparty_role,
        }
        return self._mock_insert("counterparties", data)

    async def get_records_from_counterparties(
        self,
        find_only_first: bool = False,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        **filters: Any,
    ) -> DatabaseReport:
        return self._mock_select(
            "counterparties",
            filters,
            find_only_first=find_only_first,
            limit=limit,
            offset=offset,
        )

    async def update_records_in_counterparties(
        self,
        updates: Dict[str, Any],
        **filters: Any,
    ) -> DatabaseReport:
        return self._mock_update("counterparties", updates, filters)

    async def delete_records_from_counterparties(
        self,
        delete_only_first: bool = False,
        **filters: Any,
    ) -> DatabaseReport:
        return self._mock_delete(
            "counterparties", filters, delete_only_first=delete_only_first
        )

    async def add_record_to_invoices(
        self,
        business_id: UUID,
        counterparty_id: UUID,
        invoice_type: str,
        gross_amount: Decimal,
        issue_date: date,
        due_date: date,
        status: str,
        actual_payment_date: Optional[date] = None,
        invoice_id: Optional[UUID] = None,
    ) -> DatabaseReport:
        data = {
            "invoice_id": invoice_id or uuid4(),
            "business_id": business_id,
            "counterparty_id": counterparty_id,
            "invoice_type": invoice_type,
            "gross_amount": (
                abs(gross_amount) if gross_amount is not None else gross_amount
            ),
            "issue_date": issue_date,
            "due_date": due_date,
            "actual_payment_date": actual_payment_date,
            "status": status,
        }
        return self._mock_insert("invoices", data)

    async def get_records_from_invoices(
        self,
        find_only_first: bool = False,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        **filters: Any,
    ) -> DatabaseReport:
        return self._mock_select(
            "invoices",
            filters,
            find_only_first=find_only_first,
            limit=limit,
            offset=offset,
        )

    async def update_records_in_invoices(
        self,
        updates: Dict[str, Any],
        **filters: Any,
    ) -> DatabaseReport:
        return self._mock_update("invoices", updates, filters)

    async def delete_records_from_invoices(
        self,
        delete_only_first: bool = False,
        **filters: Any,
    ) -> DatabaseReport:
        return self._mock_delete(
            "invoices", filters, delete_only_first=delete_only_first
        )

    async def add_record_to_bank_accounts(
        self,
        business_id: UUID,
        currency: str,
        current_balance: Decimal,
        overdraft_limit: Decimal = Decimal("0.00"),
        account_id: Optional[UUID] = None,
    ) -> DatabaseReport:
        data = {
            "account_id": account_id or uuid4(),
            "business_id": business_id,
            "currency": currency,
            "current_balance": current_balance,
            "overdraft_limit": overdraft_limit,
        }
        return self._mock_insert("bank_accounts", data)

    async def get_records_from_bank_accounts(
        self,
        find_only_first: bool = False,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        **filters: Any,
    ) -> DatabaseReport:
        return self._mock_select(
            "bank_accounts",
            filters,
            find_only_first=find_only_first,
            limit=limit,
            offset=offset,
        )

    async def update_records_in_bank_accounts(
        self,
        updates: Dict[str, Any],
        **filters: Any,
    ) -> DatabaseReport:
        return self._mock_update("bank_accounts", updates, filters)

    async def delete_records_from_bank_accounts(
        self,
        delete_only_first: bool = False,
        **filters: Any,
    ) -> DatabaseReport:
        return self._mock_delete(
            "bank_accounts", filters, delete_only_first=delete_only_first
        )

    async def add_record_to_transactions(
        self,
        business_id: UUID,
        account_id: UUID,
        timestamp: datetime,
        amount: Decimal,
        direction: str,
        category: str,
        liquidity_class: str = "IMMEDIATE_CASH",
        counterparty_id: Optional[UUID] = None,
        invoice_id: Optional[UUID] = None,
        transaction_id: Optional[UUID] = None,
    ) -> DatabaseReport:
        data = {
            "transaction_id": transaction_id or uuid4(),
            "business_id": business_id,
            "account_id": account_id,
            "counterparty_id": counterparty_id,
            "invoice_id": invoice_id,
            "timestamp": timestamp,
            "amount": abs(amount) if amount is not None else amount,
            "direction": direction,
            "category": category,
            "liquidity_class": liquidity_class,
        }
        return self._mock_insert("transactions", data)

    async def get_records_from_transactions(
        self,
        find_only_first: bool = False,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        **filters: Any,
    ) -> DatabaseReport:
        return self._mock_select(
            "transactions",
            filters,
            find_only_first=find_only_first,
            limit=limit,
            offset=offset,
        )

    async def update_records_in_transactions(
        self,
        updates: Dict[str, Any],
        **filters: Any,
    ) -> DatabaseReport:
        return self._mock_update("transactions", updates, filters)

    async def delete_records_from_transactions(
        self,
        delete_only_first: bool = False,
        **filters: Any,
    ) -> DatabaseReport:
        return self._mock_delete(
            "transactions", filters, delete_only_first=delete_only_first
        )

    # =========================================================================
    # CLUSTER 4: LIABILITIES & DEBT FACILITIES
    # =========================================================================

    async def add_record_to_credit_obligations(
        self,
        business_id: UUID,
        lender_name: str,
        facility_type: str,
        principal_amount: Decimal,
        outstanding_balance: Decimal,
        monthly_payment: Decimal,
        past_due_30d_count: int = 0,
        past_due_90d_count: int = 0,
        historical_defaults_count: int = 0,
        obligation_id: Optional[UUID] = None,
    ) -> DatabaseReport:
        data = {
            "obligation_id": obligation_id or uuid4(),
            "business_id": business_id,
            "lender_name": lender_name,
            "facility_type": facility_type,
            "principal_amount": (
                abs(principal_amount) if principal_amount is not None else principal_amount
            ),
            "outstanding_balance": (
                abs(outstanding_balance)
                if outstanding_balance is not None
                else outstanding_balance
            ),
            "monthly_payment": (
                abs(monthly_payment) if monthly_payment is not None else monthly_payment
            ),
            "past_due_30d_count": past_due_30d_count,
            "past_due_90d_count": past_due_90d_count,
            "historical_defaults_count": historical_defaults_count,
        }
        return self._mock_insert("credit_obligations", data)

    async def get_records_from_credit_obligations(
        self,
        find_only_first: bool = False,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        **filters: Any,
    ) -> DatabaseReport:
        return self._mock_select(
            "credit_obligations",
            filters,
            find_only_first=find_only_first,
            limit=limit,
            offset=offset,
        )

    async def update_records_in_credit_obligations(
        self,
        updates: Dict[str, Any],
        **filters: Any,
    ) -> DatabaseReport:
        return self._mock_update("credit_obligations", updates, filters)

    async def delete_records_from_credit_obligations(
        self,
        delete_only_first: bool = False,
        **filters: Any,
    ) -> DatabaseReport:
        return self._mock_delete(
            "credit_obligations", filters, delete_only_first=delete_only_first
        )

    # =========================================================================
    # CLUSTER 5: WEB APPLICATION IDENTITY & EXECUTION TELEMETRY
    # =========================================================================

    async def add_record_to_users(
        self,
        email: str,
        password_hash: str,
        full_name: str,
        role: str = "ANALYST",
        is_active: bool = True,
        user_id: Optional[UUID] = None,
    ) -> DatabaseReport:
        data = {
            "user_id": user_id or uuid4(),
            "email": email,
            "password_hash": password_hash,
            "full_name": full_name,
            "role": role,
            "is_active": is_active,
        }
        return self._mock_insert("users", data)

    async def get_records_from_users(
        self,
        find_only_first: bool = False,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        **filters: Any,
    ) -> DatabaseReport:
        return self._mock_select(
            "users",
            filters,
            find_only_first=find_only_first,
            limit=limit,
            offset=offset,
        )

    async def update_records_in_users(
        self,
        updates: Dict[str, Any],
        **filters: Any,
    ) -> DatabaseReport:
        return self._mock_update("users", updates, filters)

    async def delete_records_from_users(
        self,
        delete_only_first: bool = False,
        **filters: Any,
    ) -> DatabaseReport:
        return self._mock_delete(
            "users", filters, delete_only_first=delete_only_first
        )

    async def add_record_to_user_settings(
        self,
        user_id: UUID,
        ui_theme: str = "system",
        terminal_sound_effects: bool = False,
        auto_expand_reports: bool = True,
        setting_id: Optional[UUID] = None,
    ) -> DatabaseReport:
        data = {
            "setting_id": setting_id or uuid4(),
            "user_id": user_id,
            "ui_theme": ui_theme,
            "terminal_sound_effects": terminal_sound_effects,
            "auto_expand_reports": auto_expand_reports,
        }
        return self._mock_insert("user_settings", data)

    async def get_records_from_user_settings(
        self,
        find_only_first: bool = False,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        **filters: Any,
    ) -> DatabaseReport:
        return self._mock_select(
            "user_settings",
            filters,
            find_only_first=find_only_first,
            limit=limit,
            offset=offset,
        )

    async def update_records_in_user_settings(
        self,
        updates: Dict[str, Any],
        **filters: Any,
    ) -> DatabaseReport:
        return self._mock_update("user_settings", updates, filters)

    async def delete_records_from_user_settings(
        self,
        delete_only_first: bool = False,
        **filters: Any,
    ) -> DatabaseReport:
        return self._mock_delete(
            "user_settings", filters, delete_only_first=delete_only_first
        )

    async def add_record_to_analysis_runs(
        self,
        user_id: UUID,
        input_company_name: str,
        input_tax_id: str,
        input_industry_code: str,
        files_manifest: Dict[str, Any],
        active_submodules: List[str],
        status: str = "QUEUED",
        business_id: Optional[UUID] = None,
        run_id: Optional[UUID] = None,
        raw_indices_payload: Optional[Dict[str, Any]] = None,
        submodules_reports: Optional[List[Dict[str, Any]]] = None,
        llm_final_summary: Optional[str] = None,
        universal_score: Optional[Decimal] = None,
        verdict_category: Optional[str] = None,
        recommendation: Optional[str] = None,
        failure_reason: Optional[str] = None,
    ) -> DatabaseReport:
        data: Dict[str, Any] = {
            "run_id": run_id or uuid4(),
            "user_id": user_id,
            "business_id": business_id,
            "status": status,
            "input_company_name": input_company_name,
            "input_tax_id": input_tax_id,
            "input_industry_code": input_industry_code,
            "files_manifest": files_manifest,
            "active_submodules": active_submodules,
            "raw_indices_payload": raw_indices_payload,
            "submodules_reports": submodules_reports,
            "llm_final_summary": llm_final_summary,
            "universal_score": universal_score,
            "verdict_category": verdict_category,
            "recommendation": recommendation,
            "failure_reason": failure_reason,
            "created_at": datetime.now(),
        }
        return self._mock_insert("analysis_runs", data)

    async def get_records_from_analysis_runs(
        self,
        find_only_first: bool = False,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        **filters: Any,
    ) -> DatabaseReport:
        return self._mock_select(
            "analysis_runs",
            filters,
            find_only_first=find_only_first,
            limit=limit,
            offset=offset,
        )

    async def update_records_in_analysis_runs(
        self,
        updates: Dict[str, Any],
        **filters: Any,
    ) -> DatabaseReport:
        return self._mock_update("analysis_runs", updates, filters)

    async def delete_records_from_analysis_runs(
        self,
        delete_only_first: bool = False,
        **filters: Any,
    ) -> DatabaseReport:
        return self._mock_delete(
            "analysis_runs", filters, delete_only_first=delete_only_first
        )

    async def add_record_to_analysis_logs(
        self,
        run_id: UUID,
        severity: str,
        stage: str,
        message: str,
        timestamp: Optional[datetime] = None,
        log_id: Optional[int] = None,
    ) -> DatabaseReport:
        current_seq = len(self._storage["analysis_logs"]) + 1
        data: Dict[str, Any] = {
            "log_id": log_id or current_seq,
            "run_id": run_id,
            "severity": severity,
            "stage": stage,
            "message": message,
            "timestamp": timestamp or datetime.now(),
        }
        return self._mock_insert("analysis_logs", data)

    async def get_records_from_analysis_logs(
        self,
        find_only_first: bool = False,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        **filters: Any,
    ) -> DatabaseReport:
        return self._mock_select(
            "analysis_logs",
            filters,
            find_only_first=find_only_first,
            limit=limit,
            offset=offset,
        )

    async def update_records_in_analysis_logs(
        self,
        updates: Dict[str, Any],
        **filters: Any,
    ) -> DatabaseReport:
        return self._mock_update("analysis_logs", updates, filters)

    async def delete_records_from_analysis_logs(
        self,
        delete_only_first: bool = False,
        **filters: Any,
    ) -> DatabaseReport:
        return self._mock_delete(
            "analysis_logs", filters, delete_only_first=delete_only_first
        )

    # =========================================================================
    # BULK INGESTION METHODS
    # =========================================================================

    async def bulk_insert_transactions(
        self, records: List[Dict[str, Any]]
    ) -> DatabaseReport:
        """Simulates high-velocity bulk insert for transactions in-memory."""
        if not records:
            return DatabaseReport(
                success=True,
                data=[],
                affected_rows=0,
                operation="BULK_INSERT",
                table_name="transactions",
            )
        inserted: List[Dict[str, Any]] = []
        for r in records:
            rec = copy.deepcopy(r)
            if "transaction_id" not in rec or rec["transaction_id"] is None:
                rec["transaction_id"] = uuid4()
            if rec.get("amount") is not None:
                rec["amount"] = abs(rec["amount"])
            self._storage["transactions"].append(rec)
            inserted.append(rec)
        return DatabaseReport(
            success=True,
            data=inserted,
            affected_rows=len(inserted),
            operation="BULK_INSERT",
            table_name="transactions",
        )

    async def bulk_insert_invoices(
        self, records: List[Dict[str, Any]]
    ) -> DatabaseReport:
        """Simulates high-velocity bulk insert for invoices in-memory."""
        if not records:
            return DatabaseReport(
                success=True,
                data=[],
                affected_rows=0,
                operation="BULK_INSERT",
                table_name="invoices",
            )
        inserted: List[Dict[str, Any]] = []
        for r in records:
            rec = copy.deepcopy(r)
            if "invoice_id" not in rec or rec["invoice_id"] is None:
                rec["invoice_id"] = uuid4()
            if rec.get("gross_amount") is not None:
                rec["gross_amount"] = abs(rec["gross_amount"])
            self._storage["invoices"].append(rec)
            inserted.append(rec)
        return DatabaseReport(
            success=True,
            data=inserted,
            affected_rows=len(inserted),
            operation="BULK_INSERT",
            table_name="invoices",
        )

