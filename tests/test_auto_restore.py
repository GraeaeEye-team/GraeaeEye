"""Test Suite for Database Auto-Restore and Zero-Wipeout Protection.

Validates:
1. Configuration setting parsing (AUTO_RESTORE_LAST_DB_BACKUP, FORCE_RESTORE).
2. Backup discovery ordering by embedded timestamp & mtime (ignoring .tmp and 0-byte files).
3. Empty-DB detection to prevent accidental wipeout of populated databases.
4. Safe pg_restore execution flags and returncode handling (0 and 1 as success).
5. Orchestration in auto_restore_last_backup_if_configured with force override support.
"""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from fintech_app.core.config import Settings
from fintech_app.db.restore import (
    auto_restore_last_backup_if_configured,
    find_latest_backup,
    is_database_empty,
    restore_database_dump,
)


def test_settings_auto_restore_parsing(monkeypatch: pytest.MonkeyPatch):
    """Verifies that Settings parses AUTO_RESTORE_LAST_DB_BACKUP and FORCE_RESTORE flags."""
    monkeypatch.setenv("AUTO_RESTORE_LAST_DB_BACKUP", "true")
    monkeypatch.setenv("FORCE_RESTORE", "yes")
    s = Settings()
    assert s.auto_restore_last_db_backup is True
    assert s.force_restore_db_backup is True

    monkeypatch.setenv("AUTO_RESTORE_LAST_DB_BACKUP", "0")
    monkeypatch.setenv("FORCE_RESTORE", "false")
    s2 = Settings()
    assert s2.auto_restore_last_db_backup is False
    assert s2.force_restore_db_backup is False


def test_find_latest_backup_ordering_and_filtering(tmp_path: Path):
    """Verifies that find_latest_backup correctly picks the newest valid dump."""
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()

    # Empty directory
    assert find_latest_backup(backup_dir) is None

    # Create older and newer dumps
    older_dump = backup_dir / "backup_session_2026-09-20_120000.dump"
    older_dump.write_bytes(b"DATA_OLD")

    newer_dump = backup_dir / "backup_session_2026-09-21_183851.dump"
    newer_dump.write_bytes(b"DATA_NEW")

    # Staging .tmp file should be ignored even if newer
    tmp_dump = backup_dir / "backup_session_2026-09-22_999999.dump.tmp"
    tmp_dump.write_bytes(b"DATA_TEMP")

    # 0-byte file should be ignored
    empty_dump = backup_dir / "backup_session_2026-09-23_000000.dump"
    empty_dump.write_bytes(b"")

    latest = find_latest_backup(backup_dir)
    assert latest is not None
    assert latest.name == "backup_session_2026-09-21_183851.dump"


def test_is_database_empty_detection():
    """Verifies empty database logic with mocked psycopg connection."""
    # Case 1: Schema has no 'businesses' table -> Empty
    with patch("psycopg.connect") as mock_connect:
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_connect.return_value.__enter__.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur

        # First query (information_schema): table doesn't exist
        mock_cur.fetchone.return_value = (False,)
        assert is_database_empty() is True

    # Case 2: 'businesses' exists but has 0 rows -> Empty
    with patch("psycopg.connect") as mock_connect:
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_connect.return_value.__enter__.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur

        # Table exists, count is 0
        mock_cur.fetchone.side_effect = [(True,), (0,)]
        assert is_database_empty() is True

    # Case 3: 'businesses' has 15 rows -> NOT empty
    with patch("psycopg.connect") as mock_connect:
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_connect.return_value.__enter__.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur

        # Table exists, count is 15
        mock_cur.fetchone.side_effect = [(True,), (15,)]
        assert is_database_empty() is False

    # Case 4: Connection error -> Defensively returns False to prevent data loss
    with patch("psycopg.connect", side_effect=Exception("Database unreachable")):
        assert is_database_empty() is False


