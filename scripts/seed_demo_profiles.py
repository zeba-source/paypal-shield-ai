import argparse
import os
import sys
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config import load_dotenv
from db import get_connection


def seed(payer_id: str, home_country: str, reset: bool) -> None:
    base = datetime.now().replace(hour=10, minute=0, second=0, microsecond=0)
    conn = get_connection()
    try:
        cursor = conn.cursor()
        if reset:
            cursor.execute("DELETE FROM transactions WHERE nameOrig = %s", (payer_id,))
            cursor.execute("DELETE FROM account_profiles WHERE account_id = %s", (payer_id,))
        for index in range(40):
            event_time = base - timedelta(days=index + 1)
            cursor.execute(
                """
                INSERT INTO transactions
                    (step, type, amount, nameOrig, nameDest, event_time, country, scenario)
                VALUES (0, 'PAYMENT', %s, %s, %s, %s, %s, 'simulated')
                """,
                (Decimal("60.00"), payer_id, "DEMO_MERCHANT", event_time, home_country),
            )
        histogram = [0] * 24
        histogram[10] = 40
        cursor.execute(
            """
            INSERT INTO account_profiles
                (account_id, home_country, avg_amount, txn_count, hour_histogram, last_txn_time)
            VALUES (%s, %s, %s, 40, %s, %s)
            ON DUPLICATE KEY UPDATE
                home_country = VALUES(home_country), avg_amount = VALUES(avg_amount),
                txn_count = VALUES(txn_count), hour_histogram = VALUES(hour_histogram),
                last_txn_time = VALUES(last_txn_time)
            """,
            (payer_id, home_country, Decimal("60.00"), str(histogram).replace("'", "\""), base - timedelta(days=1)),
        )
        conn.commit()
    finally:
        cursor.close()
        conn.close()
    print(f"Seeded 40 simulated daytime orders for payer {payer_id} in {home_country}.")


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Seed a PayPal Sandbox buyer risk profile.")
    parser.add_argument("--reset", action="store_true", help="Remove this payer's existing demo rows first.")
    args = parser.parse_args()
    payer_id = os.getenv("DEMO_BUYER_PAYER_ID") or f"DEMO_BUYER_{uuid4().hex[:12]}"
    home_country = os.getenv("DEMO_HOME_COUNTRY", "US").upper()
    seed(payer_id, home_country, args.reset)


if __name__ == "__main__":
    main()