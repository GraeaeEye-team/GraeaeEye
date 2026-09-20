"""
Вспомогательные функции общего назначения.
Содержит парсеры дат, утилиты форматирования денежных сумм и математические хелперы.
"""

from decimal import Decimal
from typing import Union


def format_currency(amount: Union[Decimal, float], currency: str = "MDL") -> str:
    """Форматирует число в стандартизированную строку суммы с разделением тысяч."""
    dec_val = Decimal(str(amount)) if not isinstance(amount, Decimal) else amount
    return f"{dec_val:,.2f} {currency}"