def test_restore_database_dump_invocation(tmp_path: Path):
    """Verifies that pg_restore is called with correct flags and exit codes are handled."""
    dump_file = tmp_path / "test.dump"
    dump_file.write_bytes(b"VALID_DUMP")

    # Case 1: Clean returncode 0
    with patch("shutil.which", return_value="/usr/bin/pg_restore"), patch("subprocess.run") as mock_run:
        mock_run.return_value = subprocess.CompletedProcess(
            args=["pg_restore"],
            returncode=0,
            stdout="",
            stderr="",
        )

        res = restore_database_dump(
            dump_file,
            host="testhost",
            port=5432,
            user="testuser",
            password="testpassword",
            dbname="testdb",
        )
        assert res is True
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert "--clean" in cmd
        assert "--if-exists" in cmd
        assert "--no-owner" in cmd
        assert "--no-privileges" in cmd
        assert cmd[cmd.index("-h") + 1] == "testhost"
        assert cmd[cmd.index("-d") + 1] == "testdb"
        assert mock_run.call_args[1]["env"]["PGPASSWORD"] == "testpassword"

    # Case 2: returncode 1 (non-fatal warnings, e.g. notices during drop) -> Success
    with patch("shutil.which", return_value="/usr/bin/pg_restore"), patch("subprocess.run") as mock_run:
        mock_run.return_value = subprocess.CompletedProcess(
            args=["pg_restore"],
            returncode=1,
            stdout="",
            stderr="WARNING: errors ignored on restore: 1",
        )

        res = restore_database_dump(dump_file)
        assert res is True

    # Case 3: returncode 2 (fatal error) -> Failure
    with patch("shutil.which", return_value="/usr/bin/pg_restore"), patch("subprocess.run") as mock_run:
        mock_run.return_value = subprocess.CompletedProcess(
            args=["pg_restore"],
            returncode=2,
            stdout="",
            stderr="FATAL: cannot connect to database",
        )

        res = restore_database_dump(dump_file)
        assert res is False


def test_restore_database_dump_missing_binary(tmp_path: Path):
    """Verifies that missing pg_restore binary raises FileNotFoundError."""
    dump_file = tmp_path / "test.dump"
    dump_file.write_bytes(b"DATA")
    with patch("shutil.which", return_value=None):
        with pytest.raises(FileNotFoundError, match="postgresql-client"):
            restore_database_dump(dump_file)


@pytest.mark.asyncio
async def test_auto_restore_orchestration_disabled():
    """Verifies that auto_restore_last_backup_if_configured does nothing when disabled."""
    with patch("fintech_app.db.restore.settings.auto_restore_last_db_backup", False):
        result = await auto_restore_last_backup_if_configured()
        assert result is False


@pytest.mark.asyncio
async def test_auto_restore_orchestration_database_not_empty(tmp_path: Path):
    """Verifies that auto_restore skips when DB has data and force=False (Zero-Wipeout protection)."""
    with patch("fintech_app.db.restore.settings.auto_restore_last_db_backup", True), \
         patch("fintech_app.db.restore.settings.force_restore_db_backup", False), \
         patch("fintech_app.db.restore.is_database_empty", return_value=False), \
         patch("fintech_app.db.restore.restore_database_dump") as mock_restore:

        result = await auto_restore_last_backup_if_configured()
        assert result is False
        mock_restore.assert_not_called()


@pytest.mark.asyncio
async def test_auto_restore_orchestration_success_when_empty(tmp_path: Path):
    """Verifies that auto_restore triggers restore when DB is empty and backup is available."""
    dump_file = tmp_path / "backup_session_2026-09-21_183851.dump"
    dump_file.write_bytes(b"DUMP_CONTENT")

    with patch("fintech_app.db.restore.settings.auto_restore_last_db_backup", True), \
         patch("fintech_app.db.restore.settings.force_restore_db_backup", False), \
         patch("fintech_app.db.restore.is_database_empty", return_value=True), \
         patch("fintech_app.db.restore.find_latest_backup", return_value=dump_file), \
         patch("fintech_app.db.restore.restore_database_dump", return_value=True) as mock_restore:

        result = await auto_restore_last_backup_if_configured()
        assert result is True
        mock_restore.assert_called_once_with(dump_file)


@pytest.mark.asyncio
async def test_auto_restore_force_override_on_populated_db(tmp_path: Path):
    """Verifies that force=True overrides the empty DB check and triggers restore."""
    dump_file = tmp_path / "backup_session_2026-09-21_183851.dump"
    dump_file.write_bytes(b"DUMP_CONTENT")

    with patch("fintech_app.db.restore.settings.auto_restore_last_db_backup", True), \
         patch("fintech_app.db.restore.settings.force_restore_db_backup", True), \
         patch("fintech_app.db.restore.find_latest_backup", return_value=dump_file), \
         patch("fintech_app.db.restore.restore_database_dump", return_value=True) as mock_restore:

        result = await auto_restore_last_backup_if_configured(force=True)
        assert result is True
        mock_restore.assert_called_once_with(dump_file)

