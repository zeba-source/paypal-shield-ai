import argparse
from pathlib import Path

import mysql.connector
from mysql.connector import Error

from config import DB_CONFIG, MYSQL_DATABASE


def get_server_connection():
    return mysql.connector.connect(
        host=DB_CONFIG["host"],
        user=DB_CONFIG["user"],
        password=DB_CONFIG["password"],
        autocommit=True,
        charset="utf8mb4",
        use_unicode=True,
    )


def table_exists(conn, table_name: str) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT COUNT(*)
            FROM information_schema.tables
            WHERE table_schema = DATABASE()
              AND table_name = %s
            """,
            (table_name,),
        )
        return cur.fetchone()[0] > 0


def column_exists(conn, table_name: str, column_name: str) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT COUNT(*)
            FROM information_schema.columns
            WHERE table_schema = DATABASE()
              AND table_name = %s
              AND column_name = %s
            """,
            (table_name, column_name),
        )
        return cur.fetchone()[0] > 0


def index_exists(conn, table_name: str, index_name: str) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT COUNT(*)
            FROM information_schema.statistics
            WHERE table_schema = DATABASE()
              AND table_name = %s
              AND index_name = %s
            """,
            (table_name, index_name),
        )
        return cur.fetchone()[0] > 0


def get_auto_increment_column(conn, table_name: str):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = DATABASE()
              AND table_name = %s
              AND extra LIKE '%auto_increment%'
            ORDER BY ordinal_position
            LIMIT 1
            """,
            (table_name,),
        )
        row = cur.fetchone()
        return row[0] if row else None


