"""
Комплексный статический чекер готовности проекта GraeaeEye к запуску.
Проверяет компиляцию, корректность DDL, импортопригодность роутов и целостность контрактов.
"""

from __future__ import annotations

import ast
from pathlib import Path
import py_compile
import re
import sys

ROOT_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = ROOT_DIR / "src"

# Добавляем /src в sys.path для валидации импортов в стиле контейнера
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

ERRORS: list[str] = []
WARNINGS: list[str] = []


def log_error(msg: str) -> None:
    ERRORS.append(msg)
    print(f"❌ [ERROR] {msg}")


def log_warn(msg: str) -> None:
    WARNINGS.append(msg)
    print(f"⚠️  [WARN] {msg}")


def log_ok(msg: str) -> None:
    print(f"✅ [OK] {msg}")


def check_python_compilation() -> None:
    """1. Проверка синтаксиса и байткод-компиляции всех .py файлов."""
    print("\n--- 1. Проверка синтаксиса Python (py_compile) ---")
    py_files = list(SRC_DIR.rglob("*.py"))
    failed = 0
    for p in py_files:
        try:
            py_compile.compile(str(p), doraise=True)
        except py_compile.PyCompileError as exc:
            log_error(f"Синтаксическая ошибка в {p.relative_to(ROOT_DIR)}: {exc}")
            failed += 1
    if failed == 0:
        log_ok(f"Все {len(py_files)} Python-файлов успешно скомпилированы.")


def check_import_contracts() -> None:
    """2. Проверка ключевых модулей на циклические импорты и доступность зависимостей."""
    print("\n--- 2. Проверка импортопригодности ключевых узлов ---")
    modules_to_test = [
        "fintech_app.core.config",
        "fintech_app.shared.schemas.user_types",
        "fintech_app.db.models",
        "fintech_app.db.connection",
        "fintech_app.db.backup_daemon",
        "fintech_app.ingestion.schemas",
        "fintech_app.ingestion.ai_mapper",
        "fintech_app.ingestion.parser",
        "fintech_app.ingestion.external_intel",
        "fintech_app.ingestion.pipeline",
        "fintech_app.ml.scoring",
        "fintech_app.ml.loader",
        "fintech_app.ml.pipeline",
        "fintech_app.api.schemas",
        "fintech_app.api.dependencies",
        "fintech_app.api.mock_provider",
        "fintech_app.api.endpoints.auth",
        "fintech_app.api.endpoints.analysis",
        "fintech_app.api.router",
        "fintech_app.main",
    ]

    for mod_name in modules_to_test:
        try:
            __import__(mod_name)
            log_ok(f"Импорт модуля {mod_name}")
        except Exception as exc:
            log_error(f"Не удалось импортировать {mod_name}: {exc}")


def check_configuration_and_dependencies() -> None:
    """3. Проверка согласованности конфигураций, портов, переменных окружения и зависимостей."""
    print("\n--- 3. Проверка конфигураций, портов и зависимостей ---")

    # 1.1. Выравнивание портов
    main_py = SRC_DIR / "fintech_app" / "__main__.py"
    if main_py.exists():
        content = main_py.read_text(encoding="utf-8")
        if "port=3000" in content:
            log_error("src/fintech_app/__main__.py настроен на порт 3000! Замени на 8000.")
        elif "port=8000" in content:
            log_ok("__main__.py корректно указывает на порт 8000.")
        else:
            log_warn("__main__.py не содержит явного указания port=8000.")

    dockerfile = ROOT_DIR / "Dockerfile"
    if dockerfile.exists():
        content = dockerfile.read_text(encoding="utf-8")
        if "EXPOSE 8000" in content and ("--port 8000" in content or '"8000"' in content):
            log_ok("Dockerfile: EXPOSE 8000 и CMD слушают порт 8000.")
        else:
            log_error("Dockerfile содержит некорректный порт для Uvicorn или отсутствует EXPOSE 8000.")

        # 1.2. PYTHONPATH и запуск без src.
        if "ENV PYTHONPATH=/app/src" in content or "PYTHONPATH=/app/src" in content:
            log_ok("Dockerfile: задана директива ENV PYTHONPATH=/app/src.")
        else:
            log_error("Dockerfile: отсутствует директива ENV PYTHONPATH=/app/src.")

        if "uvicorn fintech_app.main:app" in content or '"fintech_app.main:app"' in content:
            log_ok("Dockerfile: запуск Uvicorn использует путь без префикса src.")
        else:
            log_error("Dockerfile: запуск Uvicorn должен использовать модуль fintech_app.main:app.")

    # docker-compose.yml
    compose_file = ROOT_DIR / "docker-compose.yml"
    if compose_file.exists():
        c_text = compose_file.read_text(encoding="utf-8")
        if '"8000:8000"' in c_text or "'8000:8000'" in c_text or "8000:8000" in c_text:
            log_ok("docker-compose.yml: порт backend проброшен как 8000:8000.")
        else:
            log_error("docker-compose.yml: отсутствует строгий проброс портов 8000:8000 для backend.")

        if "PYTHONPATH=/app/src" in c_text or "PYTHONPATH: /app/src" in c_text:
            log_ok("docker-compose.yml: PYTHONPATH=/app/src передан в сервисы backend и db-backup.")
        else:
            log_error("docker-compose.yml: не найдена переменная PYTHONPATH=/app/src.")

        if "- db" in c_text and "aliases:" in c_text:
            log_ok("docker-compose.yml: служба postgres объявлена с сетевым псевдонимом db.")
        else:
            log_error("docker-compose.yml: отсутствует сетевой псевдоним db у сервиса postgres.")

    # .env.example
    env_example = ROOT_DIR / ".env.example"
    if env_example.exists():
        e_text = env_example.read_text(encoding="utf-8")
        required_env_vars = [
            "POSTGRES_SERVER",
            "POSTGRES_PORT",
            "POSTGRES_USER",
            "POSTGRES_PASSWORD",
            "POSTGRES_DB",
            "BACKUP_INTERVAL_SECONDS",
        ]
        missing_vars = [v for v in required_env_vars if v not in e_text]
        if missing_vars:
            log_error(f".env.example не содержит обязательные переменные: {missing_vars}")
        else:
            log_ok(".env.example содержит все обязательные параметры БД и резервного копирования.")

    # requirements.txt
    req_file = ROOT_DIR / "requirements.txt"
    if req_file.exists():
        r_text = req_file.read_text(encoding="utf-8")
        required_pkgs = [
            "psycopg",
            "psycopg-pool",
            "openpyxl",
            "aiofiles",
            "pydantic-settings",
            "python-multipart",
        ]
        missing_pkgs = [p for p in required_pkgs if p not in r_text]
        if missing_pkgs:
            log_error(f"requirements.txt не содержит пакеты: {missing_pkgs}")
        else:
            log_ok(
                "requirements.txt содержит все обязательные системные библиотеки (psycopg, openpyxl, aiofiles, pydantic-settings, python-multipart)."
            )


