"""
Production-grade Asynchronous Data Loader for the Underwriting Analytical Core.
Bridges PostgreSQL data layer (Database) and deterministic ML submodules via CompanyDataSnapshot.
"""

from __future__ import annotations

import asyncio
from datetime import date, datetime
from decimal import Decimal
import logging
from typing import Any, List, Optional
from uuid import UUID, uuid4

from ..db.connection import Database
from ..db.models import (
    BankAccountRecord,
    BusinessRecord,
    CompanyDataSnapshot,
    CounterpartyRecord,
    CounterpartyRole,
    CreditObligationRecord,
    FacilityType,
    InvoiceRecord,
    InvoiceStatus,
    InvoiceType,
    LiquidityClass,
    MacroSectorMetricRecord,
    ShareholderRecord,
    TransactionCategory,
    TransactionDirection,
    TransactionRecord,
    WebReputationRecord,
)

logger: logging.Logger = logging.getLogger("smart_credit.ml")


class CompanyDataLoader:
    """
    Asynchronous data aggregator loading relational enterprise financial graphs
    from PostgreSQL and constructing typed CompanyDataSnapshot instances for ML evaluation.
    """

    def __init__(self, db: Database) -> None:
        self.db = db

    # =========================================================================
    # TYPE COERCION AND GRACEFUL PARSING HELPERS
    # =========================================================================

    @staticmethod
    def _to_uuid(val: Any) -> Optional[UUID]:
        if val is None:
            return None
        if isinstance(val, UUID):
            return val
        if isinstance(val, str) and val.strip():
            try:
                return UUID(val.strip())
            except ValueError:
                return None
        return None

    @staticmethod
    def _to_date(val: Any) -> Optional[date]:
        if val is None:
            return None
        if isinstance(val, datetime):
            return val.date()
        if isinstance(val, date):
            return val
        if isinstance(val, str) and val.strip():
            try:
                cleaned = val.strip().split("T")[0].split(" ")[0]
                return date.fromisoformat(cleaned)
            except Exception:
                return None
        return None

    @staticmethod
    def _to_datetime(val: Any) -> Optional[datetime]:
        if val is None:
            return None
        if isinstance(val, datetime):
            return val
        if isinstance(val, date):
            return datetime.combine(val, datetime.min.time())
        if isinstance(val, str) and val.strip():
            try:
                return datetime.fromisoformat(val.strip())
            except Exception:
                return None
        return None

    @staticmethod
    def _to_decimal(val: Any, default: Decimal = Decimal("0.00")) -> Decimal:
        if val is None:
            return default
        if isinstance(val, Decimal):
            return val
        try:
            return Decimal(str(val))
        except Exception:
            return default

    @staticmethod
    def _to_int(val: Any, default: int = 0) -> int:
        if val is None:
            return default
        try:
            return int(val)
        except Exception:
            return default

    @staticmethod
    def _to_bool(val: Any, default: bool = False) -> bool:
        if val is None:
            return default
        if isinstance(val, bool):
            return val
        if isinstance(val, str):
            return val.lower() in ("true", "1", "yes", "t")
        return bool(val)

    # =========================================================================
    # RECORD PARSERS
    # =========================================================================

    def _parse_business(self, row: dict[str, Any], fallback_id: UUID) -> BusinessRecord:
        biz_id = self._to_uuid(row.get("business_id")) or fallback_id
        reg_date = self._to_date(row.get("registration_date")) or date.today()
        return BusinessRecord(
            business_id=biz_id,
            tax_id=str(row.get("tax_id", "")),
            legal_name=str(row.get("legal_name", "")),
            industry_code=str(row.get("industry_code", "")),
            registration_date=reg_date,
            total_board_seats=self._to_int(row.get("total_board_seats"), 1),
            independent_directors_count=self._to_int(
                row.get("independent_directors_count"), 0
            ),
        )

    def _parse_shareholders(
        self, data: Any, fallback_business_id: UUID
    ) -> List[ShareholderRecord]:
        if not data:
            return []
        raw_list = data if isinstance(data, list) else [data]
        records: List[ShareholderRecord] = []
        for r in raw_list:
            if not isinstance(r, dict):
                continue
            biz_id = self._to_uuid(r.get("business_id")) or fallback_business_id
            records.append(
                ShareholderRecord(
                    ownership_id=self._to_uuid(r.get("ownership_id")) or uuid4(),
                    business_id=biz_id,
                    shareholder_name=str(r.get("shareholder_name", "")),
                    equity_percentage=self._to_decimal(
                        r.get("equity_percentage"), Decimal("0.00")
                    ),
                    is_management_member=self._to_bool(
                        r.get("is_management_member"), False
                    ),
                )
            )
        return records

    def _parse_web_reputation(
        self, data: Any, fallback_business_id: UUID
    ) -> Optional[WebReputationRecord]:
        if not data:
            return None
        r = data[0] if isinstance(data, list) else data
        if not isinstance(r, dict):
            return None
        biz_id = self._to_uuid(r.get("business_id")) or fallback_business_id
        scan_ts = self._to_datetime(r.get("scan_timestamp")) or datetime.now()
        news_score = (
            self._to_decimal(r["news_sentiment_score"])
            if r.get("news_sentiment_score") is not None
            else None
        )
        traffic = (
            self._to_int(r["web_traffic_monthly_visits"])
            if r.get("web_traffic_monthly_visits") is not None
            else None
        )
        return WebReputationRecord(
            record_id=self._to_uuid(r.get("record_id")) or uuid4(),
            business_id=biz_id,
            scan_timestamp=scan_ts,
            active_lawsuits_count=self._to_int(r.get("active_lawsuits_count"), 0),
            total_lawsuit_claims_amount=self._to_decimal(
                r.get("total_lawsuit_claims_amount"), Decimal("0.00")
            ),
            is_in_sanctions_list=self._to_bool(
                r.get("is_in_sanctions_list"), False
            ),
            news_sentiment_score=news_score,
            web_traffic_monthly_visits=traffic,
        )

    def _parse_macro_sector_metrics(
        self, data: Any, expected_industry_code: str
    ) -> Optional[MacroSectorMetricRecord]:
        if not data:
            return None
        r = data[0] if isinstance(data, list) else data
        if not isinstance(r, dict):
            return None
        return MacroSectorMetricRecord(
            metric_id=self._to_uuid(r.get("metric_id")) or uuid4(),
            industry_code=str(r.get("industry_code", expected_industry_code)),
            reference_date=self._to_date(r.get("reference_date")) or date.today(),
            sector_growth_rate_yoy=self._to_decimal(
                r.get("sector_growth_rate_yoy"), Decimal("0.00")
            ),
            sector_default_rate=self._to_decimal(
                r.get("sector_default_rate"), Decimal("0.00")
            ),
            risk_outlook_score=self._to_int(r.get("risk_outlook_score"), 5),
        )

    def _parse_counterparties(
        self, data: Any, fallback_business_id: UUID
    ) -> List[CounterpartyRecord]:
        if not data:
            return []
        raw_list = data if isinstance(data, list) else [data]
        records: List[CounterpartyRecord] = []
        for r in raw_list:
            if not isinstance(r, dict):
                continue
            biz_id = self._to_uuid(r.get("business_id")) or fallback_business_id
            role_raw = str(r.get("counterparty_role", "CLIENT")).upper()
            try:
                role = CounterpartyRole(role_raw)
            except ValueError:
                role = CounterpartyRole.CLIENT
            records.append(
                CounterpartyRecord(
                    counterparty_id=self._to_uuid(r.get("counterparty_id")) or uuid4(),
                    business_id=biz_id,
                    legal_name=str(r.get("legal_name", "")),
                    counterparty_role=role,
                    tax_id=str(r["tax_id"]) if r.get("tax_id") is not None else None,
                )
            )
        return records

    def _parse_invoices(
        self, data: Any, fallback_business_id: UUID
    ) -> List[InvoiceRecord]:
        if not data:
            return []
        raw_list = data if isinstance(data, list) else [data]
        records: List[InvoiceRecord] = []
        for r in raw_list:
            if not isinstance(r, dict):
                continue
            biz_id = self._to_uuid(r.get("business_id")) or fallback_business_id
            cp_id = self._to_uuid(r.get("counterparty_id")) or uuid4()
            inv_type_raw = str(r.get("invoice_type", "RECEIVABLE")).upper()
            try:
                inv_type = InvoiceType(inv_type_raw)
            except ValueError:
                inv_type = InvoiceType.RECEIVABLE

            status_raw = str(r.get("status", "OUTSTANDING")).upper()
            if status_raw == "PAID":
                status = InvoiceStatus.SETTLED
            else:
                try:
                    status = InvoiceStatus(status_raw)
                except ValueError:
                    status = InvoiceStatus.OUTSTANDING

            records.append(
                InvoiceRecord(
                    invoice_id=self._to_uuid(r.get("invoice_id")) or uuid4(),
                    business_id=biz_id,
                    counterparty_id=cp_id,
                    invoice_type=inv_type,
                    gross_amount=self._to_decimal(
                        r.get("gross_amount"), Decimal("0.00")
                    ),
                    issue_date=self._to_date(r.get("issue_date")) or date.today(),
                    due_date=self._to_date(r.get("due_date")) or date.today(),
                    status=status,
                    actual_payment_date=self._to_date(r.get("actual_payment_date")),
                )
            )
        return records

    def _parse_bank_accounts(
        self, data: Any, fallback_business_id: UUID
    ) -> List[BankAccountRecord]:
        if not data:
            return []
        raw_list = data if isinstance(data, list) else [data]
        records: List[BankAccountRecord] = []
        for r in raw_list:
            if not isinstance(r, dict):
                continue
            biz_id = self._to_uuid(r.get("business_id")) or fallback_business_id
            records.append(
                BankAccountRecord(
                    account_id=self._to_uuid(r.get("account_id")) or uuid4(),
                    business_id=biz_id,
                    currency=str(r.get("currency", "MDL")),
                    current_balance=self._to_decimal(
                        r.get("current_balance"), Decimal("0.00")
                    ),
                    overdraft_limit=self._to_decimal(
                        r.get("overdraft_limit"), Decimal("0.00")
                    ),
                )
            )
        return records

    def _parse_transactions(
        self, data: Any, fallback_business_id: UUID
    ) -> List[TransactionRecord]:
        if not data:
            return []
        raw_list = data if isinstance(data, list) else [data]
        records: List[TransactionRecord] = []
        for r in raw_list:
            if not isinstance(r, dict):
                continue
            biz_id = self._to_uuid(r.get("business_id")) or fallback_business_id
            acc_id = self._to_uuid(r.get("account_id")) or uuid4()
            dir_raw = str(r.get("direction", "INFLOW")).upper()
            try:
                direction = TransactionDirection(dir_raw)
            except ValueError:
                direction = TransactionDirection.INFLOW

            cat_raw = str(r.get("category", "OTHER")).upper()
            if cat_raw == "REVENUE":
                category = TransactionCategory.CLIENT_REVENUE
            elif cat_raw == "OPERATING_EXPENSE":
                category = TransactionCategory.SUPPLIER_PAYMENT
            elif cat_raw == "DEBT_SERVICE":
                category = TransactionCategory.CREDIT_REPAYMENT
            else:
                try:
                    category = TransactionCategory(cat_raw)
                except ValueError:
                    category = TransactionCategory.OTHER

            liq_raw = str(r.get("liquidity_class", "IMMEDIATE_CASH")).upper()
            try:
                liq_class = LiquidityClass(liq_raw)
            except ValueError:
                liq_class = LiquidityClass.IMMEDIATE_CASH

            records.append(
                TransactionRecord(
                    transaction_id=self._to_uuid(r.get("transaction_id")) or uuid4(),
                    business_id=biz_id,
                    account_id=acc_id,
                    timestamp=self._to_datetime(r.get("timestamp")) or datetime.now(),
                    amount=self._to_decimal(r.get("amount"), Decimal("0.00")),
                    direction=direction,
                    category=category,
                    liquidity_class=liq_class,
                    counterparty_id=self._to_uuid(r.get("counterparty_id")),
                    invoice_id=self._to_uuid(r.get("invoice_id")),
                )
            )
        return records

    def _parse_credit_obligations(
        self, data: Any, fallback_business_id: UUID
    ) -> List[CreditObligationRecord]:
        if not data:
            return []
        raw_list = data if isinstance(data, list) else [data]
        records: List[CreditObligationRecord] = []
        for r in raw_list:
            if not isinstance(r, dict):
                continue
            biz_id = self._to_uuid(r.get("business_id")) or fallback_business_id
            fac_raw = str(r.get("facility_type", "TERM_LOAN")).upper()
            try:
                fac_type = FacilityType(fac_raw)
            except ValueError:
                fac_type = FacilityType.TERM_LOAN

            records.append(
                CreditObligationRecord(
                    obligation_id=self._to_uuid(r.get("obligation_id")) or uuid4(),
                    business_id=biz_id,
                    lender_name=str(r.get("lender_name", "")),
                    facility_type=fac_type,
                    principal_amount=self._to_decimal(
                        r.get("principal_amount"), Decimal("0.00")
                    ),
                    outstanding_balance=self._to_decimal(
                        r.get("outstanding_balance"), Decimal("0.00")
                    ),
                    monthly_payment=self._to_decimal(
                        r.get("monthly_payment"), Decimal("0.00")
                    ),
                    past_due_30d_count=self._to_int(r.get("past_due_30d_count"), 0),
                    past_due_90d_count=self._to_int(r.get("past_due_90d_count"), 0),
                    historical_defaults_count=self._to_int(
                        r.get("historical_defaults_count"), 0
                    ),
                )
            )
        return records

    # =========================================================================
    # MASTER SNAPSHOT LOADING ORCHESTRATOR
    # =========================================================================

    async def load_snapshot(
        self,
        business_id: UUID,
        as_of_date: Optional[date] = None,
    ) -> CompanyDataSnapshot:
        """
        Asynchronously fetches and compiles all 9 relational entities into a CompanyDataSnapshot.

        :param business_id: Target company UUID.
        :param as_of_date: Evaluation cutoff date (defaults to date.today()).
        :return: Strongly typed CompanyDataSnapshot.
        :raises ValueError: If company record does not exist in businesses table.
        """
        effective_date = as_of_date or date.today()
        effective_biz_id = (
            business_id
            if isinstance(business_id, UUID)
            else UUID(str(business_id))
        )

        logger.info(
            "Initiating financial snapshot load for business %s as of %s",
            effective_biz_id,
            effective_date,
        )

        # Step 1: Fetch core business identity
        biz_report = await self.db.get_records_from_businesses(
            find_only_first=True, business_id=effective_biz_id
        )
        if not biz_report.success or not biz_report.data:
            logger.error(
                "Business record not found for id %s (error: %s)",
                effective_biz_id,
                biz_report.error,
            )
            raise ValueError(f"Business not found: {effective_biz_id}")

        biz_data = (
            biz_report.data[0]
            if isinstance(biz_report.data, list)
            else biz_report.data
        )
        business_record = self._parse_business(biz_data, effective_biz_id)

        # Step 2: Concurrently query all 7 related business entities
        (
            sh_rep,
            web_rep,
            cp_rep,
            inv_rep,
            ba_rep,
            tx_rep,
            co_rep,
        ) = await asyncio.gather(
            self.db.get_records_from_shareholders(business_id=effective_biz_id),
            self.db.get_records_from_web_reputation(
                find_only_first=True, business_id=effective_biz_id
            ),
            self.db.get_records_from_counterparties(business_id=effective_biz_id),
            self.db.get_records_from_invoices(business_id=effective_biz_id),
            self.db.get_records_from_bank_accounts(business_id=effective_biz_id),
            self.db.get_records_from_transactions(business_id=effective_biz_id),
            self.db.get_records_from_credit_obligations(business_id=effective_biz_id),
        )

        # Step 3: Query macroeconomic metrics by industry code
        macro_metrics = None
        if business_record.industry_code:
            clean_ind = business_record.industry_code.strip()
            macro_rep = await self.db.get_records_from_macro_sector_metrics(
                find_only_first=True,
                industry_code=clean_ind,
            )
            if macro_rep.success and macro_rep.data:
                macro_metrics = self._parse_macro_sector_metrics(
                    macro_rep.data, clean_ind
                )
            else:
                logger.debug(
                    "No macro sector metrics found for industry %s",
                    clean_ind,
                )

        # Step 4: Parse records with graceful degradation
        shareholders = (
            self._parse_shareholders(sh_rep.data, effective_biz_id)
            if sh_rep.success
            else []
        )
        web_reputation = (
            self._parse_web_reputation(web_rep.data, effective_biz_id)
            if web_rep.success
            else None
        )
        counterparties = (
            self._parse_counterparties(cp_rep.data, effective_biz_id)
            if cp_rep.success
            else []
        )
        invoices = (
            self._parse_invoices(inv_rep.data, effective_biz_id)
            if inv_rep.success
            else []
        )
        bank_accounts = (
            self._parse_bank_accounts(ba_rep.data, effective_biz_id)
            if ba_rep.success
            else []
        )
        transactions = (
            self._parse_transactions(tx_rep.data, effective_biz_id)
            if tx_rep.success
            else []
        )
        credit_obligations = (
            self._parse_credit_obligations(co_rep.data, effective_biz_id)
            if co_rep.success
            else []
        )

        snapshot = CompanyDataSnapshot(
            business=business_record,
            shareholders=shareholders,
            web_reputation=web_reputation,
            macro_sector_metrics=macro_metrics,
            counterparties=counterparties,
            invoices=invoices,
            bank_accounts=bank_accounts,
            transactions=transactions,
            credit_obligations=credit_obligations,
            as_of_date=effective_date,
            business_id=effective_biz_id,
        )

        logger.info(
            "Successfully compiled CompanyDataSnapshot for %s (%s). "
            "Shareholders: %d, Counterparties: %d, Invoices: %d, Accounts: %d, "
            "Transactions: %d, Obligations: %d",
            business_record.legal_name,
            effective_biz_id,
            len(shareholders),
            len(counterparties),
            len(invoices),
            len(bank_accounts),
            len(transactions),
            len(credit_obligations),
        )

        return snapshot


__all__ = [
    "CompanyDataLoader",
]

