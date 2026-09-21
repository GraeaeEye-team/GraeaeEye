"""
Seed script to populate GOOD_SME and RISKY_SME financial profile fixtures via DAL.

Usage:
    python -m scripts.seed_fixtures --profile good_sme|risky_sme|both [--use-mock]
"""

from __future__ import annotations

import argparse
import asyncio
import csv
from datetime import date, datetime, timedelta
from decimal import Decimal
import logging
import os
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID, uuid4

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

sys.path.insert(0, os.path.abspath("src"))

from fintech_app.core.config import settings
from fintech_app.db.mock_connection import MockDatabase

try:
    from fintech_app.db.connection import Database
except ImportError:
    Database = None  # type: ignore

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("seed_fixtures")

BASE_FIXTURES_DIR = Path("data/fixtures")


def _parse_date(val: Optional[str], ref_today: Optional[date] = None) -> Optional[date]:
    """Parses date string or template string into datetime.date."""
    if not val or not val.strip():
        return None
    s = val.strip()
    ref = ref_today or date.today()

    # Dynamic template support
    if s.startswith("{TODAY") and s.endswith("}"):
        expr = s[1:-1]
        if expr == "TODAY":
            return ref
        if "-" in expr:
            days = int(expr.split("-")[1].rstrip("d"))
            return ref - timedelta(days=days)
        if "+" in expr:
            days = int(expr.split("+")[1].rstrip("d"))
            return ref + timedelta(days=days)

    d = date.fromisoformat(s.split("T")[0].split(" ")[0])
    # Relative year drift adjustment if test runs in future years
    if ref.year != 2026:
        delta_years = ref.year - 2026
        try:
            d = d.replace(year=d.year + delta_years)
        except ValueError:
            d = d + timedelta(days=delta_years * 365)
    return d


def _parse_datetime(val: Optional[str], ref_today: Optional[date] = None) -> Optional[datetime]:
    """Parses datetime string into datetime.datetime."""
    if not val or not val.strip():
        return None
    s = val.strip()
    ref = ref_today or date.today()

    parts = s.split(" ")
    d_part = parts[0]
    t_part = parts[1] if len(parts) > 1 else "00:00:00"

    parsed_d = _parse_date(d_part, ref_today=ref)
    if parsed_d is None:
        return None

    time_comps = [int(c) for c in t_part.split(":")]
    return datetime(
        parsed_d.year,
        parsed_d.month,
        parsed_d.day,
        time_comps[0],
        time_comps[1] if len(time_comps) > 1 else 0,
        time_comps[2] if len(time_comps) > 2 else 0,
    )


def _parse_bool(val: Optional[str]) -> bool:
    if not val:
        return False
    return val.strip().lower() in ("true", "1", "yes", "t")


def _read_csv(filepath: Path) -> List[Dict[str, str]]:
    """Reads a CSV file into a list of row dicts."""
    if not filepath.exists():
        raise FileNotFoundError(f"Fixture CSV not found: {filepath}")
    with open(filepath, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader)


