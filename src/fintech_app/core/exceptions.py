"""
Базовые исключения приложения.
Определяет кастомные ошибки для парсера данных, работы с БД и вычислений ML-моделей.
"""


class GraeaeEyeException(Exception):
    """Базовое исключение для всех модулей системы."""
    pass


class ParsingError(GraeaeEyeException):
    """Ошибка при парсинге файлов выписок или AI-маппинге колонок."""
    pass


class DatabaseError(GraeaeEyeException):
    """Ошибка при выполнении запросов или транзакций в PostgreSQL."""
    pass


class MLEngineError(GraeaeEyeException):
    """Ошибка при расчете прогноза Cash Flow или скоринга контрагентов."""
    pass