def check_database_schema_ddl() -> None:
    """4. Проверка SQL-схемы на наличие 13 канонических таблиц."""
    print("\n--- 4. Проверка схемы БД (schema.sql) ---")
    schema_file = SRC_DIR / "fintech_app" / "db" / "schema.sql"
    if not schema_file.exists():
        log_error("Файл src/fintech_app/db/schema.sql не найден!")
        return

    sql = schema_file.read_text(encoding="utf-8").lower()
    expected_tables = [
        "businesses",
        "shareholders",
        "web_reputation",
        "macro_sector_metrics",
        "counterparties",
        "bank_accounts",
        "credit_obligations",
        "invoices",
        "transactions",
        "users",
        "user_settings",
        "analysis_runs",
        "analysis_logs",
    ]

    missing = []
    for tbl in expected_tables:
        pattern = rf"create\s+table\s+(if\s+not\s+exists\s+)?{tbl}\b"
        if not re.search(pattern, sql):
            missing.append(tbl)

    if missing:
        log_error(f"В schema.sql отсутствуют канонические таблицы: {missing}")
    else:
        log_ok("В schema.sql найдены все 13 канонических таблиц.")


def check_fastapi_routes() -> None:
    """5. Проверка регистрации эндпоинтов в FastAPI приложении."""
    print("\n--- 5. Проверка регистрации эндпоинтов FastAPI ---")
    try:
        from fintech_app.main import app

        routes = [r.path for r in app.routes]

        required = [
            "/health",
            "/api/v1/health",
            "/api/v1/auth/token",
            "/api/v1/analysis/start",
            "/api/v1/analysis/stream/{run_id}",
            "/api/v1/analysis/report/{run_id}",
        ]
        for route in required:
            if any(route == r or r.endswith(route) for r in routes):
                log_ok(f"Маршрут зарегистрирован: {route}")
            else:
                log_error(f"Критический маршрут отсутствует в FastAPI app: {route}")
    except Exception as exc:
        log_error(f"Не удалось инициализировать FastAPI app для проверки роутов: {exc}")


def main() -> None:
    print("🚀 Запуск статической проверки готовности к старту...")
    check_python_compilation()
    check_configuration_and_dependencies()
    check_database_schema_ddl()
    check_import_contracts()
    check_fastapi_routes()

    print("\n================== ИТОГ АУДИТА ==================")
    if ERRORS:
        print(f"❌ Найдено {len(ERRORS)} критических ошибок, блокирующих запуск:")
        for e in ERRORS:
            print(f"   • {e}")
        sys.exit(1)
    else:
        print("🎉 Все статические проверки пройдены! Проект готов к запуску в Docker.")
        if WARNINGS:
            print(f"Предупреждения ({len(WARNINGS)}):")
            for w in WARNINGS:
                print(f"   • {w}")
        sys.exit(0)


if __name__ == "__main__":
    main()
