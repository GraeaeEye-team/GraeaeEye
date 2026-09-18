"""
Управление подключениями и соединениями с PostgreSQL.
Содержит класс Database для выполнения SQL-запросов и структуру ответа Response.
"""
from dataclasses import dataclass
from typing import Any, Optional


class Database:
    """Управление соединением и курсором подключения к PostgreSQL."""

    def __init__(self, connection):
        self.connection = connection
        self.cursor = self.connection.cursor()

    def close(self) -> None:
        if self.cursor:
            self.cursor.close()
        if self.connection:
            self.connection.close()

