import json
import statistics
import time

import requests
from kafka import KafkaConsumer, KafkaProducer

from config import API_URL, KAFKA_BOOTSTRAP, TOPIC_RISK_DECISIONS, TOPIC_TRANSACTIONS
from db import get_connection, record_txn_event
from orchestrator import RiskOrchestrator


INSERT_SQL = """
INSERT INTO transactions (
    step, type, amount, nameOrig,
    oldbalanceOrg, newbalanceOrig,
    nameDest, oldbalanceDest,
    newbalanceDest, isFraud,
    isFlaggedFraud, event_time,
    lat, lon, country, city, scenario
)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
"""


def normalize_float(value, default=0.0):
    try:
        return float(value) if value not in (None, "") else default
    except (TypeError, ValueError):
        return default


def normalize_int(value, default=0):
    try:
        return int(value) if value not in (None, "") else default
    except (TypeError, ValueError):
        return default


def build_transaction_values(data):
    return (
        normalize_int(data.get("step"), 0), data.get("type"),
        normalize_float(data.get("amount"), 0.0), data.get("nameOrig"),
        normalize_float(data.get("oldbalanceOrg"), 0.0),
        normalize_float(data.get("newbalanceOrig"), 0.0), data.get("nameDest"),
        normalize_float(data.get("oldbalanceDest"), 0.0),
        normalize_float(data.get("newbalanceDest"), 0.0),
        normalize_int(data.get("isFraud"), 0), normalize_int(data.get("isFlaggedFraud"), 0),
        data.get("event_time"), normalize_float(data.get("lat"), 0.0),
        normalize_float(data.get("lon"), 0.0), data.get("country"), data.get("city"), data.get("scenario"),
    )


def insert_transaction(data):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(INSERT_SQL, build_transaction_values(data))
        conn.commit()
        return cursor.lastrowid
    finally:
        cursor.close()
        conn.close()


def notify_2fa(txn_id, account_id):
    try:
        requests.post(
            f"{API_URL}/2fa/start",
            json={"txn_id": txn_id, "account_id": account_id},
            timeout=0.25,
        )
    except requests.RequestException as exc:
        print(f"2FA notification unavailable: {exc}")


def main():
    consumer = KafkaConsumer(
        TOPIC_TRANSACTIONS,
        bootstrap_servers=KAFKA_BOOTSTRAP,
        group_id="risk-engine",
        auto_offset_reset="earliest",
        enable_auto_commit=False,
        value_deserializer=lambda value: json.loads(value.decode("utf-8")),
    )
    producer = KafkaProducer(
        bootstrap_servers=KAFKA_BOOTSTRAP,
        value_serializer=lambda value: json.dumps(value).encode("utf-8"),
    )
    orchestrator = RiskOrchestrator()
    latencies = []
    try:
        print("Risk consumer waiting for messages...")
        for message in consumer:
            started = time.perf_counter()
            data = message.value
            if not isinstance(data, dict):
                consumer.commit()
                continue
            txn_id = insert_transaction(data)
            txn = dict(data)
            txn["txn_id"] = txn_id
            record_txn_event(txn_id, "RECEIVED", {"type": txn.get("type"), "amount": txn.get("amount"), "scenario": txn.get("scenario")})
            decision = orchestrator.process(txn)
            producer.send(TOPIC_RISK_DECISIONS, value=decision).get(timeout=5)
            consumer.commit()
            if decision["action"] == "REQUEST_2FA":
                notify_2fa(txn_id, txn.get("nameOrig"))
            latency_ms = (time.perf_counter() - started) * 1000
            latencies.append(latency_ms)
            print(
                f"{txn_id} | {txn.get('type')} | {txn.get('amount')} | "
                f"{decision['scores']} | {decision['action']} | latency_ms={latency_ms:.1f}"
            )
            if len(latencies) % 100 == 0:
                print(
                    f"latencies n={len(latencies)} p50={statistics.median(latencies):.1f}ms "
                    f"p95={_percentile(latencies, 95):.1f}ms"
                )
    except KeyboardInterrupt:
        print("Stopping risk consumer...")
    finally:
        consumer.close()
        producer.flush()
        producer.close()


def _percentile(values, percentile):
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, round((percentile / 100) * (len(ordered) - 1))))
    return ordered[index]


if __name__ == "__main__":
    main()