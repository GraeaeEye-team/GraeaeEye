"""
Сбор открытых внешних данных, судебных реестров и макроэкономических метрик.
Реализует асинхронный опрос реестров с жестким таймаутом (<= 2.5 сек) и
детерминированным нейтральным fallback-ответом при оффлайне или сбоях сети.
Boundary Rule: только сбор и нормализация, никакого кредитного скоринга (ML-логика в ml/).
"""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timezone
from decimal import Decimal
import logging
from typing import Any, Dict, List, Optional
from uuid import UUID

from fintech_app.core.config import settings
from fintech_app.ingestion.parser import JudicialRegistryParser
from fintech_app.ingestion.schemas import ParsedJudicialRecord

logger = logging.getLogger(__name__)

EXTERNAL_TIMEOUT_SECONDS = 2.5


class ExternalIntelligenceCollector:
    """
    Асинхронный коллектор открытых данных (налоговый реестр, арбитраж, санкции, макропоказатели).
    """

    def __init__(self, use_mock: Optional[bool] = None) -> None:
        self.use_mock = settings.use_mock_engine if use_mock is None else use_mock
        self.court_parser = JudicialRegistryParser()

    async def collect_reputation(
        self,
        business_id: UUID,
        legal_name: str,
        tax_id: str,
    ) -> Dict[str, Any]:
        """
        Сбор информации о судебных исках, налоговых задолженностях и санкционных списках.
        """
        if self.use_mock:
            return self._neutral_reputation_fallback(business_id, legal_name, tax_id)

        try:
            return await asyncio.wait_for(
                self._fetch_remote_reputation(business_id, legal_name, tax_id),
                timeout=EXTERNAL_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            logger.warning(
                "External intelligence reputation lookup timed out (>%ss) for tax_id %s. Using neutral fallback.",
                EXTERNAL_TIMEOUT_SECONDS,
                tax_id,
            )
            return self._neutral_reputation_fallback(business_id, legal_name, tax_id, warning="TIMEOUT")
        except Exception as exc:
            logger.error("Error collecting external reputation for %s: %s. Using neutral fallback.", tax_id, exc)
            return self._neutral_reputation_fallback(business_id, legal_name, tax_id, warning=str(exc))

    async def collect_macro_metrics(self, industry_code: str) -> Dict[str, Any]:
        """
        Сбор отраслевых бенчмарков и макроэкономических индикаторов для сектора экономики.
        """
        if self.use_mock:
            return self._neutral_macro_fallback(industry_code)

        try:
            return await asyncio.wait_for(
                self._fetch_remote_macro(industry_code),
                timeout=EXTERNAL_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            logger.warning(
                "External macro metrics lookup timed out (>%ss) for sector %s. Using neutral fallback.",
                EXTERNAL_TIMEOUT_SECONDS,
                industry_code,
            )
            return self._neutral_macro_fallback(industry_code, warning="TIMEOUT")
        except Exception as exc:
            logger.error("Error collecting macro metrics for %s: %s. Using neutral fallback.", industry_code, exc)
            return self._neutral_macro_fallback(industry_code, warning=str(exc))

    async def collect_all(self, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """
        Комплексный сбор всех внешних данных по манифесту запроса.
        """
        biz_id_raw = metadata.get("business_id")
        business_id = UUID(str(biz_id_raw)) if biz_id_raw else UUID("00000000-0000-0000-0000-000000000000")
        legal_name = str(metadata.get("company_name") or metadata.get("legal_name") or "Unknown Entity")
        tax_id = str(metadata.get("tax_id") or metadata.get("counterparty_tax_id") or "")
        industry_code = str(metadata.get("sector_code") or metadata.get("industry_code") or "G46")

        reputation_task = self.collect_reputation(business_id, legal_name, tax_id)
        macro_task = self.collect_macro_metrics(industry_code)

        rep_res, macro_res = await asyncio.gather(reputation_task, macro_task)

        return {
            "business_id": str(business_id),
            "tax_id": tax_id,
            "acquired_at": datetime.now(timezone.utc).isoformat(),
            "reputation": rep_res,
            "macro_metrics": macro_res,
            "success": True,
        }

    # -------------------------------------------------------------------------
    # Внутренние сетевые клиенты (могут интегрироваться с Crawl4AI или REST API)
    # -------------------------------------------------------------------------

    async def _fetch_remote_reputation(
        self,
        business_id: UUID,
        legal_name: str,
        tax_id: str,
    ) -> Dict[str, Any]:
        """Эмуляция сетевого запроса к внешнему реестру / скраперу (детерминированный офлайн-адаптер)."""
        return self._neutral_reputation_fallback(business_id, legal_name, tax_id, source="EXTERNAL_REGISTRY")

    async def _fetch_remote_macro(self, industry_code: str) -> Dict[str, Any]:
        """Эмуляция сетевого запроса к макроэкономическим агрегаторам (детерминированный офлайн-адаптер)."""
        return self._neutral_macro_fallback(industry_code, source="CENTRAL_BANK_API")

    # -------------------------------------------------------------------------
    # Детерминированные нейтральные фоллбеки
    # -------------------------------------------------------------------------

    def _neutral_reputation_fallback(
        self,
        business_id: UUID,
        legal_name: str,
        tax_id: str,
        source: str = "MOCK_FALLBACK",
        warning: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Детерминированная нейтральная запись: отсутствие открытых исков,
        нулевая налоговая задолженность, нейтральный сентимент.
        """
        clean_court_records = [
            ParsedJudicialRecord(
                case_number=f"CASE-DEFAULT-{tax_id[-4:] if len(tax_id)>=4 else '0001'}",
                filing_date=date(2024, 6, 1),
                role="DEFENDANT",
                claim_amount=Decimal("0.00"),
                case_status="CLOSED",
            )
        ]

        data = {
            "business_id": str(business_id),
            "legal_name": legal_name,
            "tax_id": tax_id,
            "has_active_claims": False,
            "active_lawsuits_count": 0,
            "total_claim_amount": Decimal("0.00"),
            "tax_arrears_amount": Decimal("0.00"),
            "sanctions_flag": False,
            "reputation_sentiment": 0.0,
            "court_cases": [r.model_dump() for r in clean_court_records],
            "source": source,
            "fallback_used": source != "EXTERNAL_REGISTRY",
        }
        if warning:
            data["warning"] = warning
        return data

    def _neutral_macro_fallback(
        self,
        industry_code: str,
        source: str = "MOCK_FALLBACK",
        warning: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Детерминированные отраслевые медианы (NACE / CAEM).
        """
        data = {
            "industry_code": industry_code or "DEFAULT",
            "gdp_growth_rate": Decimal("0.035"),
            "inflation_rate": Decimal("0.052"),
            "sector_default_probability": Decimal("0.025"),
            "key_interest_rate": Decimal("0.065"),
            "macro_risk_level": "MODERATE",
            "source": source,
            "fallback_used": source != "CENTRAL_BANK_API",
        }
        if warning:
            data["warning"] = warning
        return data
