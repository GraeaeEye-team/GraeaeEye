"""
Демонстрационный скрипт для проверки работы UniversalDataParser.
Использование:
    python examples/demo.py
    python examples/demo.py "path/to/file.csv"
"""

import os
import sys
from pathlib import Path

# Fix Windows console UTF-8 output
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from smart_credit_parser import UniversalDataParser, ParseOptions

SCHEMA_PATH = Path(
    os.getenv(
        "SCHEMA_PATH",
        PROJECT_ROOT / "schema.sql" if (PROJECT_ROOT / "schema.sql").exists() else r"c:\Users\skv1d\Downloads\schema.sql"
    )
)


def run_demo():
    print("=" * 70)
    print("SMART CREDIT SYSTEM: ТЕСТИРОВАНИЕ УНИВЕРСАЛЬНОГО AI-ПАРСЕРА")
    print("=" * 70)
    print(f"Схема БД: {SCHEMA_PATH}")

    parser = UniversalDataParser(schema_path=SCHEMA_PATH)

    # 1. Если передан файл через аргументы
    if len(sys.argv) > 1:
        custom_file = Path(sys.argv[1])
        print(f"\n[+] Разбор пользовательского файла: {custom_file}")
        if not custom_file.exists():
            print(f"[-] Ошибка: файл '{custom_file}' не найден!")
            return

        result = parser.parse_file(custom_file, options=ParseOptions(dry_run=True))
        print("\n" + result.report.to_markdown())
        return

    # 2. Сценарий 1: Эталонный файл (Fast-Path)
    print("\n--- [Сценарий 1] Эталонный файл (Fast-Path, 0 вызовов ИИ) ---")
    tmp_canonical = PROJECT_ROOT / "demo_canonical.csv"
    tmp_canonical.write_text(
        "business_id,tax_id,legal_name,industry_code,registration_date,total_board_seats\n"
        "550e8400-e29b-41d4-a716-446655440001,1002600001111,Alfa Tech SRL,IT-01,2021-03-15,3\n"
        "550e8400-e29b-41d4-a716-446655440002,1002600002222,Beta Agro SRL,AGRI-02,2019-07-20,1\n",
        encoding="utf-8",
    )
    res1 = parser.parse_file(tmp_canonical, options=ParseOptions(dry_run=True))
    print(f"[OK] Статус: Успешно (Fast-Path = {res1.report.fast_path_used})")
    print(f"[OK] Принято строк: {res1.report.rows_accepted} из {res1.report.total_rows_read}")
    tmp_canonical.unlink(missing_ok=True)

    # 3. Сценарий 2: Произвольный файл на русском языке
    print("\n--- [Сценарий 2] Произвольный файл (Русский язык, европейские даты и суммы) ---")
    tmp_ru = PROJECT_ROOT / "demo_russian.csv"
    tmp_ru.write_text(
        "ИНН;Название компании;Отрасль;Дата регистрации;Количество директоров\n"
        "1002600003333;МолдТоргЭкспорт SRL;Торговля;15.08.2018;2\n"
        "1002600004444;Винодельня Кодру SA;Виноделие;25/11/2016;4\n",
        encoding="utf-8",
    )
    res2 = parser.parse_file(tmp_ru, options=ParseOptions(target_table="businesses", dry_run=True))
    print(f"[OK] Определена таблица: {res2.report.target_table}")
    print(f"[OK] Маппинг колонок:")
    for m in res2.mapping.column_mappings:
        print(f"     * '{m.source_column}' -> '{m.target_column}' (уверенность: {int(m.confidence * 100)}%)")
    tmp_ru.unlink(missing_ok=True)

    # 4. Сценарий 3: Защита и детерминированная валидация ограничений БД
    print("\n--- [Сценарий 3] Защита от нарушений ограничений схемы (CHECK и дубликаты) ---")
    tmp_invalid = PROJECT_ROOT / "demo_invalid.csv"
    tmp_invalid.write_text(
        "tax_id,legal_name,industry_code,registration_date,total_board_seats\n"
        "1002600005555,Корректная компания,IT,2020-01-01,2\n"
        "1002600005555,Дубликат ИНН,IT,2020-01-01,2\n"
        "1002600006666,Ошибка мест,IT,2020-01-01,0\n",
        encoding="utf-8",
    )
    res3 = parser.parse_file(tmp_invalid, options=ParseOptions(dry_run=True))
    print(f"[OK] Принято строк: {res3.report.rows_accepted}")
    print(f"[OK] Отклонено строк: {res3.report.rows_rejected}")
    for rej in res3.report.rejected_details:
        print(f"     [X] Строка #{rej.row_index}: {rej.errors}")
    tmp_invalid.unlink(missing_ok=True)

    print("\n" + "=" * 70)
    print("РЕЗУЛЬТАТ: ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ УСПЕШНО!")
    print("=" * 70)


if __name__ == "__main__":
    run_demo()
