"""
Конфигурация параметров приложения.
Загружает переменные окружения из .env (параметры подключения к PostgreSQL, API-ключи).
"""

import os
from dataclasses import dataclass


@dataclass
class Settings:
    app_env: str = os.getenv("APP_ENV", "development")
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    use_mock_engine: bool = os.getenv("USE_MOCK_ENGINE", "false").lower() in ("true", "1", "yes")

    postgres_server: str = os.getenv("POSTGRES_SERVER", "localhost")
    postgres_port: int = int(os.getenv("POSTGRES_PORT", "5432"))
    postgres_user: str = os.getenv("POSTGRES_USER", "postgres")
    postgres_password: str = os.getenv("POSTGRES_PASSWORD", "postgres")
    postgres_db: str = os.getenv("POSTGRES_DB", "graeae_eye_db")

    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    llm_model: str = os.getenv("LLM_MODEL", "gpt-4o-mini")
    ollama_host: str = os.getenv("OLLAMA_HOST", "http://localhost:11434")
    llm_provider: str = os.getenv("LLM_PROVIDER", "auto")
    llm_inference_timeout: float = float(os.getenv("LLM_INFERENCE_TIMEOUT", "300.0"))
    llm_heartbeat_interval: float = float(os.getenv("LLM_HEARTBEAT_INTERVAL", "10.0"))

    @property
    def database_url(self) -> str:
        user = self.postgres_user
        pwd = self.postgres_password
        host = self.postgres_server
        port = self.postgres_port
        db = self.postgres_db
        return f"postgresql://{user}:{pwd}@{host}:{port}/{db}"


settings = Settings()
