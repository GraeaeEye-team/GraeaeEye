# Smart Credit System: Universal AI Data Parser Module

Модуль универсального парсинга и приведения входящих данных клиента произвольного формата к канонической реляционной схеме базы данных PostgreSQL 16 (`schema.sql`).

Включает в себя:
- Автономное ядро парсинга с динамической интроспекцией DDL без хардкода схемы.
- Адаптеры форматов: CSV/TSV, Excel (.xlsx, .xlsm), JSON/JSONL, XML, TXT, PDF.
- Fast-Path для эталонных файлов (0 вызовов LLM).
- Гибридный AI-маппинг (Google Gemini + интеллектуальный локальный эвристический матчер).
- Детерминированный нормализатор типов (даты, суммы с валютами, синонимы ENUM, булевы флаги).
- Строгий валидатор ограничений `schema.sql` (`NOT NULL`, `CHECK`, `UNIQUE`, `ENUM`, внешние ключи).
- Атомарный транзакционный писатель с защитой от дублирования (`ON CONFLICT DO NOTHING`).
- Единый публичный сервисный контракт `ParserModuleService` с ролевой моделью доступа (RBAC: `ANALYST`, `UNDERWRITER`, `ADMIN`).
- Интерактивный 4-шаговый веб-мастер (Upload $\rightarrow$ AI Mapping $\rightarrow$ Dry-Run $\rightarrow$ Commit) на базе FastAPI.

---

## 📋 Содержание

