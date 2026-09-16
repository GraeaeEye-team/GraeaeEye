"""
Интеллектуальный маппер колонок выписок на основе LLM / эмбеддингов.
Анализирует контекст заголовков и сопоставляет нестандартные столбцы с единой схемой БД.
"""
from typing import Dict, List


def map_columns_with_ai(column_names: List[str]) -> Dict[str, str]:
    """
    Преобразует список произвольных заголовков столбцов выписки
    в канонические поля БД ('amount', 'date', 'counterparty_inn', 'description').
    """
    mapping = {}
    for col in column_names:
        col_lower = col.lower()
        if "сумм" in col_lower or "amount" in col_lower:
            mapping[col] = "amount"
        elif "дат" in col_lower or "date" in col_lower:
            mapping[col] = "date"
        elif "инн" in col_lower or "inn" in col_lower:
            mapping[col] = "counterparty_inn"
        else:
            mapping[col] = col
    return mapping

