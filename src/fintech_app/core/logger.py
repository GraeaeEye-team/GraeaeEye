"""
Централизованная настройка логирования (logging).
Форматирует вывод логов приложения в консоль и файлы журнала.
"""

import logging
import sys

logger = logging.getLogger("graeae_eye")
logger.setLevel(logging.INFO)

if not logger.handlers:
    formatter = logging.Formatter("[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s")
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    logger.addHandler(handler)
