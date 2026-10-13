import subprocess
import sys
import time
import os
import tempfile
from pathlib import Path

from kafka import KafkaAdminClient
from kafka.admin import NewTopic
from mysql.connector import Error

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from config import (
    KAFKA_BOOTSTRAP,
)
from db import get_connection


PYTHON = sys.executable


def check_mysql():
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT VERSION()")
        version = cursor.fetchone()[0]
        print(f"MySQL: {version}")
    finally:
        cursor.close()
        conn.close()


def create_smoke_topic(topic_name):
    admin = KafkaAdminClient(bootstrap_servers=KAFKA_BOOTSTRAP, client_id="fintech-smoke")
    try:
        admin.create_topics(
            [NewTopic(name=topic_name, num_partitions=1, replication_factor=1)],
            validate_only=False,
        )
        print(f"Kafka: connected at {KAFKA_BOOTSTRAP}")
    finally:
        admin.close()


def transaction_stats():
    conn = get_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT COUNT(*) AS row_count,
                   SUM(event_time IS NULL) AS null_event_time,
                   SUM(city IS NULL) AS null_city
            FROM transactions
            """
        )
        return cursor.fetchone()
    finally:
        cursor.close()
        conn.close()


def sample_rows():
    conn = get_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT event_time, nameOrig, city, country
            FROM transactions
            ORDER BY txn_id
            LIMIT 5
            """
        )
        return cursor.fetchall()
    finally:
        cursor.close()
        conn.close()


def main():
    consumer = None
    consumer_log_path = None
    try:
        check_mysql()
        topic_name = f"transactions-smoke-{os.getpid()}-{int(time.time())}"
        create_smoke_topic(topic_name)

        setup = subprocess.run(
            [PYTHON, "setup_db.py", "--reset"],
            cwd=ROOT,
            check=True,
        )
        del setup

        process_env = os.environ.copy()
        process_env["KAFKA_TRANSACTIONS_TOPIC"] = topic_name

        consumer_log = tempfile.NamedTemporaryFile(mode="w+", encoding="utf-8", delete=False)
        consumer_log_path = consumer_log.name
        consumer = subprocess.Popen(
            [PYTHON, "consumer.py"],
            cwd=ROOT,
            env=process_env,
            stdout=consumer_log,
            stderr=subprocess.STDOUT,
        )
        consumer_log.close()
        time.sleep(1)

        subprocess.run(
            [PYTHON, "producer.py", "--limit", "200", "--delay", "0.01"],
            cwd=ROOT,
            env=process_env,
            check=True,
            stdout=subprocess.DEVNULL,
        )

        deadline = time.monotonic() + 30
        stats = {"row_count": 0, "null_event_time": 0, "null_city": 0}
        while time.monotonic() < deadline:
            stats = transaction_stats()
            if stats["row_count"] >= 200:
                break
            time.sleep(0.5)

        if consumer.poll() is not None:
            details = Path(consumer_log_path).read_text(encoding="utf-8").strip()
            raise RuntimeError(
                f"consumer.py exited early with code {consumer.returncode}: {details}"
            )

        rows = sample_rows()
        print(f"Row count: {stats['row_count']}")
        print("Sample rows:")
        for row in rows:
            print(row)

        valid = (
            stats["row_count"] == 200
            and stats["null_event_time"] == 0
            and stats["null_city"] == 0
            and len(rows) == 5
        )
        if not valid:
            raise AssertionError("Expected 200 rows with non-NULL event_time and city")

        print("PASS")
        return 0
    except (Error, OSError, RuntimeError, TimeoutError, AssertionError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    finally:
        if consumer is not None and consumer.poll() is None:
            consumer.terminate()
            try:
                consumer.wait(timeout=5)
            except subprocess.TimeoutExpired:
                consumer.kill()
                consumer.wait()


if __name__ == "__main__":
    raise SystemExit(main())