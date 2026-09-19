"""
Production-grade Asynchronous Data Access Layer (DAL) for the Smart Credit System.
Target: src/fintech_app/db/connection.py
Specification: docs/database_architecture-v2.md
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
import logging
import os
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID, uuid4

try:
    import psycopg
    from psycopg import sql
    from psycopg.rows import dict_row
    from psycopg.types.json import Jsonb
    from psycopg_pool import AsyncConnectionPool
except ModuleNotFoundError:
    psycopg = None  # type: ignore
    sql = None  # type: ignore
    dict_row = None  # type: ignore
    Jsonb = None  # type: ignore
    AsyncConnectionPool = Any  # type: ignore

try:
    from src.fintech_app.db.models import DatabaseReport
except ModuleNotFoundError:
    from fintech_app.db.models import DatabaseReport

logger = logging.getLogger("smart_credit.db.connection")


class Database:
    """
    Production-grade asynchronous database client and connection pool wrapper
    leveraging psycopg v3 and psycopg_pool.
    """

    def __init__(
        self,
        pool: Optional[AsyncConnectionPool] = None,
        conninfo: Optional[str] = None,
        min_size: int = 4,
        max_size: int = 20,
        max_idle: float = 300.0,
    ) -> None:
        self._managed_pool = False
        if pool is not None:
            self.pool = pool
        else:
            if AsyncConnectionPool is Any or psycopg is None:
                raise RuntimeError(
                    "psycopg and psycopg-pool must be installed to initialize Database. "
                    "Use MockDatabase for offline testing."
                )
            if conninfo is None:
                host = os.getenv("POSTGRES_SERVER", "localhost")
                port = os.getenv("POSTGRES_PORT", "5432")
                user = os.getenv("POSTGRES_USER", "postgres")
                password = os.getenv("POSTGRES_PASSWORD", "postgres")
                dbname = os.getenv("POSTGRES_DB", "graeae_eye_db")
                conninfo = (
                    f"host={host} port={port} user={user} password={password} dbname={dbname}"
                )

            self.pool = AsyncConnectionPool(
                conninfo=conninfo,
                min_size=min_size,
                max_size=max_size,
                max_idle=max_idle,
                open=False,
                kwargs={"row_factory": dict_row},
            )
            self._managed_pool = True

    async def open(self) -> None:
        """Opens the managed connection pool if created internally."""
        if self._managed_pool and self.pool is not None:
            await self.pool.open()

    async def close(self) -> None:
        """Safely drains and closes the managed connection pool."""
        if self._managed_pool and self.pool is not None:
            await self.pool.close()

    async def health_check(self) -> bool:
        """Verifies database connectivity by executing SELECT 1."""
        try:
            async with self.pool.connection() as conn:
                async with conn.cursor() as cur:
                    await cur.execute("SELECT 1;")
                    res = await cur.fetchone()
                    return res is not None
        except Exception as exc:
            logger.warning("Database health check failed: %s", exc)
            return False

    async def __aenter__(self) -> Database:
        await self.open()
        return self

    async def __aexit__(
        self,
        exc_type: Optional[type],
        exc_val: Optional[BaseException],
        exc_tb: Optional[Any],
    ) -> None:
        await self.close()

    # =========================================================================
    # CORE EXECUTION HELPERS
    # =========================================================================

    def _build_where_clause(
        self, filters: Dict[str, Any]
    ) -> Tuple[sql.Composed, List[Any]]:
        """
        Dynamically constructs parameterized WHERE conditions from a filter dictionary.
        """
        conditions: List[sql.Composed] = []
        values: List[Any] = []
        for col, val in filters.items():
            if val is not None:
                conditions.append(sql.SQL("{col} = %s").format(col=sql.Identifier(col)))
                if hasattr(val, "value") and isinstance(val.value, str):
                    values.append(val.value)
                else:
                    values.append(val)
        if not conditions:
            return sql.SQL(""), []
        return sql.SQL(" WHERE ") + sql.SQL(" AND ").join(conditions), values

    async def _execute_insert(
        self,
        table_name: str,
        data: Dict[str, Any],
        returning: bool = True,
    ) -> DatabaseReport:
        """Executes a parameterized INSERT operation returning DatabaseReport."""
        try:
            cols = list(data.keys())
            vals: List[Any] = []
            for col in cols:
                v = data[col]
                if isinstance(v, (dict, list)):
                    vals.append(Jsonb(v))
                elif hasattr(v, "value") and isinstance(v.value, str):
                    vals.append(v.value)
                else:
                    vals.append(v)

            if returning:
                query = sql.SQL(
                    "INSERT INTO {table} ({cols}) VALUES ({placeholders}) RETURNING *;"
                ).format(
                    table=sql.Identifier(table_name),
                    cols=sql.SQL(", ").join(sql.Identifier(c) for c in cols),
                    placeholders=sql.SQL(", ").join(sql.Placeholder() for _ in cols),
                )
            else:
                query = sql.SQL(
                    "INSERT INTO {table} ({cols}) VALUES ({placeholders});"
                ).format(
                    table=sql.Identifier(table_name),
                    cols=sql.SQL(", ").join(sql.Identifier(c) for c in cols),
                    placeholders=sql.SQL(", ").join(sql.Placeholder() for _ in cols),
                )

            async with self.pool.connection() as conn:
                async with conn.transaction():
                    async with conn.cursor() as cur:
                        await cur.execute(query, vals)
                        if returning:
                            row = await cur.fetchone()
                            result_data = dict(row) if row else None
                            return DatabaseReport(
                                success=True,
                                data=result_data,
                                affected_rows=1 if result_data else 0,
                                operation="INSERT",
                                table_name=table_name,
                            )
                        return DatabaseReport(
                            success=True,
                            affected_rows=cur.rowcount,
                            operation="INSERT",
                            table_name=table_name,
                        )
        except Exception as exc:
            logger.error("Insert failed on table %s: %s", table_name, exc, exc_info=True)
            return DatabaseReport(
                success=False,
                error=str(exc),
                affected_rows=0,
                operation="INSERT",
                table_name=table_name,
            )

    async def _execute_select(
        self,
        table_name: str,
        filters: Dict[str, Any],
        find_only_first: bool = False,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        order_by: Optional[str] = None,
    ) -> DatabaseReport:
        """Executes a parameterized SELECT query against table_name."""
        try:
            where_sql, values = self._build_where_clause(filters)
            query_parts = [
                sql.SQL("SELECT * FROM {table}").format(table=sql.Identifier(table_name)),
                where_sql,
            ]
            if order_by:
                parts = order_by.strip().split()
                col_part = sql.Identifier(parts[0])
                dir_part = (
                    sql.SQL("DESC")
                    if len(parts) > 1 and parts[1].upper() == "DESC"
                    else sql.SQL("ASC")
                )
                query_parts.append(
                    sql.SQL(" ORDER BY ") + col_part + sql.SQL(" ") + dir_part
                )

            if limit is not None:
                query_parts.append(sql.SQL(" LIMIT %s"))
                values.append(limit)
            elif find_only_first:
                query_parts.append(sql.SQL(" LIMIT 1"))

            if offset is not None:
                query_parts.append(sql.SQL(" OFFSET %s"))
                values.append(offset)

            query = sql.SQL("").join(query_parts)

            async with self.pool.connection() as conn:
                async with conn.transaction():
                    async with conn.cursor() as cur:
                        await cur.execute(query, values)
                        if find_only_first:
                            row = await cur.fetchone()
                            result_data = dict(row) if row else None
                            return DatabaseReport(
                                success=True,
                                data=result_data,
                                affected_rows=1 if result_data else 0,
                                operation="SELECT",
                                table_name=table_name,
                            )
                        rows = await cur.fetchall()
                        result_list = [dict(r) for r in rows]
                        return DatabaseReport(
                            success=True,
                            data=result_list,
                            affected_rows=len(result_list),
                            operation="SELECT",
                            table_name=table_name,
                        )
        except Exception as exc:
            logger.error("Select failed on table %s: %s", table_name, exc, exc_info=True)
            return DatabaseReport(
                success=False,
                error=str(exc),
                affected_rows=0,
                operation="SELECT",
                table_name=table_name,
            )

    async def _execute_update(
        self,
        table_name: str,
        updates: Dict[str, Any],
        filters: Dict[str, Any],
    ) -> DatabaseReport:
        """Executes a parameterized UPDATE query against table_name RETURNING *."""
        try:
            if not updates:
                return DatabaseReport(
                    success=True,
                    data=[],
                    affected_rows=0,
                    operation="UPDATE",
                    table_name=table_name,
                )

            set_clauses: List[sql.Composed] = []
            set_values: List[Any] = []
            for col, val in updates.items():
                set_clauses.append(sql.SQL("{col} = %s").format(col=sql.Identifier(col)))
                if isinstance(val, (dict, list)):
                    set_values.append(Jsonb(val))
                elif hasattr(val, "value") and isinstance(val.value, str):
                    set_values.append(val.value)
                else:
                    set_values.append(val)

            where_sql, where_values = self._build_where_clause(filters)
            all_values = set_values + where_values

            query = sql.SQL(
                "UPDATE {table} SET {assignments} {where_clause} RETURNING *;"
            ).format(
                table=sql.Identifier(table_name),
                assignments=sql.SQL(", ").join(set_clauses),
                where_clause=where_sql,
            )

            async with self.pool.connection() as conn:
                async with conn.transaction():
                    async with conn.cursor() as cur:
                        await cur.execute(query, all_values)
                        rows = await cur.fetchall()
                        result_list = [dict(r) for r in rows]
                        return DatabaseReport(
                            success=True,
                            data=result_list,
                            affected_rows=len(result_list),
                            operation="UPDATE",
                            table_name=table_name,
                        )
        except Exception as exc:
            logger.error("Update failed on table %s: %s", table_name, exc, exc_info=True)
            return DatabaseReport(
                success=False,
                error=str(exc),
                affected_rows=0,
                operation="UPDATE",
                table_name=table_name,
            )

    async def _execute_delete(
        self,
        table_name: str,
        filters: Dict[str, Any],
        delete_only_first: bool = False,
    ) -> DatabaseReport:
        """Executes a parameterized DELETE query against table_name."""
        try:
            where_sql, where_values = self._build_where_clause(filters)
            if delete_only_first:
                query = sql.SQL(
                    "DELETE FROM {table} WHERE ctid IN ("
                    "SELECT ctid FROM {table} {where_clause} LIMIT 1);"
                ).format(
                    table=sql.Identifier(table_name),
                    where_clause=where_sql,
                )
            else:
                query = sql.SQL("DELETE FROM {table} {where_clause};").format(
                    table=sql.Identifier(table_name),
                    where_clause=where_sql,
                )

            async with self.pool.connection() as conn:
                async with conn.transaction():
                    async with conn.cursor() as cur:
                        await cur.execute(query, where_values)
                        return DatabaseReport(
                            success=True,
                            affected_rows=cur.rowcount,
                            operation="DELETE",
                            table_name=table_name,
                        )
        except Exception as exc:
            logger.error("Delete failed on table %s: %s", table_name, exc, exc_info=True)
            return DatabaseReport(
                success=False,
                error=str(exc),
                affected_rows=0,
                operation="DELETE",
                table_name=table_name,
            )

    # =========================================================================
    # CLUSTER 1: CORPORATE IDENTITY & GOVERNANCE
    # =========================================================================

    # --- Table: businesses ---
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
        return await self._execute_insert("businesses", data)

    async def get_records_from_businesses(
        self,
        find_only_first: bool = False,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        **filters: Any,
    ) -> DatabaseReport:
        return await self._execute_select(
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
        return await self._execute_update("businesses", updates, filters)

    async def delete_records_from_businesses(
        self,
        delete_only_first: bool = False,
        **filters: Any,
    ) -> DatabaseReport:
        return await self._execute_delete(
            "businesses", filters, delete_only_first=delete_only_first
        )

    # --- Table: shareholders ---
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
        return await self._execute_insert("shareholders", data)

    async def get_records_from_shareholders(
        self,
        find_only_first: bool = False,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        **filters: Any,
    ) -> DatabaseReport:
        return await self._execute_select(
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
        return await self._execute_update("shareholders", updates, filters)

    async def delete_records_from_shareholders(
        self,
        delete_only_first: bool = False,
        **filters: Any,
    ) -> DatabaseReport:
        return await self._execute_delete(
            "shareholders", filters, delete_only_first=delete_only_first
        )

    # =========================================================================
    # CLUSTER 2: EXTERNAL INTELLIGENCE & MACRO DATA
    # =========================================================================

    # --- Table: web_reputation ---
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
        return await self._execute_insert("web_reputation", data)

    async def get_records_from_web_reputation(
        self,
        find_only_first: bool = False,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        **filters: Any,
    ) -> DatabaseReport:
        return await self._execute_select(
            "web_reputation",
            filters,
            find_only_first=find_only_first,
            limit=limit,
            offset=offset,
            order_by="scan_timestamp DESC",
        )

    async def update_records_in_web_reputation(
        self,
        updates: Dict[str, Any],
        **filters: Any,
    ) -> DatabaseReport:
        return await self._execute_update("web_reputation", updates, filters)

    async def delete_records_from_web_reputation(
        self,
        delete_only_first: bool = False,
        **filters: Any,
    ) -> DatabaseReport:
        return await self._execute_delete(
            "web_reputation", filters, delete_only_first=delete_only_first
        )

    # --- Table: macro_sector_metrics ---
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
        return await self._execute_insert("macro_sector_metrics", data)

    async def get_records_from_macro_sector_metrics(
        self,
        find_only_first: bool = False,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        **filters: Any,
    ) -> DatabaseReport:
        return await self._execute_select(
            "macro_sector_metrics",
            filters,
            find_only_first=find_only_first,
            limit=limit,
            offset=offset,
            order_by="reference_date DESC",
        )

    async def update_records_in_macro_sector_metrics(
        self,
        updates: Dict[str, Any],
        **filters: Any,
    ) -> DatabaseReport:
        return await self._execute_update("macro_sector_metrics", updates, filters)

    async def delete_records_from_macro_sector_metrics(
        self,
        delete_only_first: bool = False,
        **filters: Any,
    ) -> DatabaseReport:
        return await self._execute_delete(
            "macro_sector_metrics", filters, delete_only_first=delete_only_first
        )

    # =========================================================================
    # CLUSTER 3: COMMERCIAL GRAPH & CASH FLOW LEDGER
    # =========================================================================

    # --- Table: counterparties ---
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
        return await self._execute_insert("counterparties", data)

    async def get_records_from_counterparties(
        self,
        find_only_first: bool = False,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        **filters: Any,
    ) -> DatabaseReport:
        return await self._execute_select(
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
        return await self._execute_update("counterparties", updates, filters)

    async def delete_records_from_counterparties(
        self,
        delete_only_first: bool = False,
        **filters: Any,
    ) -> DatabaseReport:
        return await self._execute_delete(
            "counterparties", filters, delete_only_first=delete_only_first
        )

    # --- Table: invoices ---
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
            "gross_amount": abs(gross_amount) if gross_amount is not None else gross_amount,
            "issue_date": issue_date,
            "due_date": due_date,
            "actual_payment_date": actual_payment_date,
            "status": status,
        }
        return await self._execute_insert("invoices", data)

    async def get_records_from_invoices(
        self,
        find_only_first: bool = False,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        **filters: Any,
    ) -> DatabaseReport:
        return await self._execute_select(
            "invoices",
            filters,
            find_only_first=find_only_first,
            limit=limit,
            offset=offset,
            order_by="due_date ASC",
        )

    async def update_records_in_invoices(
        self,
        updates: Dict[str, Any],
        **filters: Any,
    ) -> DatabaseReport:
        return await self._execute_update("invoices", updates, filters)

    async def delete_records_from_invoices(
        self,
        delete_only_first: bool = False,
        **filters: Any,
    ) -> DatabaseReport:
        return await self._execute_delete(
            "invoices", filters, delete_only_first=delete_only_first
        )

    # --- Table: bank_accounts ---
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
        return await self._execute_insert("bank_accounts", data)

    async def get_records_from_bank_accounts(
        self,
        find_only_first: bool = False,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        **filters: Any,
    ) -> DatabaseReport:
        return await self._execute_select(
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
        return await self._execute_update("bank_accounts", updates, filters)

    async def delete_records_from_bank_accounts(
        self,
        delete_only_first: bool = False,
        **filters: Any,
    ) -> DatabaseReport:
        return await self._execute_delete(
            "bank_accounts", filters, delete_only_first=delete_only_first
        )

    # --- Table: transactions ---
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
        return await self._execute_insert("transactions", data)

    async def get_records_from_transactions(
        self,
        find_only_first: bool = False,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        **filters: Any,
    ) -> DatabaseReport:
        return await self._execute_select(
            "transactions",
            filters,
            find_only_first=find_only_first,
            limit=limit,
            offset=offset,
            order_by="timestamp DESC",
        )

    async def update_records_in_transactions(
        self,
        updates: Dict[str, Any],
        **filters: Any,
    ) -> DatabaseReport:
        return await self._execute_update("transactions", updates, filters)

    async def delete_records_from_transactions(
        self,
        delete_only_first: bool = False,
        **filters: Any,
    ) -> DatabaseReport:
        return await self._execute_delete(
            "transactions", filters, delete_only_first=delete_only_first
        )

    # =========================================================================
    # CLUSTER 4: LIABILITIES & DEBT FACILITIES
    # =========================================================================

    # --- Table: credit_obligations ---
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
        return await self._execute_insert("credit_obligations", data)

    async def get_records_from_credit_obligations(
        self,
        find_only_first: bool = False,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        **filters: Any,
    ) -> DatabaseReport:
        return await self._execute_select(
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
        return await self._execute_update("credit_obligations", updates, filters)

    async def delete_records_from_credit_obligations(
        self,
        delete_only_first: bool = False,
        **filters: Any,
    ) -> DatabaseReport:
        return await self._execute_delete(
            "credit_obligations", filters, delete_only_first=delete_only_first
        )

    # =========================================================================
    # CLUSTER 5: WEB APPLICATION IDENTITY & EXECUTION TELEMETRY
    # =========================================================================

    # --- Table: users ---
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
        return await self._execute_insert("users", data)

    async def get_records_from_users(
        self,
        find_only_first: bool = False,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        **filters: Any,
    ) -> DatabaseReport:
        return await self._execute_select(
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
        return await self._execute_update("users", updates, filters)

    async def delete_records_from_users(
        self,
        delete_only_first: bool = False,
        **filters: Any,
    ) -> DatabaseReport:
        return await self._execute_delete(
            "users", filters, delete_only_first=delete_only_first
        )

    # --- Table: user_settings ---
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
        return await self._execute_insert("user_settings", data)

    async def get_records_from_user_settings(
        self,
        find_only_first: bool = False,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        **filters: Any,
    ) -> DatabaseReport:
        return await self._execute_select(
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
        return await self._execute_update("user_settings", updates, filters)

    async def delete_records_from_user_settings(
        self,
        delete_only_first: bool = False,
        **filters: Any,
    ) -> DatabaseReport:
        return await self._execute_delete(
            "user_settings", filters, delete_only_first=delete_only_first
        )

    # --- Table: analysis_runs ---
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
        }
        return await self._execute_insert("analysis_runs", data)

    async def get_records_from_analysis_runs(
        self,
        find_only_first: bool = False,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        **filters: Any,
    ) -> DatabaseReport:
        return await self._execute_select(
            "analysis_runs",
            filters,
            find_only_first=find_only_first,
            limit=limit,
            offset=offset,
            order_by="created_at DESC",
        )

    async def update_records_in_analysis_runs(
        self,
        updates: Dict[str, Any],
        **filters: Any,
    ) -> DatabaseReport:
        return await self._execute_update("analysis_runs", updates, filters)

    async def delete_records_from_analysis_runs(
        self,
        delete_only_first: bool = False,
        **filters: Any,
    ) -> DatabaseReport:
        return await self._execute_delete(
            "analysis_runs", filters, delete_only_first=delete_only_first
        )

    # --- Table: analysis_logs ---
    async def add_record_to_analysis_logs(
        self,
        run_id: UUID,
        severity: str,
        stage: str,
        message: str,
        timestamp: Optional[datetime] = None,
        log_id: Optional[int] = None,
    ) -> DatabaseReport:
        data: Dict[str, Any] = {
            "run_id": run_id,
            "severity": severity,
            "stage": stage,
            "message": message,
            "timestamp": timestamp or datetime.now(),
        }
        if log_id is not None:
            data["log_id"] = log_id
        return await self._execute_insert("analysis_logs", data)

    async def get_records_from_analysis_logs(
        self,
        find_only_first: bool = False,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        **filters: Any,
    ) -> DatabaseReport:
        return await self._execute_select(
            "analysis_logs",
            filters,
            find_only_first=find_only_first,
            limit=limit,
            offset=offset,
            order_by="log_id ASC",
        )

    async def update_records_in_analysis_logs(
        self,
        updates: Dict[str, Any],
        **filters: Any,
    ) -> DatabaseReport:
        return await self._execute_update("analysis_logs", updates, filters)

    async def delete_records_from_analysis_logs(
        self,
        delete_only_first: bool = False,
        **filters: Any,
    ) -> DatabaseReport:
        return await self._execute_delete(
            "analysis_logs", filters, delete_only_first=delete_only_first
        )

    # =========================================================================
    # HIGH-VELOCITY BULK INGESTION VIA CURSOR.COPY()
    # =========================================================================

    async def bulk_insert_transactions(
        self, records: List[Dict[str, Any]]
    ) -> DatabaseReport:
        """
        High-velocity bulk streaming insertion into transactions table using cursor.copy().
        """
        if not records:
            return DatabaseReport(
                success=True,
                data=[],
                affected_rows=0,
                operation="BULK_INSERT",
                table_name="transactions",
            )
        try:
            cols = [
                "transaction_id",
                "business_id",
                "account_id",
                "counterparty_id",
                "invoice_id",
                "timestamp",
                "amount",
                "direction",
                "category",
                "liquidity_class",
            ]
            copy_sql = sql.SQL("COPY {table} ({fields}) FROM STDIN").format(
                table=sql.Identifier("transactions"),
                fields=sql.SQL(", ").join(sql.Identifier(c) for c in cols),
            )

            async with self.pool.connection() as conn:
                async with conn.transaction():
                    async with conn.cursor() as cur:
                        async with cur.copy(copy_sql) as copy_op:
                            for r in records:
                                tx_id = r.get("transaction_id") or uuid4()
                                biz_id = r["business_id"]
                                acc_id = r["account_id"]
                                cp_id = r.get("counterparty_id")
                                inv_id = r.get("invoice_id")
                                ts = r["timestamp"]
                                amt = (
                                    Decimal(str(r["amount"]))
                                    if not isinstance(r["amount"], Decimal)
                                    else r["amount"]
                                )
                                amt = abs(amt)
                                direction = (
                                    r["direction"].value
                                    if hasattr(r["direction"], "value")
                                    else str(r["direction"])
                                )
                                category = (
                                    r["category"].value
                                    if hasattr(r["category"], "value")
                                    else str(r["category"])
                                )
                                liq = r.get("liquidity_class", "IMMEDIATE_CASH")
                                liquidity_class = (
                                    liq.value if hasattr(liq, "value") else str(liq)
                                )

                                row = (
                                    tx_id,
                                    biz_id,
                                    acc_id,
                                    cp_id,
                                    inv_id,
                                    ts,
                                    amt,
                                    direction,
                                    category,
                                    liquidity_class,
                                )
                                await copy_op.write_row(row)

            return DatabaseReport(
                success=True,
                affected_rows=len(records),
                operation="BULK_INSERT",
                table_name="transactions",
            )
        except Exception as exc:
            logger.error("Bulk insert into transactions failed: %s", exc, exc_info=True)
            return DatabaseReport(
                success=False,
                error=str(exc),
                affected_rows=0,
                operation="BULK_INSERT",
                table_name="transactions",
            )

    async def bulk_insert_invoices(
        self, records: List[Dict[str, Any]]
    ) -> DatabaseReport:
        """
        High-velocity bulk streaming insertion into invoices table using cursor.copy().
        """
        if not records:
            return DatabaseReport(
                success=True,
                data=[],
                affected_rows=0,
                operation="BULK_INSERT",
                table_name="invoices",
            )
        try:
            cols = [
                "invoice_id",
                "business_id",
                "counterparty_id",
                "invoice_type",
                "gross_amount",
                "issue_date",
                "due_date",
                "actual_payment_date",
                "status",
            ]
            copy_sql = sql.SQL("COPY {table} ({fields}) FROM STDIN").format(
                table=sql.Identifier("invoices"),
                fields=sql.SQL(", ").join(sql.Identifier(c) for c in cols),
            )

            async with self.pool.connection() as conn:
                async with conn.transaction():
                    async with conn.cursor() as cur:
                        async with cur.copy(copy_sql) as copy_op:
                            for r in records:
                                inv_id = r.get("invoice_id") or uuid4()
                                biz_id = r["business_id"]
                                cp_id = r["counterparty_id"]
                                inv_type = (
                                    r["invoice_type"].value
                                    if hasattr(r["invoice_type"], "value")
                                    else str(r["invoice_type"])
                                )
                                gross = (
                                    Decimal(str(r["gross_amount"]))
                                    if not isinstance(r["gross_amount"], Decimal)
                                    else r["gross_amount"]
                                )
                                gross = abs(gross)
                                issue_date = r["issue_date"]
                                due_date = r["due_date"]
                                actual_payment_date = r.get("actual_payment_date")
                                status = (
                                    r["status"].value
                                    if hasattr(r["status"], "value")
                                    else str(r["status"])
                                )

                                row = (
                                    inv_id,
                                    biz_id,
                                    cp_id,
                                    inv_type,
                                    gross,
                                    issue_date,
                                    due_date,
                                    actual_payment_date,
                                    status,
                                )
                                await copy_op.write_row(row)

            return DatabaseReport(
                success=True,
                affected_rows=len(records),
                operation="BULK_INSERT",
                table_name="invoices",
            )
        except Exception as exc:
            logger.error("Bulk insert into invoices failed: %s", exc, exc_info=True)
            return DatabaseReport(
                success=False,
                error=str(exc),
                affected_rows=0,
                operation="BULK_INSERT",
                table_name="invoices",
            )


# Export MockDatabase convenience alias if needed
try:
    from src.fintech_app.db.mock_connection import MockDatabase
except ModuleNotFoundError:
    try:
        from fintech_app.db.mock_connection import MockDatabase
    except Exception:
        MockDatabase = None  # type: ignore