def create_database_if_missing():
    conn = get_server_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(f"CREATE DATABASE IF NOT EXISTS `{MYSQL_DATABASE}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
    finally:
        conn.close()


def ensure_transactions_table(conn):
    if not table_exists(conn, "transactions"):
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS `transactions` (
                    `txn_id` BIGINT NOT NULL AUTO_INCREMENT,
                    `step` INT NULL,
                    `type` VARCHAR(30) NULL,
                    `amount` DECIMAL(18,2) NULL,
                    `nameOrig` VARCHAR(50) NULL,
                    `oldbalanceOrg` DECIMAL(18,2) NULL,
                    `newbalanceOrig` DECIMAL(18,2) NULL,
                    `nameDest` VARCHAR(50) NULL,
                    `oldbalanceDest` DECIMAL(18,2) NULL,
                    `newbalanceDest` DECIMAL(18,2) NULL,
                    `isFraud` TINYINT NULL,
                    `isFlaggedFraud` TINYINT NULL,
                    `event_time` DATETIME NULL,
                    `lat` DOUBLE NULL,
                    `lon` DOUBLE NULL,
                    `country` VARCHAR(50) NULL,
                    `city` VARCHAR(50) NULL,
                    `scenario` VARCHAR(30) NULL,
                    PRIMARY KEY (`txn_id`)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """
            )
        return

    if not column_exists(conn, "transactions", "txn_id"):
        auto_col = get_auto_increment_column(conn, "transactions")
        if auto_col:
            with conn.cursor() as cur:
                cur.execute(
                    f"ALTER TABLE `transactions` CHANGE COLUMN `{auto_col}` `txn_id` BIGINT NOT NULL AUTO_INCREMENT"
                )
        else:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    ALTER TABLE `transactions`
                    ADD COLUMN `txn_id` BIGINT NOT NULL AUTO_INCREMENT,
                    ADD UNIQUE KEY `uk_transactions_txn_id` (`txn_id`)
                    """
                )

    for column_name, column_sql in {
        "event_time": "DATETIME NULL",
        "lat": "DOUBLE NULL",
        "lon": "DOUBLE NULL",
        "country": "VARCHAR(50) NULL",
        "city": "VARCHAR(50) NULL",
        "scenario": "VARCHAR(30) NULL",
    }.items():
        if not column_exists(conn, "transactions", column_name):
            with conn.cursor() as cur:
                cur.execute(
                    f"ALTER TABLE `transactions` ADD COLUMN `{column_name}` {column_sql}"
                )

    for index_name, index_sql in {
        "idx_transactions_nameOrig_event_time": "(`nameOrig`, `event_time`)",
        "idx_transactions_nameDest_event_time": "(`nameDest`, `event_time`)",
    }.items():
        if not index_exists(conn, "transactions", index_name):
            with conn.cursor() as cur:
                cur.execute(f"CREATE INDEX `{index_name}` ON `transactions` {index_sql}")


def ensure_other_tables(conn):
    with conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS `txn_events` (
                `id` BIGINT NOT NULL AUTO_INCREMENT,
                `txn_id` BIGINT NOT NULL,
                `stage` ENUM('RECEIVED','AGENTS_SCORED','POLICY_DECISION','2FA_SENT','2FA_VERIFIED','2FA_FAILED','2FA_EXPIRED','APPROVED','HELD','BLOCKED','ANALYST_REVIEW') NOT NULL,
                `detail` JSON NULL,
                `created_at` DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
                PRIMARY KEY (`id`),
                INDEX `idx_txn_events_txn_created` (`txn_id`, `created_at`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """
        )

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS `account_profiles` (
                `account_id` VARCHAR(50) NOT NULL,
                `home_city` VARCHAR(50) NULL,
                `home_country` VARCHAR(50) NULL,
                `home_lat` DOUBLE NULL,
                `home_lon` DOUBLE NULL,
                `avg_amount` DECIMAL(18,2) NULL,
                `txn_count` INT NULL,
                `hour_histogram` JSON NULL,
                `trusted_locations` JSON NULL,
                `last_txn_time` DATETIME NULL,
                `last_lat` DOUBLE NULL,
                `last_lon` DOUBLE NULL,
                `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (`account_id`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """
        )

    if not column_exists(conn, "account_profiles", "trusted_locations"):
        with conn.cursor() as cur:
            cur.execute("ALTER TABLE `account_profiles` ADD COLUMN `trusted_locations` JSON NULL")
    if not column_exists(conn, "account_profiles", "last_city"):
        with conn.cursor() as cur:
            cur.execute("ALTER TABLE `account_profiles` ADD COLUMN `last_city` VARCHAR(50) NULL")

    with conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS `risk_alerts` (
                `id` BIGINT NOT NULL AUTO_INCREMENT,
                `txn_id` BIGINT NOT NULL,
                `account_id` VARCHAR(50) NULL,
                `frequency_score` DOUBLE NULL,
                `time_score` DOUBLE NULL,
                `geo_score` DOUBLE NULL,
                `final_score` DOUBLE NULL,
                `action` VARCHAR(50) NULL,
                `reasons` JSON NULL,
                `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (`id`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS `verification_requests` (
                `id` BIGINT NOT NULL AUTO_INCREMENT,
                `txn_id` BIGINT NOT NULL,
                `account_id` VARCHAR(50) NULL,
                `otp_hash` VARCHAR(255) NULL,
                `dev_otp` VARCHAR(6) NULL,
                `status` ENUM('PENDING','PASSED','FAILED','EXPIRED') DEFAULT 'PENDING',
                `attempts` INT DEFAULT 0,
                `expires_at` DATETIME NULL,
                `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (`id`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS `txn_status` (
                `txn_id` BIGINT NOT NULL,
                `status` ENUM('APPROVED','PENDING_2FA','HELD','BLOCKED') DEFAULT 'APPROVED',
                `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (`txn_id`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS `review_log` (
                `id` BIGINT NOT NULL AUTO_INCREMENT,
                `txn_id` BIGINT NOT NULL,
                `analyst` VARCHAR(100) NULL,
                `decision` VARCHAR(50) NULL,
                `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (`id`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """
        )

    if not column_exists(conn, "verification_requests", "dev_otp"):
        with conn.cursor() as cur:
            cur.execute("ALTER TABLE `verification_requests` ADD COLUMN `dev_otp` VARCHAR(6) NULL")

    apply_paypal_migration(conn)


def apply_paypal_migration(conn):
    sql_dir = Path(__file__).resolve().parent / "sql"
    with conn.cursor() as cur:
        for migration_path in sorted(sql_dir.glob("*.sql")):
            for statement in migration_path.read_text(encoding="utf-8").split(";"):
                if statement.strip():
                    cur.execute(statement)


def reset_transactions_if_requested(conn, reset: bool):
    if not reset:
        return
    if table_exists(conn, "transactions"):
        with conn.cursor() as cur:
            cur.execute("TRUNCATE TABLE `transactions`")
        print("TRUNCATED transactions")


def main():
    parser = argparse.ArgumentParser(description="Initialize the FinTech MySQL schema.")
    parser.add_argument("--reset", action="store_true", help="Truncate transactions before continuing.")
    args = parser.parse_args()

    create_database_if_missing()

    from db import get_connection

    conn = get_connection()
    try:
        ensure_transactions_table(conn)
        ensure_other_tables(conn)
        reset_transactions_if_requested(conn, args.reset)
        print("Schema ready.")
        with conn.cursor() as cur:
            cur.execute("SHOW TABLES")
            tables = cur.fetchall()
            print("Tables:")
            for row in tables:
                print(row[0])
    finally:
        conn.close()


if __name__ == "__main__":
    main()
