"""
Пользовательские типы данных и перечисления (Enums).
Определяет варианты контрактов, уровни финансовых рисков и статусы счетов.
"""
from enum import Enum


class ContractType(str, Enum):
    SERVICE = "service"
    SUPPLY = "supply"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

