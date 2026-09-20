"""
Базовый модуль контрактов и утилит для аналитического ядра скоринга.

Предоставляет:
- SubmoduleResult: Датакласс стандартизированного результата расчета подмодуля.
- BaseSubmoduleEvaluator: Абстрактный базовый класс для реализации аналитических подмодулей.
- clamp, safe_div: Чистые математические функции-хелперы для финансовых расчетов.
- logger: Централизованный логгер аналитического ядра smart_credit.ml.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal
import logging
from typing import Any

try:
    from src.fintech_app.shared.schemas.user_types import EvaluationStatus
except ModuleNotFoundError:
    from fintech_app.shared.schemas.user_types import EvaluationStatus

logger: logging.Logger = logging.getLogger("smart_credit.ml")


@dataclass
class SubmoduleResult:
    """
    Стандартизированный контейнер результатов вычислений аналитического подмодуля.

    Атрибуты:
        submodule_code: Уникальный строковый код подмодуля (например, 'OS', 'ICR', 'RQ').
        status: Статус выполнения расчета (EvaluationStatus.SUCCESS, DATA_ABSENT, ERROR).
        impact_weight: Весовой коэффициент подмодуля в совокупной оценке риска (0.0 - 1.0).
        verdict: Краткий текстовый вердикт подмодуля.
        indices: Словарь рассчитанных нормализованных индексов (значения от 0.0 до 100.0 или None).
        summary: Человекочитаемое резюме результатов оценки.
        diagnostic_report: Подробный диагностический текстовый отчет для кредитного досье.
    """

    submodule_code: str
    status: EvaluationStatus
    impact_weight: float
    verdict: str
    indices: dict[str, float | None]
    summary: str
    diagnostic_report: str


class BaseSubmoduleEvaluator(ABC):
    """
    Абстрактный базовый класс для аналитических подмодулей скоринга.

    Определяет единый интерфейс исполнения и атрибуты веса и идентификатора подмодуля.
    """

    submodule_code: str = ""
    impact_weight: float = 0.0
    logger: logging.Logger = logger

    def __init__(self, submodule_code: str = "", impact_weight: float = 0.0) -> None:
        if submodule_code:
            self.submodule_code = submodule_code
        if impact_weight:
            self.impact_weight = impact_weight

    @property
    def code(self) -> str:
        """Алиас кода подмодуля для обратной совместимости."""
        return self.submodule_code

    @code.setter
    def code(self, value: str) -> None:
        self.submodule_code = value

    @abstractmethod
    def evaluate(self, snapshot: Any) -> SubmoduleResult:
        """
        Выполняет расчет метрик и оценку финансового снапшота компании.

        :param snapshot: Снапшот данных компании (CompanyDataSnapshot или аналогичный объект).
        :return: Структурированный результат анализа SubmoduleResult.
        """
        pass


def clamp(val: float, low: float = 0.0, high: float = 100.0) -> float:
    """
    Ограничивает числовое значение val заданным диапазоном [low, high].

    :param val: Исходное значение.
    :param low: Нижняя граница диапазона (по умолчанию 0.0).
    :param high: Верхняя граница диапазона (по умолчанию 100.0).
    :return: Значение типа float в границах [low, high].
    :raises ValueError: Если low > high.
    """
    if low > high:
        raise ValueError(f"Нижняя граница low ({low}) не может быть больше " f"верхней границы high ({high})")
    if val < low:
        return float(low)
    if val > high:
        return float(high)
    return float(val)


def safe_div(
    numerator: float | Decimal,
    denominator: float | Decimal,
    default_denom: float = 1.0,
) -> float:
    """
    Безопасное деление с защитой от ZeroDivisionError и гарантированным приведением к float.

    Если знаменатель равен нулю, для деления используется default_denom.
    Если при делении возникает ZeroDivisionError, возвращается 0.0.

    :param numerator: Числитель (float или Decimal).
    :param denominator: Знаменатель (float или Decimal).
    :param default_denom: Знаменатель по умолчанию, если denominator равен 0 (по умолчанию 1.0).
    :return: Результат деления в виде float.
    """
    try:
        num = float(numerator) if numerator is not None else 0.0
        denom = float(denominator) if denominator is not None else 0.0
        if denom == 0.0:
            denom = float(default_denom)
        return float(num / denom)
    except ZeroDivisionError:
        return 0.0


__all__ = [
    "BaseSubmoduleEvaluator",
    "EvaluationStatus",
    "SubmoduleResult",
    "clamp",
    "logger",
    "safe_div",
]