- [Установка и окружение](#-установка-и-окружение)
- [Переменные окружения (.env)](#-переменные-окружения-env)
- [Запуск тестов](#-запуск-тестов)
- [Запуск веб-интерфейса мастера](#-запуск-веб-интерфейса-мастера)
- [Программное использование (API сервиса)](#-программное-использование-api-сервиса)
- [Консольный пример (CLI)](#-консольный-пример-cli)
- [Ролевая модель доступа (RBAC)](#-ролевая-модель-доступа-rbac)
- [Как добавить новый формат данных](#-как-добавить-новый-формат-данных)
- [Что делать при изменении schema.sql](#-что-делать-при-изменении-schemasql)

---

## 🛠 Установка и окружение

Требуется Python 3.10 или новее.

```powershell
# 1. Клонирование репозитория
git clone <URL_РЕПОЗИТОРИЯ>
cd smart_credit_parser

# 2. Создание и активация виртуального окружения
python -m venv .venv
# Для Windows PowerShell:
.venv\Scripts\Activate.ps1
# Для Linux/macOS:
source .venv/bin/activate

# 3. Установка зависимостей
pip install --upgrade pip
pip install -r requirements.txt
# Или установка пакета в режиме разработки:
pip install -e .[dev]
```

---

## ⚙ Переменные окружения (.env)

Скопируйте шаблон `.env.example` в `.env` при необходимости кастомизации:

```powershell
Copy-Item .env.example .env
```

| Переменная | По умолчанию | Описание |
|---|---|---|
| `SCHEMA_PATH` | `schema.sql` | Путь к каноническому DDL-файлу PostgreSQL 16. |
| `GEMINI_API_KEY` | *(пусто)* | API-ключ Google Gemini. Если не задан, автоматически используется быстрый локальный мультиязычный эвристический матчер (работает офлайн, 0 расходов). |
| `GEMINI_MODEL` | `gemini-2.0-flash` | Модель Gemini для семантического вывода сложных маппингов. |
| `DATABASE_URL` | *(пусто)* | Строка подключения к PostgreSQL (например, `postgresql://user:pass@localhost:5432/smart_credit`). Если не задана, модуль работает в режиме in-memory проверки. |
| `HOST` | `127.0.0.1` | Хост для запуска веб-сервера. |
| `PORT` | `8000` | Порт веб-сервера мастера. |
| `TEMP_UPLOAD_DIR` | `smart_credit_uploads` | Каталог для временного сохранения входящих файлов. |

---

## 🧪 Запуск тестов

Набор включает **47 автоматизированных тестов**, покрывающих интроспекцию DDL, все адаптеры форматов, AI-маппер, защиту от Prompt Injection, проверку ограничений схемы, сервисную ролевую модель и REST API:

```powershell
pytest tests/ -v
```

---

## 🌐 Запуск веб-интерфейса мастера

Веб-мастер предоставляет пошаговый процесс загрузки данных клиентом:

```powershell
python run_server.py
```

После запуска перейдите в браузере по адресам:
- **Веб-интерфейс мастера (4 шага):** [http://127.0.0.1:8000](http://127.0.0.1:8000)
- **Интерактивная документация REST API (Swagger):** [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

### Шаги мастера:
1. **Шаг 1: Загрузка (Upload):** Drag-and-drop файлов любого формата, интроспекция структуры, проверка Fast-Path.
2. **Шаг 2: Семантическое сопоставление (Mapping):** Интерактивная таблица с цветовыми бейджами уверенности ИИ, дропдауны колонок схемы, защита от коллизий (нельзя назначить два разных поля файла на одно поле БД) и возможность игнорировать лишние колонки.
3. **Шаг 3: Предварительная проверка (Dry-Run):** Детерминированная проверка ограничений PostgreSQL 16 (CHECK, UNIQUE, NOT NULL, ENUM) без изменения БД, таблица предпросмотра нормализованных строк.
4. **Шаг 4: Фиксация (Commit):** Атомарная транзакция, доступная строго ролям `UNDERWRITER` и `ADMIN`. Скачивание отчетов аудита в `.md` и `.json`.

---

## 💻 Программное использование (API сервиса)

Хост-приложение взаимодействует с парсером через фасад [`ParserModuleService`](smart_credit_parser/app_interface.py):

```python
from pathlib import Path
from smart_credit_parser.app_interface import ParserModuleService

# Инициализация сервиса
service = ParserModuleService(schema_path="schema.sql")

# 1. Загрузка и первичный анализ файла
file_bytes = Path("client_invoices.xlsx").read_bytes()
inspection = service.upload_and_inspect(
    file_bytes=file_bytes,
    filename="client_invoices.xlsx",
    user_id="analyst_1",
    user_role="ANALYST",
)
print(f"Определена таблица: {inspection.suggested_table}")

# 2. Получение или ручная корректировка сопоставления
mapping = service.get_mapping(inspection.session_id)

# 3. Запуск предпросмотра (Dry-Run)
dry_run = service.run_dry_run(inspection.session_id)
print(f"Принято: {dry_run.rows_accepted}, Отклонено: {dry_run.rows_rejected}")

# 4. Фиксация в БД (требует роль UNDERWRITER или ADMIN)
commit_res = service.confirm_and_write(
    session_id=inspection.session_id,
    user_id="underwriter_1",
    user_role="UNDERWRITER",
)
print(f"Записано {commit_res.inserted_count} строк в {commit_res.target_table}")
```

---

## 🖥 Консольный пример (CLI)

Для быстрой проверки разбора файлов в командной строке:

```powershell
# Запуск демонстрации всех ключевых сценариев:
python examples/demo.py

# Разбор произвольного файла клиента:
python examples/demo.py "samples/client_test_invoices.xlsx"
```

---

## 🔒 Ролевая модель доступа (RBAC)

Роли соответствуют `schema.sql`:

| Роль | Шаг 1 (Upload) | Шаг 2 (Mapping) | Шаг 3 (Dry-Run) | Шаг 4 (Commit to DB) |
|---|:---:|:---:|:---:|:---:|
| **ANALYST** | ✅ Разрешено | ✅ Разрешено | ✅ Разрешено | ❌ Заблокировано |
| **UNDERWRITER** | ✅ Разрешено | ✅ Разрешено | ✅ Разрешено | ✅ Разрешено |
| **ADMIN** | ✅ Разрешено | ✅ Разрешено | ✅ Разрешено | ✅ Разрешено |

Попытка вызова `confirm_and_write()` пользователем с ролью `ANALYST` немедленно завершается исключением `PermissionError` и блокируется на уровне веб-интерфейса.

---

## 🔌 Как добавить новый формат данных

Все адаптеры наследуются от базового класса `BaseExtractor`:

1. Создайте файл `smart_credit_parser/extractors/my_format_extractor.py`:
   ```python
   from pathlib import Path
   from typing import Any, Dict, Iterator, List, Tuple
   from .base import BaseExtractor

   class MyFormatExtractor(BaseExtractor):
       def can_handle(self, file_path: Path) -> bool:
           return file_path.suffix.lower() in (".myext",)

       def get_sample(self, file_path: Path, max_rows: int = 10) -> Tuple[List[str], List[Dict[str, Any]]]:
           # Извлечение заголовков и первых max_rows строк
           ...

       def extract_chunks(self, file_path: Path, chunk_size: int = 1000) -> Iterator[List[Dict[str, Any]]]:
           # Потоковая генерация пакетов строк для масштабируемости
           ...
   ```
2. Зарегистрируйте экстрактор в [`smart_credit_parser/extractors/registry.py`](smart_credit_parser/extractors/registry.py):
   ```python
   from .my_format_extractor import MyFormatExtractor
   EXTRACTORS.append(MyFormatExtractor())
   ```
Новый формат станет автоматически доступен во всех компонентах системы и веб-мастере.

---

## 🔄 Что делать при изменении `schema.sql`

Благодаря динамической интроспекции DDL (`SQLSchemaParser`):
1. **Никакой код парсера переписывать не нужно.**
2. Достаточно обновить файл `schema.sql` в корне проекта (или указать новый путь через переменную `SCHEMA_PATH`).
3. При следующем запуске парсер автоматически:
   - Перестроит граф всех 13 таблиц;
   - Обновит типы колонок, допустимые списки ENUM-значений и числовые CHECK-диапазоны;
   - Перестроит граф внешних ключей и топологический порядок зависимостей таблиц.
