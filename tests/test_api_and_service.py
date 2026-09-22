"""
Integration and RBAC tests for ParserModuleService (app_interface.py).
"""

import sqlite3
import pytest

from smart_credit_parser.app_interface import ParserModuleService

from tests.conftest import SCHEMA_PATH


@pytest.fixture
def sqlite_db():
    conn = sqlite3.connect(":memory:")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE businesses (
            business_id TEXT PRIMARY KEY,
            tax_id TEXT NOT NULL UNIQUE,
            legal_name TEXT NOT NULL,
            industry_code TEXT NOT NULL,
            registration_date TEXT NOT NULL,
            total_board_seats INTEGER NOT NULL DEFAULT 1,
            independent_directors_count INTEGER NOT NULL DEFAULT 0
        );
    """)
    conn.commit()
    yield conn
    conn.close()


@pytest.fixture
def service(sqlite_db, tmp_path):
    return ParserModuleService(
        schema_path=SCHEMA_PATH,
        db_connection=sqlite_db,
        temp_storage_dir=tmp_path / "uploads",
    )


def test_full_wizard_workflow_with_rbac(service):
    # --- Шаг 1: Upload (Analyst) ---
    csv_bytes = (
        "ИНН;Название компании;Отрасль;Дата регистрации;Мест в совете\n"
        "1002600007777;МолдАгроТех SRL;Агро;15.05.2019;3\n"
    ).encode("utf-8")

    inspection = service.upload_and_inspect(
        file_bytes=csv_bytes,
        filename="companies_ru.csv",
        user_id="analyst_1",
        user_role="ANALYST",
    )
    assert inspection.session_id is not None
    assert "ИНН" in inspection.headers
    assert inspection.suggested_table == "businesses"

    # --- Шаг 2: Get Mapping & Custom Update ---
    mapping_res = service.get_mapping(inspection.session_id, target_table_hint="businesses")
    assert mapping_res.target_table == "businesses"

    # Analyst confirms or overrides mapping
    updated_mapping = service.update_mapping(
        session_id=inspection.session_id,
        target_table="businesses",
        custom_mappings={
            "ИНН": "tax_id",
            "Название компании": "legal_name",
            "Отрасль": "industry_code",
            "Дата регистрации": "registration_date",
            "Мест в совете": "total_board_seats",
        },
        save_to_cache=True,
    )
    assert updated_mapping.target_table == "businesses"

    # --- Шаг 3: Dry-Run Verification ---
    dry_run_res = service.run_dry_run(inspection.session_id)
    assert dry_run_res.rows_accepted == 1
    assert dry_run_res.rows_rejected == 0
    assert dry_run_res.is_ready_for_commit is True

    # --- Шаг 4: RBAC Enforcement on Commit ---
    # Attempt to write by ANALYST must FAIL with PermissionError
    with pytest.raises(PermissionError, match="not authorized to confirm and write"):
        service.confirm_and_write(
            session_id=inspection.session_id,
            user_id="analyst_1",
            user_role="ANALYST",
        )

    # Commit by UNDERWRITER must SUCCEED
    commit_res = service.confirm_and_write(
        session_id=inspection.session_id,
        user_id="underwriter_1",
        user_role="UNDERWRITER",
    )
    assert commit_res.status == "COMMITTED"
    assert commit_res.inserted_count == 1
    assert commit_res.committed_by_role == "UNDERWRITER"

    # Verify history
    history = service.get_history()
    assert len(history) == 1
    assert history[0].status == "COMMITTED"
    assert history[0].committed_by == "underwriter_1"

    # Verify downloadable report
    report_md = service.download_report(inspection.session_id)
    assert "Отчет разбора данных" in report_md
    assert "businesses" in report_md


def test_invoices_table_auto_detection_and_dry_run(service):
    csv_bytes = (
        "Тип документа;Сумма счета;Дата выставления;Срок оплаты;Статус оплаты\n"
        "продажа;15000 MDL;10.01.2025;10.02.2025;оплачен\n"
        "продажа;-50 MDL;10.01.2025;10.02.2025;оплачен\n"
    ).encode("utf-8")

    inspection = service.upload_and_inspect(
        file_bytes=csv_bytes,
        filename="invoices.csv",
        user_role="UNDERWRITER",
    )
    # Check that invoices was detected automatically, NOT default businesses
    assert inspection.suggested_table == "invoices"

    mapping = service.get_mapping(inspection.session_id)
    assert mapping.target_table == "invoices"

    dry_run = service.run_dry_run(inspection.session_id)
    # 1 valid row (15000), 1 rejected (-50 violates CHECK >= 0)
    assert dry_run.rows_accepted == 1
    assert dry_run.rows_rejected == 1
    assert dry_run.is_ready_for_commit is True


def test_duplicate_target_column_collision_rejected(service):
    csv_bytes = (
        "Сумма счета;Комментарий\n"
        "100;Текст\n"
    ).encode("utf-8")

    inspection = service.upload_and_inspect(
        file_bytes=csv_bytes,
        filename="test_collision.csv",
        user_role="UNDERWRITER",
    )

    # Attempting to map two different file columns to the same SQL target column must FAIL
    with pytest.raises(ValueError, match="Коллизия сопоставления"):
        service.update_mapping(
            session_id=inspection.session_id,
            target_table="invoices",
            custom_mappings={
                "Сумма счета": "gross_amount",
                "Комментарий": "gross_amount",
            },
        )


