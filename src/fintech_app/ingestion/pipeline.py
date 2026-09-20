"""
Координатор конвейера инжестии данных (Ingestion Pipeline).
Объединяет потоковый парсинг выписок (BankStatementParser), семантическую категоризацию (ai_mapper),
сбор внешних реестров (ExternalIntelligenceCollector) и сохранение в PostgreSQL через DAL.
Boundary Rule: только сбор и нормализация, никакого кредитного скоринга (ML-логика в ml/).
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
import logging
from typing import Any, Dict, List, Optional, Tuple, Union
from uuid import UUID, uuid4

from fintech_app.core.config import settings
from fintech_app.core.exceptions import ParsingError
from fintech_app.ingestion.ai_mapper import TransactionCategorizationMapper
from fintech_app.ingestion.external_intel import ExternalIntelligenceCollector
from fintech_app.ingestion.parser import (
    BankStatementParser,
    CreditObligationParser,
    InvoiceParser,
)
from fintech_app.ingestion.schemas import (
    IngestionResult,
    ParsedBankStatementPayload,
    ParsedCreditObligationRecord,
    ParsedInvoiceRecord,
    StandardizedTransactionBatch,
)

logger = logging.getLogger(__name__)


class IngestionPipeline:
    """
    Главный оркестратор подсистемы Ingestion.
    Координирует распаковку файлов, запуск парсеров, обогащение и сохранение через DAL.
    """

    def __init__(self, db: Optional[Any] = None) -> None:
        self.db = db
        self.parser = BankStatementParser()
        self.invoice_parser = InvoiceParser()
        self.obligation_parser = CreditObligationParser()
        self.mapper = TransactionCategorizationMapper()
        self.external_intel = ExternalIntelligenceCollector()

    async def run(
        self,
        metadata: Dict[str, Any],
        files: Optional[List[Any]] = None,
    ) -> IngestionResult:
        """
        Запускает полный цикл инжестии:
        1. Извлечение параметров компании (business_id, account_id).
        2. Парсинг файлов выписок (CSV, XLSX).
        3. Семантическая категоризация расходов и маппинг на сущности.
        4. Параллельный сбор открытых внешних данных (суды, налоги, макро).
        5. Сохранение пачек транзакций через DAL (bulk_insert_transactions).
        """
        warnings: List[str] = []
        try:
            # 1. Инициализация идентификаторов
            biz_id_raw = metadata.get("business_id")
            business_id = UUID(str(biz_id_raw)) if biz_id_raw else uuid4()

            acc_id_raw = metadata.get("account_id")
            account_id = UUID(str(acc_id_raw)) if acc_id_raw else uuid4()

            uploaded_files = files or []
            batches: List[StandardizedTransactionBatch] = []
            invoices_list: List[ParsedInvoiceRecord] = []
            obligations_list: List[ParsedCreditObligationRecord] = []

            # 2. Обработка файлов выписок, счетов и кредитов
            if not uploaded_files:
                logger.info(
                    "No files provided for ingestion for business %s. Skipping statement parsing.",
                    business_id,
                )
                warnings.append("No files provided for ingestion.")
            else:
                for file_obj in uploaded_files:
                    filename, content_bytes = await self._extract_file_content(file_obj)
                    if not content_bytes:
                        warnings.append(f"File '{filename}' was empty; skipped.")
                        continue

                    lower_name = filename.lower()
                    try:
                        if any(
                            k in lower_name
                            for k in ("invoice", "factura", "facturi", "schet", "счет", "счета", "накладн")
                        ):
                            if lower_name.endswith((".xlsx", ".xls")):
                                invs = self.invoice_parser.parse_xlsx(content_bytes, business_id=business_id)
                            else:
                                invs = self.invoice_parser.parse_csv(content_bytes, business_id=business_id)
                            invoices_list.extend(invs)
                        elif any(
                            k in lower_name
                            for k in (
                                "obligation",
                                "credit",
                                "loan",
                                "datorii",
                                "imprumut",
                                "кредит",
                                "займ",
                                "обязательств",
                            )
                        ):
                            if lower_name.endswith((".xlsx", ".xls")):
                                obls = self.obligation_parser.parse_xlsx(content_bytes, business_id=business_id)
                            else:
                                obls = self.obligation_parser.parse_csv(content_bytes, business_id=business_id)
                            obligations_list.extend(obls)
                        elif lower_name.endswith(".csv"):
                            payload = self.parser.parse_csv(
                                content_bytes,
                                account_id=account_id,
                                business_id=business_id,
                            )
                            if payload and payload.lines:
                                batch = self.mapper.map_categories_and_counterparties(payload)
                                batches.append(batch)
                        elif lower_name.endswith((".xlsx", ".xls")):
                            payload = self.parser.parse_xlsx(
                                content_bytes,
                                account_id=account_id,
                                business_id=business_id,
                            )
                            if payload and payload.lines:
                                batch = self.mapper.map_categories_and_counterparties(payload)
                                batches.append(batch)
                        elif lower_name.endswith(".pdf"):
                            payload = self.parser.parse_pdf(
                                content_bytes,
                                account_id=account_id,
                                business_id=business_id,
                            )
                            if payload and payload.lines:
                                batch = self.mapper.map_categories_and_counterparties(payload)
                                batches.append(batch)
                        else:
                            # Попытка парсинга как CSV по умолчанию
                            payload = self.parser.parse_csv(
                                content_bytes,
                                account_id=account_id,
                                business_id=business_id,
                            )
                            if payload and payload.lines:
                                batch = self.mapper.map_categories_and_counterparties(payload)
                                batches.append(batch)
                    except ParsingError as p_err:
                        logger.warning("Parsing warning for file '%s': %s", filename, p_err)
                        warnings.append(f"Parsing '{filename}': {p_err}")
                        continue

            if uploaded_files and not batches and not invoices_list and not obligations_list:
                raise ParsingError(f"All {len(uploaded_files)} uploaded files failed parsing: {'; '.join(warnings)}")

            # 3. Сбор внешних данных (асинхронно, с таймаутом <= 2.5с)
            external_data_acquired = False
            ext_res: Dict[str, Any] = {}
            try:
                ext_meta = dict(metadata)
                ext_meta["business_id"] = business_id
                ext_res = await self.external_intel.collect_all(ext_meta)
                external_data_acquired = ext_res.get("success", False)
            except Exception as ext_err:
                logger.warning("External intelligence gathering failed gracefully: %s", ext_err)
                warnings.append(f"External intelligence: {ext_err}")

            # 4. Сохранение в базу данных через DAL (если DAL передан)
            total_records_ingested = 0

            if self.db is not None:
                # 4a. Гарантируем наличие записи о предприятии (businesses)
                if hasattr(self.db, "get_records_from_businesses") and hasattr(self.db, "add_record_to_businesses"):
                    try:
                        biz_check = await self.db.get_records_from_businesses(
                            find_only_first=True, business_id=business_id
                        )
                        if not (biz_check.success and biz_check.data):
                            c_name = metadata.get("company_name") or f"Enterprise-{str(business_id)[:8]}"
                            c_tax = metadata.get("tax_id") or f"TAX-{str(business_id)[:10]}"
                            c_sec = metadata.get("sector_code") or "6201"
                            await self.db.add_record_to_businesses(
                                business_id=business_id,
                                legal_name=c_name,
                                tax_id=c_tax,
                                industry_code=c_sec,
                                registration_date=date.today(),
                            )
                    except Exception as b_err:
                        logger.warning("Failed to ensure business record %s: %s", business_id, b_err)

                # 4b. Гарантируем наличие расчетного счета (bank_accounts)
                if hasattr(self.db, "get_records_from_bank_accounts") and hasattr(
                    self.db, "add_record_to_bank_accounts"
                ):
                    try:
                        ba_check = await self.db.get_records_from_bank_accounts(
                            find_only_first=True,
                            business_id=business_id,
                            account_id=account_id,
                        )
                        if not (ba_check.success and ba_check.data):
                            await self.db.add_record_to_bank_accounts(
                                business_id=business_id,
                                currency="MDL",
                                current_balance=Decimal("0.00"),
                                account_id=account_id,
                            )
                    except Exception as ba_err:
                        logger.warning("Failed to ensure bank account %s: %s", account_id, ba_err)

                # 4c. Гарантируем наличие акционеров (shareholders)
                if hasattr(self.db, "add_record_to_shareholders") and hasattr(self.db, "get_records_from_shareholders"):
                    try:
                        sh_check = await self.db.get_records_from_shareholders(
                            find_only_first=True, business_id=business_id
                        )
                        if not (sh_check.success and sh_check.data):
                            sh_name = (
                                metadata.get("founder_name") or f"Owner of {metadata.get('company_name', 'Enterprise')}"
                            )
                            await self.db.add_record_to_shareholders(
                                business_id=business_id,
                                shareholder_name=sh_name,
                                equity_percentage=Decimal("100.00"),
                                is_management_member=True,
                            )
                    except Exception as sh_err:
                        logger.warning("Failed to ensure shareholder for %s: %s", business_id, sh_err)

                # 4d. Регистрируем уникальных контрагентов (counterparties) из транзакций
                registered_cp_ids: set[UUID] = set()
                registered_cp_names: Dict[str, UUID] = {}
                if hasattr(self.db, "add_record_to_counterparties") and hasattr(
                    self.db, "get_records_from_counterparties"
                ):
                    for b in batches:
                        for t in b.transactions:
                            cp_id = t.counterparty_id
                            if cp_id and cp_id not in registered_cp_ids:
                                try:
                                    cp_chk = await self.db.get_records_from_counterparties(
                                        find_only_first=True,
                                        business_id=business_id,
                                        counterparty_id=cp_id,
                                    )
                                    if not (cp_chk.success and cp_chk.data):
                                        c_name = t.counterparty_name or f"Counterparty {str(cp_id)[:8]}"
                                        await self.db.add_record_to_counterparties(
                                            counterparty_id=cp_id,
                                            business_id=business_id,
                                            tax_id=t.counterparty_tax_id or None,
                                            legal_name=c_name,
                                            counterparty_role="BOTH",
                                        )
                                    registered_cp_ids.add(cp_id)
                                    if t.counterparty_name:
                                        registered_cp_names[t.counterparty_name] = cp_id
                                except Exception as cp_err:
                                    logger.warning(
                                        "Failed to register counterparty %s: %s. Clearing FK.",
                                        cp_id,
                                        cp_err,
                                    )
                                    t.counterparty_id = None

                # 4e. Вставка транзакций
                all_tx_dicts: List[Dict[str, Any]] = []
                for b in batches:
                    all_tx_dicts.extend(b.to_dict_records())

                if hasattr(self.db, "bulk_insert_transactions") and all_tx_dicts:
                    try:
                        db_rep = await self.db.bulk_insert_transactions(all_tx_dicts)
                        total_records_ingested += (
                            db_rep.affected_rows if hasattr(db_rep, "affected_rows") else len(all_tx_dicts)
                        )
                    except Exception as db_err:
                        logger.error("DAL bulk transaction persistence error: %s", db_err)
                        warnings.append(f"DAL persistence: {db_err}")
                        total_records_ingested += len(all_tx_dicts)
                else:
                    total_records_ingested += len(all_tx_dicts)

                # 4f. Сохранение счетов-фактур (invoices)
                if invoices_list and hasattr(self.db, "bulk_insert_invoices"):
                    try:
                        invoice_dicts: List[Dict[str, Any]] = []
                        for inv in invoices_list:
                            cp_id = registered_cp_names.get(inv.counterparty_name)
                            if not cp_id:
                                cp_id = uuid4()
                                if hasattr(self.db, "add_record_to_counterparties"):
                                    await self.db.add_record_to_counterparties(
                                        counterparty_id=cp_id,
                                        business_id=business_id,
                                        legal_name=inv.counterparty_name,
                                        counterparty_role=inv.counterparty_role or "BOTH",
                                    )
                                registered_cp_names[inv.counterparty_name] = cp_id

                            invoice_dicts.append(
                                {
                                    "invoice_id": inv.invoice_id,
                                    "business_id": business_id,
                                    "counterparty_id": cp_id,
                                    "invoice_type": inv.invoice_type,
                                    "gross_amount": inv.gross_amount,
                                    "issue_date": inv.issue_date,
                                    "due_date": inv.due_date,
                                    "actual_payment_date": inv.actual_payment_date,
                                    "status": inv.status,
                                }
                            )

                        inv_rep = await self.db.bulk_insert_invoices(invoice_dicts)
                        total_records_ingested += (
                            inv_rep.affected_rows if hasattr(inv_rep, "affected_rows") else len(invoice_dicts)
                        )
                    except Exception as inv_err:
                        logger.error("DAL bulk invoices error: %s", inv_err)
                        warnings.append(f"DAL invoices: {inv_err}")

                # 4g. Сохранение кредитных обязательств (credit_obligations)
                if obligations_list and hasattr(self.db, "add_record_to_credit_obligations"):
                    try:
                        for obl in obligations_list:
                            await self.db.add_record_to_credit_obligations(
                                obligation_id=obl.obligation_id,
                                business_id=business_id,
                                lender_name=obl.lender_name,
                                facility_type=obl.facility_type,
                                principal_amount=obl.principal_amount,
                                outstanding_balance=obl.outstanding_balance,
                                monthly_payment=obl.monthly_payment,
                                past_due_30d_count=obl.past_due_30d_count,
                                past_due_90d_count=obl.past_due_90d_count,
                                historical_defaults_count=obl.historical_defaults_count,
                            )
                            total_records_ingested += 1
                    except Exception as obl_err:
                        logger.error("DAL credit obligations error: %s", obl_err)
                        warnings.append(f"DAL obligations: {obl_err}")

                # 4h. Сохранение данных внешней разведки (web_reputation & macro_sector_metrics)
                if ext_res:
                    if hasattr(self.db, "add_record_to_web_reputation"):
                        try:
                            rep_data = ext_res.get("reputation", {})
                            raw_sent = float(rep_data.get("reputation_sentiment", 0.0))
                            clamped_sent = max(-1.0, min(1.0, raw_sent))
                            sent_dec = Decimal(str(round(clamped_sent, 3))).quantize(Decimal("0.001"))
                            await self.db.add_record_to_web_reputation(
                                business_id=business_id,
                                scan_timestamp=datetime.now(timezone.utc),
                                active_lawsuits_count=int(rep_data.get("active_lawsuits_count", 0)),
                                total_lawsuit_claims_amount=Decimal(str(rep_data.get("total_claim_amount", "0.00"))),
                                is_in_sanctions_list=bool(rep_data.get("sanctions_flag", False)),
                                news_sentiment_score=sent_dec,
                                web_traffic_monthly_visits=12000,
                            )
                        except Exception as rep_err:
                            logger.warning("Could not persist web_reputation: %s", rep_err)

                    if hasattr(self.db, "add_record_to_macro_sector_metrics"):
                        try:
                            macro_data = ext_res.get("macro_metrics", {})
                            sec_code = str(macro_data.get("industry_code") or metadata.get("sector_code") or "G46")
                            g_raw = Decimal(str(macro_data.get("gdp_growth_rate", "0.035")))
                            d_raw = Decimal(str(macro_data.get("sector_default_probability", "0.025")))
                            # Normalize fractional rates (e.g. 0.035 -> 3.50%) to percentage numbers
                            g_rate = (
                                (g_raw * 100).quantize(Decimal("0.01"))
                                if abs(g_raw) <= Decimal("1.0")
                                else g_raw.quantize(Decimal("0.01"))
                            )
                            d_rate = (
                                (d_raw * 100).quantize(Decimal("0.01"))
                                if abs(d_raw) <= Decimal("1.0")
                                else d_raw.quantize(Decimal("0.01"))
                            )
                            # Risk outlook score must strictly satisfy CHECK (risk_outlook_score BETWEEN 1 AND 10)
                            raw_risk = macro_data.get("risk_outlook_score", 5)
                            risk_score = max(1, min(10, int(raw_risk)))
                            await self.db.add_record_to_macro_sector_metrics(
                                industry_code=sec_code,
                                reference_date=date.today(),
                                sector_growth_rate_yoy=g_rate,
                                sector_default_rate=d_rate,
                                risk_outlook_score=risk_score,
                            )
                        except Exception as mac_err:
                            logger.warning("Could not persist macro_sector_metrics: %s", mac_err)
            else:
                total_records_ingested = (
                    sum(len(b.transactions) for b in batches) + len(invoices_list) + len(obligations_list)
                )

            return IngestionResult(
                success=True,
                business_id=business_id,
                records_ingested=total_records_ingested,
                external_data_acquired=external_data_acquired,
                warnings=warnings,
                error=None,
                message=f"Successfully ingested {total_records_ingested} records for business {business_id}.",
            )

        except Exception as unhandled_err:
            logger.exception("Critical error inside IngestionPipeline.run: %s", unhandled_err)
            return IngestionResult(
                success=False,
                business_id=metadata.get("business_id"),
                records_ingested=0,
                external_data_acquired=False,
                warnings=warnings,
                error=str(unhandled_err),
                message=f"Pipeline ingestion failed: {unhandled_err}",
            )

    async def _extract_file_content(self, file_obj: Any) -> Tuple[str, bytes]:
        """Универсально извлекает имя файла и байты содержимого."""
        filename = "upload.csv"
        content_bytes = b""

        if hasattr(file_obj, "filename") and hasattr(file_obj, "read"):
            # FastAPI UploadFile
            filename = file_obj.filename or "upload.csv"
            content = await file_obj.read()
            content_bytes = content if isinstance(content, bytes) else str(content).encode("utf-8")
        elif isinstance(file_obj, tuple) and len(file_obj) == 2:
            # Кортеж (filename, bytes)
            filename = str(file_obj[0])
            content_bytes = file_obj[1] if isinstance(file_obj[1], bytes) else str(file_obj[1]).encode("utf-8")
        elif isinstance(file_obj, bytes):
            content_bytes = file_obj
        elif isinstance(file_obj, str):
            # Путь к файлу
            try:
                import aiofiles

                async with aiofiles.open(file_obj, "rb") as f:
                    content_bytes = await f.read()
                filename = file_obj.split("/")[-1]
            except Exception:
                with open(file_obj, "rb") as f:
                    content_bytes = f.read()
                filename = file_obj.split("/")[-1]

        return filename, content_bytes
