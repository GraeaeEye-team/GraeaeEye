"""Automated PostgreSQL backup daemon with zero-wipeout protection.

Periodically generates native PostgreSQL custom binary dumps (`pg_dump -F c`)
and captures a final consistent state on container termination (SIGTERM/SIGINT).
"""

from datetime import datetime
import logging
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from typing import Any, Optional

import psycopg

# Structured logging configuration with [BackupDaemon] prefix
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [BackupDaemon] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("BackupDaemon")

# Global flag to manage graceful shutdown
SHUTDOWN_REQUESTED: bool = False

# Configuration defaults from environment
POSTGRES_SERVER: str = os.getenv("POSTGRES_SERVER", "postgres")
POSTGRES_PORT: int = int(os.getenv("POSTGRES_PORT", "5432"))
POSTGRES_USER: str = os.getenv("POSTGRES_USER", "postgres")
POSTGRES_PASSWORD: str = os.getenv("POSTGRES_PASSWORD", "postgres")
POSTGRES_DB: str = os.getenv("POSTGRES_DB", "graeae_eye_db")
BACKUP_DIR: Path = Path(
    os.getenv(
        "BACKUP_DIR",
        "/app/src/fintech_app/db/backups"
        if Path("/app").exists()
        else "src/fintech_app/db/backups",
    )
)
BACKUP_INTERVAL_SECONDS: int = int(os.getenv("BACKUP_INTERVAL_SECONDS", "300"))


def sigterm_handler(signum: int, frame: Any) -> None:
    """Signal handler for graceful shutdown on SIGTERM and SIGINT."""
    global SHUTDOWN_REQUESTED
    logger.info("Received termination signal (%s). Initiating graceful shutdown...", signum)
    SHUTDOWN_REQUESTED = True


def is_database_populated(
    host: Optional[str] = None,
    port: Optional[int] = None,
    user: Optional[str] = None,
    password: Optional[str] = None,
    dbname: Optional[str] = None,
) -> bool:
    """Verify that key tables contain data before performing a backup.

    Prevents zero-wipeout where an unpopulated or empty database replaces
    an existing valid backup.
    """
    h = host or POSTGRES_SERVER
    p = port or POSTGRES_PORT
    u = user or POSTGRES_USER
    pwd = password or POSTGRES_PASSWORD
    db = dbname or POSTGRES_DB

    query = (
        "SELECT "
        "(SELECT COUNT(*) FROM businesses) + "
        "(SELECT COUNT(*) FROM transactions) + "
        "(SELECT COUNT(*) FROM analysis_runs);"
    )
    try:
        with psycopg.connect(
            host=h,
            port=p,
            user=u,
            password=pwd,
            dbname=db,
            connect_timeout=5,
        ) as conn:
            with conn.cursor() as cur:
                cur.execute(query)
                row = cur.fetchone()
                if row and row[0] is not None:
                    total_rows = int(row[0])
                    logger.info("Population check: %d key rows found.", total_rows)
                    return total_rows > 0
                return False
    except Exception as exc:
        logger.warning(
            "Database population verification failed or DB unpopulated: %s",
            exc,
        )
        return False


def create_safe_dump(
    session_file: Path,
    host: Optional[str] = None,
    port: Optional[int] = None,
    user: Optional[str] = None,
    password: Optional[str] = None,
    dbname: Optional[str] = None,
) -> bool:
    """Perform a 3-stage zero-wipeout backup into session_file.

    1. Verify database is populated.
    2. Write compressed custom dump to .tmp staging file via pg_dump.
    3. Validate integrity via pg_restore --list and swap atomically.
    """
    h = host or POSTGRES_SERVER
    p = port or POSTGRES_PORT
    u = user or POSTGRES_USER
    pwd = password or POSTGRES_PASSWORD
    db = dbname or POSTGRES_DB

    if not is_database_populated(host=h, port=p, user=u, password=pwd, dbname=db):
        logger.warning(
            "Database is empty or unpopulated. Dump aborted to protect active state."
        )
        return False

    tmp_file = session_file.with_name(f"{session_file.name}.tmp")
    tmp_file.parent.mkdir(parents=True, exist_ok=True)

    try:
        cmd = [
            "pg_dump",
            "-h",
            h,
            "-p",
            str(p),
            "-U",
            u,
            "-d",
            db,
            "-F",
            "c",
            "-b",
            "-v",
            "-f",
            str(tmp_file),
        ]
        env = os.environ.copy()
        if pwd:
            env["PGPASSWORD"] = pwd

        logger.info("Executing pg_dump to staging file: %s", tmp_file)
        dump_proc = subprocess.run(
            cmd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        if dump_proc.returncode != 0:
            logger.error("pg_dump failed (code %d): %s", dump_proc.returncode, dump_proc.stderr)
            if tmp_file.exists():
                tmp_file.unlink()
            return False

        logger.info("Validating staging file integrity via pg_restore --list...")
        restore_cmd = ["pg_restore", "--list", str(tmp_file)]
        restore_proc = subprocess.run(
            restore_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        if restore_proc.returncode != 0:
            logger.error(
                "pg_restore header validation failed (code %d): %s",
                restore_proc.returncode,
                restore_proc.stderr,
            )
            if tmp_file.exists():
                tmp_file.unlink()
            return False

        if not tmp_file.exists() or tmp_file.stat().st_size == 0:
            logger.error("Staging dump file is missing or empty.")
            if tmp_file.exists():
                tmp_file.unlink()
            return False

        os.replace(tmp_file, session_file)
        size_kb = session_file.stat().st_size / 1024
        logger.info(
            "Atomic swap complete. Session backup ready: %s (%.2f KB)",
            session_file,
            size_kb,
        )
        return True

    except Exception as exc:
        logger.error("Unexpected failure during safe dump creation: %s", exc)
        if tmp_file.exists():
            try:
                tmp_file.unlink()
            except OSError:
                pass
        return False


def main() -> None:
    """Main backup daemon loop with graceful shutdown handling."""
    signal.signal(signal.SIGTERM, sigterm_handler)
    signal.signal(signal.SIGINT, sigterm_handler)

    backup_dir = BACKUP_DIR
    backup_dir.mkdir(parents=True, exist_ok=True)

    session_filename = f"backup_session_{datetime.now().strftime('%Y-%m-%d_%H%M%S')}.dump"
    session_file = backup_dir / session_filename

    logger.info("Starting Backup Daemon.")
    logger.info("Session dump target: %s", session_file)
    logger.info(
        "Target DB: %s@%s:%d/%s",
        POSTGRES_USER,
        POSTGRES_SERVER,
        POSTGRES_PORT,
        POSTGRES_DB,
    )
    logger.info("Interval: %d seconds. Awaiting cycles...", BACKUP_INTERVAL_SECONDS)

    create_safe_dump(session_file)

    elapsed = 0
    while not SHUTDOWN_REQUESTED:
        time.sleep(1)
        elapsed += 1
        if elapsed >= BACKUP_INTERVAL_SECONDS:
            logger.info(
                "Backup interval (%ds) reached. Triggering dump...",
                BACKUP_INTERVAL_SECONDS,
            )
            create_safe_dump(session_file)
            elapsed = 0

    logger.info("Shutdown requested. Performing final state dump before exit...")
    create_safe_dump(session_file)
    logger.info("Graceful shutdown complete. Exiting.")
    sys.exit(0)


if __name__ == "__main__":
    main()

