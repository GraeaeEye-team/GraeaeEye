"""
Pydantic-схемы валидации распарсенных данных.
Гарантируют корректность типов данных после маппинга AI-парсёра перед сохранением в PostgreSQL.
"""
from datetime import date
from typing import Optional
from pydantic import BaseModel, Field


class NormalizedTransactionSchema(BaseModel):
    transaction_date: date
    amount: float
    counterparty_inn: Optional[str] = None
    description: str = Field(default="")

