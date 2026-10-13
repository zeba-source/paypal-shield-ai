# from kafka import KafkaConsumer
# import json

# consumer = KafkaConsumer(
#     'transactions-topic',
#     bootstrap_servers='localhost:9092',
#     auto_offset_reset='earliest',
#     enable_auto_commit=True,
#     value_deserializer=lambda x: json.loads(x.decode('utf-8'))
# )

# print("Waiting for messages...\n")

# for message in consumer:
#     data = message.value

#     print("Received:", data)

#     # Example Fraud Detection
#     if 'amount' in data:
#         try:
#             amount = float(data['amount'])

#             if amount > 50000:
#                 print("⚠️ FRAUD ALERT: High Transaction Detected")

#         except:
#             pass


import json

from kafka import KafkaConsumer

from config import KAFKA_BOOTSTRAP, TOPIC_TRANSACTIONS, load_dotenv
from db import get_connection

load_dotenv()

INSERT_SQL = """
INSERT INTO transactions (
    step, type, amount, nameOrig,
    oldbalanceOrg, newbalanceOrig,
    nameDest, oldbalanceDest,
    newbalanceDest, isFraud,
    isFlaggedFraud, event_time,
    lat, lon, country, city
)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
"""


def get_db_connection():
    return get_connection()


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
        normalize_int(data.get("step"), 0),
        data.get("type"),
        normalize_float(data.get("amount"), 0.0),
        data.get("nameOrig"),
        normalize_float(data.get("oldbalanceOrg"), 0.0),
        normalize_float(data.get("newbalanceOrig"), 0.0),
        data.get("nameDest"),
        normalize_float(data.get("oldbalanceDest"), 0.0),
        normalize_float(data.get("newbalanceDest"), 0.0),
        normalize_int(data.get("isFraud"), 0),
        normalize_int(data.get("isFlaggedFraud"), 0),
        data.get("event_time"),
        normalize_float(data.get("lat"), 0.0),
        normalize_float(data.get("lon"), 0.0),
        data.get("country"),
        data.get("city"),
    )


consumer = KafkaConsumer(
    TOPIC_TRANSACTIONS,
    bootstrap_servers=KAFKA_BOOTSTRAP,
    auto_offset_reset="earliest",
    enable_auto_commit=True,
    value_deserializer=lambda value: json.loads(value.decode("utf-8")),
)

print("Waiting for messages...\n")

batch = []

try:
    db = get_db_connection()
    cursor = db.cursor()

    for message in consumer:
        data = message.value
        if not isinstance(data, dict):
            continue

        print("Received:", data)
        batch.append(build_transaction_values(data))

        if len(batch) >= 100:
            cursor.executemany(INSERT_SQL, batch)
            db.commit()
            print(f"Inserted batch of {len(batch)} rows into MySQL")
            batch.clear()

        if float(data.get("amount", 0) or 0) > 50000:
            print("⚠️ FRAUD ALERT: High Transaction Detected")

    if batch:
        cursor.executemany(INSERT_SQL, batch)
        db.commit()
        print(f"Inserted final batch of {len(batch)} rows into MySQL")

finally:
    if "cursor" in locals():
        cursor.close()
    if "db" in locals():
        db.close()