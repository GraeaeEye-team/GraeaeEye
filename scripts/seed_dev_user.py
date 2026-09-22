"""
Seed script to initialize development user in the database.

Usage:
    python -m scripts.seed_dev_user
"""

from __future__ import annotations

import asyncio
import logging
import sys
from uuid import uuid4

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from ..auth.security import hash_password
from ..core.config import settings
from ..db.mock_connection import MockDatabase

from ..db.connection import Database

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("seed_dev_user")

DEV_EMAIL = "analyst@graeae.eye"
DEV_PASSWORD_PLAIN = "correct-horse-battery-staple"
DEV_FULL_NAME = "Graeae Senior Underwriter"
DEV_ROLE = "ANALYST"


async def seed_user() -> None:
    """Seeds the default development analyst user if not already present."""
    if settings.use_mock_engine or Database is None:
        logger.info("Using MockDatabase (USE_MOCK_ENGINE=%s)", settings.use_mock_engine)
        db = MockDatabase.get_instance()
        await db.open()
    else:
        logger.info(
            "Connecting to real PostgreSQL database at %s:%s",
            settings.postgres_server,
            settings.postgres_port,
        )
        try:
            db = Database.get_instance()
            await asyncio.wait_for(db.open(), timeout=2.0)
        except Exception as exc:
            logger.warning("Could not connect to PostgreSQL (%s). Falling back to MockDatabase.", exc)
            db = MockDatabase.get_instance()
            await db.open()

    try:
        # Check if user already exists
        check_rep = await db.get_records_from_users(find_only_first=True, email=DEV_EMAIL)
        if check_rep.success and check_rep.data:
            print(f"User {DEV_EMAIL} already exists. Skipping.")
            return

        # Hash password and insert
        hashed = hash_password(DEV_PASSWORD_PLAIN)
        insert_rep = await db.add_record_to_users(
            user_id=uuid4(),
            email=DEV_EMAIL,
            password_hash=hashed,
            full_name=DEV_FULL_NAME,
            role=DEV_ROLE,
            is_active=True,
        )

        if insert_rep.success:
            print(f"Successfully seeded development user: {DEV_EMAIL} (role: {DEV_ROLE})")
        else:
            print(f"Failed to seed user {DEV_EMAIL}")
            sys.exit(1)
    finally:
        try:
            await db.close()
        except Exception:
            pass


if __name__ == "__main__":
    asyncio.run(seed_user())
