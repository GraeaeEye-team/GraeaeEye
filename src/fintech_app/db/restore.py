"""Database restore utilities for GraeaeEye.

Provides automated and safe restoration from PostgreSQL binary dumps (`pg_dump -F c`)
with zero-wipeout protection and empty-database checks.
"""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
import re
import shutil
import subprocess
from typing import Any, List, Optional, Union

import psycopg

from fintech_app.core.config import settings

logger = logging.getLogger("fintech_app.restore")

# Regular expression to extract timestamps from standard backup filenames
# e.g., backup_session_2026-09-21_183851.dump
TIMESTAMP_REGEX = re.compile(r"(\d{4}-\d{2}-\d{2}_\d{6})")


def get_candidate_backup_dirs(backup_dir: Optional[Union[str, Path]] = None) -> List[Path]:
    """Returns an ordered list of candidate directories where backups may reside."""
    if backup_dir:
        return [Path(backup_dir)]

    candidates: List[Path] = []
    configured_dir = getattr(settings, "backup_dir", None)
    if configured_dir:
        candidates.append(Path(configured_dir))

    env_dir = os.getenv("BACKUP_DIR")
    if env_dir:
        candidates.append(Path(env_dir))

    # Standard container and repository locations
    candidates.append(Path("/app/src/fintech_app/db/backups"))
    candidates.append(Path(__file__).parent / "backups")
    candidates.append(Path("src/fintech_app/db/backups"))

    # De-duplicate while preserving order
    seen = set()
    result = []
    for c in candidates:
        resolved = c.resolve() if c.is_absolute() else c
        if str(resolved) not in seen:
            seen.add(str(resolved))
            result.append(c)
    return result


def find_latest_backup(backup_dir: Optional[Union[str, Path]] = None) -> Optional[Path]:
    """Scans backup directories and returns the path to the newest valid PostgreSQL dump.

    Valid dumps must:
    1. Have extension .dump
    2. Not be a staging .tmp file
    3. Have file size > 0 bytes
    4. Are sorted primarily by embedded timestamp (YYYY-MM-DD_HHMMSS), falling back to st_mtime.
    """
    candidates = get_candidate_backup_dirs(backup_dir)
    dumps: List[Path] = []

    for d in candidates:
        if d.is_dir():
            for p in d.glob("*.dump"):
                if not p.name.endswith(".tmp") and p.is_file():
                    try:
                        if p.stat().st_size > 0:
                            dumps.append(p)
                    except OSError:
                        continue

    if not dumps:
        return None

    def dump_sort_key(p: Path) -> tuple[str, float]:
        m = TIMESTAMP_REGEX.search(p.name)
        ts_key = m.group(1) if m else ""
        try:
            mtime = p.stat().st_mtime
        except OSError:
            mtime = 0.0
        return (ts_key, mtime)

    dumps.sort(key=dump_sort_key, reverse=True)
    return dumps[0]


def is_database_empty(
    host: Optional[str] = None,
    port: Optional[int] = None,
    user: Optional[str] = None,
    password: Optional[str] = None,
    dbname: Optional[str] = None,
) -> bool:
    """Checks whether the database is empty (uninitialized or 0 rows in key tables).

    Returns:
        True if the database has no schema or 0 records in 'businesses'.
        False if 'businesses' contains at least 1 record.
    """
    h = host or settings.postgres_server
    p = port or settings.postgres_port
    u = user or settings.postgres_user
    pwd = password or settings.postgres_password
    db = dbname or settings.postgres_db

    check_table_sql = (
        "SELECT EXISTS ("
        "  SELECT 1 FROM information_schema.tables "
        "  WHERE table_schema = 'public' AND table_name = 'businesses'"
        ");"
    )

    try:
        with psycopg.connect(
            host=h,
            port=p,
            user=u,
            password=pwd,
            dbname=db,
            connect_timeout=3,
        ) as conn:
            with conn.cursor() as cur:
                cur.execute(check_table_sql)
                row = cur.fetchone()
                if not row or not row[0]:
                    # Schema doesn't have 'businesses' table yet -> database is completely empty
                    return True

                cur.execute("SELECT COUNT(*) FROM businesses;")
                count_row = cur.fetchone()
                count = int(count_row[0]) if count_row and count_row[0] is not None else 0
                return count == 0

    except Exception as exc:
        logger.warning(
            "[AutoRestore] Failed to query database population status (%s). Assuming not empty to prevent data loss.",
            exc,
        )
        return False


