"""
Integration tests with real database connection (SQLite):
Verifies dry-run non-persistence, atomic commit, rollback on error, and duplicate prevention.
"""

import sqlite3
from pathlib import Path
import pytest

from smart_credit_parser import UniversalDataParser, ParseOptions

from tests.conftest import SCHEMA_PATH


@pytest.fixture
def test_db():
    conn = sqlite3.connect(":memory:")
    cursor = conn.cursor()
    # Create SQLite equivalent of businesses table
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


def test_dry_run_leaves_db_completely_empty(tmp_path: Path, test_db):
    """Verifies that dry_run=True writes ZERO records to the database."""
    csv_file = tmp_path / "companies.csv"
    csv_file.write_text(
        "tax_id,legal_name,industry_code,registration_date\n"
        "1002600001111,AgroCorp SRL,AGRI-01,2020-01-15\n"
        "1002600002222,TechNova SRL,IT-02,2021-03-20\n",
        encoding="utf-8",
    )

    parser = UniversalDataParser(schema_path=SCHEMA_PATH, db_connection=test_db)

    # Execute with dry_run = True
    result = parser.parse_file(csv_file, options=ParseOptions(target_table="businesses", dry_run=True))
    assert result.success is True
    assert result.report.rows_accepted == 2

    # Verify DB has 0 rows
    cursor = test_db.cursor()
    cursor.execute("SELECT COUNT(*) FROM businesses;")
    count = cursor.fetchone()[0]
    assert count == 0, f"Expected 0 rows in DB after dry-run, but found {count}"


def test_live_commit_writes_records(tmp_path: Path, test_db):
    """Verifies that dry_run=False commits records to the database."""
    csv_file = tmp_path / "companies.csv"
    csv_file.write_text(
        "tax_id,legal_name,industry_code,registration_date\n"
        "1002600001111,AgroCorp SRL,AGRI-01,2020-01-15\n"
        "1002600002222,TechNova SRL,IT-02,2021-03-20\n",
        encoding="utf-8",
    )

    parser = UniversalDataParser(schema_path=SCHEMA_PATH, db_connection=test_db)

    # Execute with dry_run = False
    result = parser.parse_file(csv_file, options=ParseOptions(target_table="businesses", dry_run=False))
    assert result.success is True

    cursor = test_db.cursor()
    cursor.execute("SELECT COUNT(*) FROM businesses;")
    count = cursor.fetchone()[0]
    assert count == 2


def test_reupload_avoids_duplicates(tmp_path: Path, test_db):
    """Verifies that re-uploading the same file does not create duplicate records (ON CONFLICT DO NOTHING)."""
    csv_file = tmp_path / "companies.csv"
    csv_file.write_text(
        "tax_id,legal_name,industry_code,registration_date\n"
        "1002600001111,AgroCorp SRL,AGRI-01,2020-01-15\n",
        encoding="utf-8",
    )

    parser = UniversalDataParser(schema_path=SCHEMA_PATH, db_connection=test_db)

    # First upload
    parser.parse_file(csv_file, options=ParseOptions(target_table="businesses", dry_run=False))
    cursor = test_db.cursor()
    cursor.execute("SELECT COUNT(*) FROM businesses;")
    assert cursor.fetchone()[0] == 1

    # Second upload of the exact same file
    parser.parse_file(csv_file, options=ParseOptions(target_table="businesses", dry_run=False))
    cursor.execute("SELECT COUNT(*) FROM businesses;")
    # Count should STILL be 1 because of ON CONFLICT DO NOTHING
    assert cursor.fetchone()[0] == 1


def test_atomic_transaction_rollback_on_failure(test_db):
    """Verifies that if a write fails mid-batch, rollback occurs and 0 records are persisted."""
    from smart_credit_parser.engine.transactional_writer import TransactionalWriter

    writer = TransactionalWriter(db_connection=test_db)

    # Valid record followed by a record that causes a SQL error (non-existent column)
    records = [
        {"tax_id": "1002600003333", "legal_name": "Valid SRL", "industry_code": "IT", "registration_date": "2020-01-01"},
        {"tax_id": "1002600004444", "NON_EXISTENT_COLUMN": "Crash"},
    ]

    with pytest.raises(RuntimeError, match="Transaction failed and was rolled back"):
        writer.write_records("businesses", records, dry_run=False)

    cursor = test_db.cursor()
    cursor.execute("SELECT COUNT(*) FROM businesses WHERE tax_id = '1002600003333';")
    # Due to atomic transaction rollback, the first record was NOT kept!
    assert cursor.fetchone()[0] == 0