async def seed_profile(
    profile: str,
    db: Any,
    fixtures_base_dir: Optional[Path] = None,
) -> Optional[UUID]:
    """
    Seeds a given profile (good_sme or risky_sme) into the database.
    Idempotent: skips seeding if business with tax_id already exists and prints 'exists'.
    Returns the UUID of the business.
    """
    base_dir = fixtures_base_dir or BASE_FIXTURES_DIR
    profile_dir = base_dir / profile
    if not profile_dir.is_dir():
        raise FileNotFoundError(f"Profile directory not found: {profile_dir}")

    # 1. Parse business.csv
    biz_rows = _read_csv(profile_dir / "business.csv")
    if not biz_rows:
        raise ValueError(f"Empty business.csv for profile '{profile}'")

    biz_data = biz_rows[0]
    tax_id = biz_data["tax_id"].strip()
    legal_name = biz_data["legal_name"].strip()
    industry_code = biz_data["industry_code"].strip()
    reg_date = _parse_date(biz_data["registration_date"]) or date(2020, 1, 1)
    total_board_seats = int(biz_data.get("total_board_seats", 1))
    independent_directors_count = int(biz_data.get("independent_directors_count", 0))

    # Idempotency check: verify if business already exists
    existing_rep = await db.get_records_from_businesses(find_only_first=True, tax_id=tax_id)
    if existing_rep.success and existing_rep.data:
        existing_data = existing_rep.data[0] if isinstance(existing_rep.data, list) else existing_rep.data
        existing_id = UUID(str(existing_data["business_id"]))
        print(
            f"Profile '{profile}' with tax_id '{tax_id}' already exists in database (business_id={existing_id}). Skipping."
        )
        return existing_id

    # 2. Add business
    business_id = uuid4()
    biz_insert = await db.add_record_to_businesses(
        tax_id=tax_id,
        legal_name=legal_name,
        industry_code=industry_code,
        registration_date=reg_date,
        business_id=business_id,
        total_board_seats=total_board_seats,
        independent_directors_count=independent_directors_count,
    )
    if not biz_insert.success:
        raise RuntimeError(f"Failed to insert business for {profile}: {biz_insert.error}")

    # 3. Obligations: iterate rows -> add_record_to_credit_obligations(...)
    ob_rows = _read_csv(profile_dir / "obligations.csv")
    obligations_count = 0
    for row in ob_rows:
        await db.add_record_to_credit_obligations(
            business_id=business_id,
            lender_name=row["lender_name"].strip(),
            facility_type=row["facility_type"].strip(),
            principal_amount=Decimal(row["principal_amount"].strip()),
            outstanding_balance=Decimal(row["outstanding_balance"].strip()),
            monthly_payment=Decimal(row["monthly_payment"].strip()),
            past_due_30d_count=int(row.get("past_due_30d_count", 0)),
            past_due_90d_count=int(row.get("past_due_90d_count", 0)),
            historical_defaults_count=int(row.get("historical_defaults_count", 0)),
        )
        obligations_count += 1

    # 4. Shareholders: iterate rows -> add_record_to_shareholders(...)
    sh_rows = _read_csv(profile_dir / "shareholders.csv")
    shareholders_count = 0
    for row in sh_rows:
        await db.add_record_to_shareholders(
            business_id=business_id,
            shareholder_name=row["shareholder_name"].strip(),
            equity_percentage=Decimal(row["equity_percentage"].strip()),
            is_management_member=_parse_bool(row.get("is_management_member", "false")),
        )
        shareholders_count += 1

    # 5. Accounts: iterate rows -> add_record_to_bank_accounts(...)
    acc_rows = _read_csv(profile_dir / "accounts.csv")
    account_ids: List[UUID] = []
    for row in acc_rows:
        acc_id = uuid4()
        await db.add_record_to_bank_accounts(
            business_id=business_id,
            currency=row["currency"].strip(),
            current_balance=Decimal(row["current_balance"].strip()),
            overdraft_limit=Decimal(row.get("overdraft_limit", "0.00").strip()),
            account_id=acc_id,
        )
        account_ids.append(acc_id)
    primary_acc_id = account_ids[0] if account_ids else uuid4()

    # 6. Invoices: iterate invoices.csv -> add unique counterparties -> bulk_insert_invoices(...)
    inv_rows = _read_csv(profile_dir / "invoices.csv")
    counterparty_map: Dict[Tuple[str, str], UUID] = {}
    for row in inv_rows:
        cp_name = row["counterparty_name"].strip()
        cp_role = row.get("counterparty_role", "CLIENT").strip().upper()
        key = (cp_name, cp_role)
        if key not in counterparty_map:
            cp_id = uuid4()
            await db.add_record_to_counterparties(
                business_id=business_id,
                legal_name=cp_name,
                counterparty_role=cp_role,
                counterparty_id=cp_id,
            )
            counterparty_map[key] = cp_id

    invoice_records: List[Dict[str, Any]] = []
    for row in inv_rows:
        cp_name = row["counterparty_name"].strip()
        cp_role = row.get("counterparty_role", "CLIENT").strip().upper()
        cp_id = counterparty_map[(cp_name, cp_role)]

        inv_record = {
            "invoice_id": uuid4(),
            "business_id": business_id,
            "counterparty_id": cp_id,
            "invoice_type": row["invoice_type"].strip().upper(),
            "gross_amount": Decimal(row["gross_amount"].strip()),
            "issue_date": _parse_date(row["issue_date"]),
            "due_date": _parse_date(row["due_date"]),
            "actual_payment_date": _parse_date(row.get("actual_payment_date")),
            "status": row["status"].strip().upper(),
        }
        invoice_records.append(inv_record)

    await db.bulk_insert_invoices(invoice_records)

    # 7. Transactions: bulk_insert_transactions(records)
    tx_rows = _read_csv(profile_dir / "transactions.csv")
    transaction_records: List[Dict[str, Any]] = []
    for row in tx_rows:
        tx_record = {
            "transaction_id": uuid4(),
            "business_id": business_id,
            "account_id": primary_acc_id,
            "timestamp": _parse_datetime(row["timestamp"]),
            "amount": Decimal(row["amount"].strip()),
            "direction": row["direction"].strip().upper(),
            "category": row["category"].strip().upper(),
            "liquidity_class": row.get("liquidity_class", "IMMEDIATE_CASH").strip().upper(),
        }
        transaction_records.append(tx_record)

    await db.bulk_insert_transactions(transaction_records)

    print(
        f"Seeded profile '{profile}': business_id={business_id} "
        f"(tax_id={tax_id}, accounts={len(acc_rows)}, shareholders={shareholders_count}, "
        f"obligations={obligations_count}, counterparties={len(counterparty_map)}, "
        f"invoices={len(invoice_records)}, transactions={len(transaction_records)})"
    )
    return business_id