def restore_database_dump(
    dump_path: Path,
    host: Optional[str] = None,
    port: Optional[int] = None,
    user: Optional[str] = None,
    password: Optional[str] = None,
    dbname: Optional[str] = None,
) -> bool:
    """Restores a PostgreSQL custom dump (`pg_dump -F c`) into the target database via `pg_restore`.

    Treats returncode 0 (clean success) and 1 (success with non-fatal warnings,
    such as dropping non-existent tables via --clean --if-exists) as valid completions.
    """
    h = host or settings.postgres_server
    p = port or settings.postgres_port
    u = user or settings.postgres_user
    pwd = password or settings.postgres_password
    db = dbname or settings.postgres_db

    pg_restore_bin = shutil.which("pg_restore")
    if not pg_restore_bin:
        err_msg = (
            "Utility 'pg_restore' not found in system PATH. "
            "Ensure 'postgresql-client' package is installed."
        )
        logger.error("[AutoRestore] %s", err_msg)
        raise FileNotFoundError(err_msg)

    cmd = [
        pg_restore_bin,
        "-h",
        h,
        "-p",
        str(p),
        "-U",
        u,
        "-d",
        db,
        "--clean",
        "--if-exists",
        "--no-owner",
        "--no-privileges",
        str(dump_path),
    ]

    env = os.environ.copy()
    if pwd:
        env["PGPASSWORD"] = pwd

    logger.info(
        "[AutoRestore] Executing pg_restore from %s into %s@%s:%d/%s...",
        dump_path.name,
        u,
        h,
        p,
        db,
    )

    try:
        proc = subprocess.run(
            cmd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )

        # In PostgreSQL:
        # returncode 0: Success without warnings.
        # returncode 1: Completed with non-fatal warnings (e.g. notices or drop if-exists warnings).
        # returncode > 1: Fatal execution failure.
        if proc.returncode in (0, 1):
            if proc.returncode == 1 and proc.stderr:
                logger.info(
                    "[AutoRestore] pg_restore completed with non-fatal warnings: %s",
                    proc.stderr.strip()[:300],
                )
            logger.info(
                "[AutoRestore] Database successfully restored from '%s' (exit code: %d).",
                dump_path.name,
                proc.returncode,
            )
            return True

        logger.error(
            "[AutoRestore] pg_restore failed with exit code %d: %s",
            proc.returncode,
            proc.stderr.strip(),
        )
        return False

    except Exception as exc:
        logger.error("[AutoRestore] Unexpected error executing pg_restore: %s", exc)
        return False


async def auto_restore_last_backup_if_configured(force: Optional[bool] = None) -> bool:
    """Orchestrates safe automated database restoration during application startup.

    Guarantees:
    1. Executes only if settings.auto_restore_last_db_backup is True.
    2. Zero-wipeout protection: Skips restoration if database is already populated,
       unless force=True or FORCE_RESTORE=true is explicitly configured.
    3. Locates the latest valid dump file and restores it cleanly.
    """
    if not getattr(settings, "auto_restore_last_db_backup", False):
        logger.debug("[AutoRestore] auto_restore_last_db_backup is disabled.")
        return False

    effective_force = (
        force if force is not None else getattr(settings, "force_restore_db_backup", False)
    )

    if not effective_force:
        is_empty = await asyncio.to_thread(is_database_empty)
        if not is_empty:
            logger.info(
                "[AutoRestore] Database already contains records. Skipping restore to prevent data loss. "
                "(Use FORCE_RESTORE=true to override)"
            )
            return False

    latest_dump = find_latest_backup()
    if not latest_dump:
        logger.warning(
            "[AutoRestore] AUTO_RESTORE_LAST_DB_BACKUP is enabled, but no valid .dump files were found."
        )
        return False

    try:
        size_kb = latest_dump.stat().st_size / 1024
    except OSError:
        size_kb = 0.0

    logger.info(
        "[AutoRestore] Target database is empty. Restoring from latest backup: %s (%.1f KB)...",
        latest_dump.name,
        size_kb,
    )

    success = await asyncio.to_thread(restore_database_dump, latest_dump)
    if success:
        logger.info(
            "[AutoRestore] 🎉 Successfully populated database tables from latest backup: %s",
            latest_dump.name,
        )
    else:
        logger.error(
            "[AutoRestore] ❌ Failed to restore database from %s.",
            latest_dump.name,
        )

    return success
