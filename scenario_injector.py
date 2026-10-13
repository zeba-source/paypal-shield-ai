import argparse
from datetime import datetime, timedelta
import json

from kafka import KafkaProducer

from config import KAFKA_BOOTSTRAP, TOPIC_TRANSACTIONS

CITIES = {
    "Nagpur": (21.1458, 79.0882, "India"),
    "London": (51.5074, -0.1278, "UK"),
}


def transaction(event_time, txn_type, amount, sender, receiver, city, country, lat, lon, old_balance, new_balance, scenario):
    return {
        "step": 1,
        "type": txn_type,
        "amount": amount,
        "nameOrig": sender,
        "oldbalanceOrg": old_balance,
        "newbalanceOrig": new_balance,
        "nameDest": receiver,
        "oldbalanceDest": 0.0,
        "newbalanceDest": 0.0,
        "isFraud": 0,
        "isFlaggedFraud": 0,
        "event_time": event_time.isoformat(),
        "lat": lat,
        "lon": lon,
        "country": country,
        "city": city,
        "scenario": scenario,
    }


def mule_events():
    base = datetime(2026, 2, 1, 2, 0)
    events = []
    for index in range(10):
        events.append(transaction(
            base + timedelta(minutes=index // 2), "TRANSFER", 100.0,
            f"C_MULE_SENDER_{index + 1}", "C_MULE_1", "Nagpur", "India",
            CITIES["Nagpur"][0], CITIES["Nagpur"][1], 1000.0, 900.0, "mule",
        ))
    events.append(transaction(
        base + timedelta(minutes=6), "CASH_OUT", 950.0,
        "C_MULE_1", "C_MULE_CASHOUT", "Nagpur", "India",
        CITIES["Nagpur"][0], CITIES["Nagpur"][1], 1000.0, 50.0, "mule",
    ))
    return events


def night_events():
    base = datetime(2026, 3, 1, 10, 0)
    events = []
    for index in range(40):
        events.append(transaction(
            base - timedelta(days=index), "PAYMENT", 100.0,
            "C_DAY_USER", f"C_DAY_SHOP_{index + 1}", "Nagpur", "India",
            CITIES["Nagpur"][0], CITIES["Nagpur"][1], 1000.0, 900.0, "night",
        ))
    events.append(transaction(
        datetime(2026, 4, 1, 2, 30), "TRANSFER", 800.0,
        "C_DAY_USER", "C_NIGHT_DEST", "Nagpur", "India",
        CITIES["Nagpur"][0], CITIES["Nagpur"][1], 1000.0, 200.0, "night",
    ))
    return events


def travel_events():
    base = datetime(2026, 5, 1, 12, 0)
    return [
        transaction(
            base, "PAYMENT", 100.0, "C_TRAVEL_USER", "C_NAGPUR_SHOP", "Nagpur", "India",
            CITIES["Nagpur"][0], CITIES["Nagpur"][1], 1000.0, 900.0, "travel",
        ),
        transaction(
            base + timedelta(minutes=20), "TRANSFER", 100.0, "C_TRAVEL_USER", "C_LONDON_DEST", "London", "UK",
            CITIES["London"][0], CITIES["London"][1], 900.0, 800.0, "travel",
        ),
    ]


def main():
    parser = argparse.ArgumentParser(description="Inject deterministic fraud-demo scenarios into Kafka.")
    parser.add_argument("--scenario", choices=("mule", "night", "travel", "all"), default="all")
    args = parser.parse_args()
    builders = {"mule": mule_events, "night": night_events, "travel": travel_events}
    selected = list(builders) if args.scenario == "all" else [args.scenario]
    producer = KafkaProducer(
        bootstrap_servers=KAFKA_BOOTSTRAP,
        value_serializer=lambda value: json.dumps(value).encode("utf-8"),
    )
    try:
        total = 0
        for name in selected:
            events = builders[name]()
            for event in events:
                producer.send(TOPIC_TRANSACTIONS, value=event)
            producer.flush()
            print(f"Published {len(events)} {name} events")
            total += len(events)
        print(f"Published {total} scenario events to {TOPIC_TRANSACTIONS}")
    finally:
        producer.close()


if __name__ == "__main__":
    main()
