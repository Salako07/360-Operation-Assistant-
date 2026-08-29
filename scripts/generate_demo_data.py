#!/usr/bin/env python3
"""CLI utility to generate, validate, and seed NovaDesk synthetic enterprise data."""

import argparse
from pathlib import Path
import sys
import time
from typing import Any

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "src"))

from operations_agent.data.database import get_db_connection, get_db_path, init_db
from operations_agent.data.generator import SEED, generate_synthetic_enterprise_data
from operations_agent.data.scenarios import DEMO_SCENARIOS


def validate_enterprise_database(db_path: Path) -> dict[str, Any]:
    """Execute referential integrity, temporal, and scenario validation checks."""
    conn = get_db_connection(db_path)
    issues: list[str] = []

    # 1. Foreign Key Checks
    fk_errors = conn.execute("PRAGMA foreign_key_check;").fetchall()
    if fk_errors:
        issues.append(f"Foreign key violations found: {len(fk_errors)}")

    # 2. Temporal Logic: Transactions must not precede Customer joined_on date
    invalid_tx = conn.execute("""
        SELECT COUNT(*) FROM transactions t
        JOIN customers c ON t.customer_id = c.customer_id
        WHERE t.occurred_on < c.joined_on
    """).fetchone()[0]
    if invalid_tx > 0:
        issues.append(f"Found {invalid_tx} transactions occurring before customer signup date.")

    # 3. Temporal Logic: Invoices must not precede Customer joined_on date
    invalid_inv = conn.execute("""
        SELECT COUNT(*) FROM invoices i
        JOIN customers c ON i.customer_id = c.customer_id
        WHERE i.issue_date < c.joined_on
    """).fetchone()[0]
    if invalid_inv > 0:
        issues.append(f"Found {invalid_inv} invoices issued before customer signup date.")

    # 4. Support Ticket Resolution Time Validity
    invalid_tickets = conn.execute("""
        SELECT COUNT(*) FROM support_tickets
        WHERE resolved_at IS NOT NULL AND resolved_at < created_at
    """).fetchone()[0]
    if invalid_tickets > 0:
        issues.append(f"Found {invalid_tickets} support tickets resolved before creation.")

    # 5. Deliberate Scenarios Presence
    for scenario in DEMO_SCENARIOS:
        row = conn.execute("SELECT customer_id, company_name, account_status, plan_name FROM customers WHERE customer_id = ?", (scenario.customer_id,)).fetchone()
        if not row:
            issues.append(f"Missing deliberate scenario customer {scenario.customer_id} ({scenario.company_name})")

    # Counts
    counts = {
        "customers": conn.execute("SELECT COUNT(*) FROM customers").fetchone()[0],
        "subscriptions": conn.execute("SELECT COUNT(*) FROM subscriptions").fetchone()[0],
        "transactions": conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0],
        "invoices": conn.execute("SELECT COUNT(*) FROM invoices").fetchone()[0],
        "usage_records": conn.execute("SELECT COUNT(*) FROM product_usage").fetchone()[0],
        "support_tickets": conn.execute("SELECT COUNT(*) FROM support_tickets").fetchone()[0],
        "interactions": conn.execute("SELECT COUNT(*) FROM customer_interactions").fetchone()[0],
        "knowledge_articles": conn.execute("SELECT COUNT(*) FROM knowledge_base").fetchone()[0],
        "account_managers": conn.execute("SELECT COUNT(*) FROM account_managers").fetchone()[0],
    }
    conn.close()

    return {
        "valid": len(issues) == 0,
        "issues": issues,
        "counts": counts,
    }


def main() -> int:
    """Generate and validate the synthetic enterprise dataset."""
    parser = argparse.ArgumentParser(description="NovaDesk Enterprise Synthetic Data Generator")
    parser.add_argument("--customers", type=int, default=10000, help="Number of customer records to generate (default: 10,000)")
    parser.add_argument("--seed", type=int, default=SEED, help="Deterministic random seed (default: 42)")
    parser.add_argument("--db-path", type=str, default=None, help="Target SQLite database file path")
    parser.add_argument("--validate-only", action="store_true", help="Run validation without regenerating data")
    args = parser.parse_args()

    target_db = Path(args.db_path) if args.db_path else get_db_path()

    print("================================================================")
    print("        NOVADESK ENTERPRISE SYNTHETIC DATA ENVIRONMENT          ")
    print("================================================================")
    print(f"Target Database: {target_db.resolve()}")
    print(f"Random Seed:     {args.seed}")
    print(f"Target Scale:    {args.customers:,} Customers")
    print("----------------------------------------------------------------")

    start_time = time.perf_counter()

    if not args.validate_only:
        print("[1/2] Generating relational synthetic dataset...")
        stats = generate_synthetic_enterprise_data(
            db_path=target_db,
            customer_count=args.customers,
            seed=args.seed,
        )
        gen_elapsed = time.perf_counter() - start_time
        print(f"      Generation completed in {gen_elapsed:.2f} seconds.")
    else:
        print("[1/2] Skipping generation (--validate-only active)...")

    print("[2/2] Validating relational integrity and business scenarios...")
    val_result = validate_enterprise_database(target_db)
    val_elapsed = time.perf_counter() - start_time

    print("----------------------------------------------------------------")
    print("                    DATASET RECORD COUNTS                       ")
    print("----------------------------------------------------------------")
    for entity, count in val_result["counts"].items():
        print(f"  • {entity.replace('_', ' ').title():<24}: {count:>10,}")
    print(f"  • Investigation Scenarios : {len(DEMO_SCENARIOS):>10,}")
    print("----------------------------------------------------------------")

    if val_result["valid"]:
        print(f"STATUS: SUCCESS - All relationships and {len(DEMO_SCENARIOS)} benchmark scenarios verified in {val_elapsed:.2f}s!")
        return 0
    else:
        print("STATUS: FAILED - Data validation issues detected:")
        for issue in val_result["issues"]:
            print(f"  ! {issue}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