async def run_seeding(profile: str = "both", use_mock: bool = False) -> Dict[str, Optional[UUID]]:
    """Connects to database and executes seeding for requested profile(s)."""
    is_mock = use_mock or settings.use_mock_engine or Database is None
    if is_mock:
        logger.info("Using MockDatabase instance for seeding (use_mock=%s)", is_mock)
        db = MockDatabase.get_instance()
        await db.open()
    else:
        logger.info("Connecting to PostgreSQL at %s:%s", settings.postgres_server, settings.postgres_port)
        try:
            db = Database.get_instance()
            await asyncio.wait_for(db.open(), timeout=2.0)
        except Exception as exc:
            logger.warning("Could not connect to PostgreSQL (%s). Falling back to MockDatabase.", exc)
            db = MockDatabase.get_instance()
            await db.open()

    results: Dict[str, Optional[UUID]] = {}
    try:
        profiles_to_seed = ["good_sme", "risky_sme"] if profile == "both" else [profile]
        for p in profiles_to_seed:
            biz_id = await seed_profile(p, db)
            results[p] = biz_id
    finally:
        try:
            await db.close()
        except Exception:
            pass

    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed GOOD_SME / RISKY_SME financial profile fixtures.")
    parser.add_argument(
        "--profile",
        type=str,
        choices=["good_sme", "risky_sme", "both"],
        default="both",
        help="Profile to seed: good_sme, risky_sme, or both (default: both)",
    )
    parser.add_argument(
        "--use-mock",
        action="store_true",
        default=False,
        help="Use in-memory MockDatabase regardless of environment",
    )
    args = parser.parse_args()
    asyncio.run(run_seeding(profile=args.profile, use_mock=args.use_mock))


if __name__ == "__main__":
    main()
