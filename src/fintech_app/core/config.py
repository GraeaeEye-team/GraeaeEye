"""
Конфигурация параметров приложения.
Загружает переменные окружения из .env (параметры подключения к PostgreSQL, API-ключи).
"""

import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


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
    ollama_host: str = os.getenv("OLLAMA_HOST", "")
    llm_provider: str = os.getenv("LLM_PROVIDER", "auto")
    llm_inference_timeout: float = float(os.getenv("LLM_INFERENCE_TIMEOUT", "300.0"))
    llm_heartbeat_interval: float = float(os.getenv("LLM_HEARTBEAT_INTERVAL", "10.0"))

    # Database Backup & Auto-Restore Settings
    backup_dir: str = os.getenv("BACKUP_DIR", "src/fintech_app/db/backups")
    auto_restore_last_db_backup: bool = os.getenv(
        "AUTO_RESTORE_LAST_DB_BACKUP", "false"
    ).lower() in ("true", "1", "yes")
    force_restore_db_backup: bool = os.getenv(
        "FORCE_RESTORE", "false"
    ).lower() in ("true", "1", "yes")

    def __post_init__(self) -> None:
        """Dynamically refresh attributes from environment upon instantiation."""
        self.app_env = os.getenv("APP_ENV", self.app_env)
        self.log_level = os.getenv("LOG_LEVEL", self.log_level)
        self.use_mock_engine = os.getenv("USE_MOCK_ENGINE", str(self.use_mock_engine)).lower() in (
            "true",
            "1",
            "yes",
        )
        self.postgres_server = os.getenv("POSTGRES_SERVER", self.postgres_server)
        self.postgres_port = int(os.getenv("POSTGRES_PORT", str(self.postgres_port)))
        self.postgres_user = os.getenv("POSTGRES_USER", self.postgres_user)
        self.postgres_password = os.getenv("POSTGRES_PASSWORD", self.postgres_password)
        self.postgres_db = os.getenv("POSTGRES_DB", self.postgres_db)
        self.openai_api_key = os.getenv("OPENAI_API_KEY", self.openai_api_key)
        self.llm_model = os.getenv("LLM_MODEL", self.llm_model)
        self.ollama_host = os.getenv("OLLAMA_HOST", self.ollama_host)
        self.llm_provider = os.getenv("LLM_PROVIDER", self.llm_provider)
        self.llm_inference_timeout = float(os.getenv("LLM_INFERENCE_TIMEOUT", str(self.llm_inference_timeout)))
        self.llm_heartbeat_interval = float(os.getenv("LLM_HEARTBEAT_INTERVAL", str(self.llm_heartbeat_interval)))
        self.backup_dir = os.getenv("BACKUP_DIR", self.backup_dir)
        self.auto_restore_last_db_backup = os.getenv(
            "AUTO_RESTORE_LAST_DB_BACKUP", str(self.auto_restore_last_db_backup)
        ).lower() in ("true", "1", "yes")
        self.force_restore_db_backup = os.getenv(
            "FORCE_RESTORE", str(self.force_restore_db_backup)
        ).lower() in ("true", "1", "yes")

    @property
    def database_url(self) -> str:
        user = self.postgres_user
        pwd = self.postgres_password
        host = self.postgres_server
        port = self.postgres_port
        db = self.postgres_db
        return f"postgresql://{user}:{pwd}@{host}:{port}/{db}"


settings = Settings()
