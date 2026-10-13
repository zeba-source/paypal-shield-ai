import argparse
import hashlib
import json
import random
import time
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
from kafka import KafkaProducer

from config import KAFKA_BOOTSTRAP, TOPIC_TRANSACTIONS, load_dotenv

load_dotenv()

CITY_DATA = {
    "Mumbai": {"country": "India", "lat": 19.0760, "lon": 72.8777},
    "Delhi": {"country": "India", "lat": 28.6139, "lon": 77.2090},
    "Bengaluru": {"country": "India", "lat": 12.9716, "lon": 77.5946},
    "Chennai": {"country": "India", "lat": 13.0827, "lon": 80.2707},
    "Hyderabad": {"country": "India", "lat": 17.3850, "lon": 78.4867},
    "Kolkata": {"country": "India", "lat": 22.5726, "lon": 88.3639},
    "Pune": {"country": "India", "lat": 18.5204, "lon": 73.8567},
    "Ahmedabad": {"country": "India", "lat": 23.0225, "lon": 72.5714},
    "Jaipur": {"country": "India", "lat": 26.9124, "lon": 75.7873},
    "Kochi": {"country": "India", "lat": 9.9312, "lon": 76.2673},
    "Lucknow": {"country": "India", "lat": 26.8467, "lon": 80.9462},
    "Chandigarh": {"country": "India", "lat": 30.7333, "lon": 76.7794},
    "Dubai": {"country": "UAE", "lat": 25.2048, "lon": 55.2708},
    "Singapore": {"country": "Singapore", "lat": 1.3521, "lon": 103.8198},
    "London": {"country": "UK", "lat": 51.5074, "lon": -0.1278},
}
CITY_LIST = list(CITY_DATA.keys())
DEFAULT_DELAY = 0.05


def clean_value(value):
    if hasattr(value, "item"):
        return value.item()
    return value


def get_home_city(account_id):
    digest = hashlib.sha256(str(account_id).encode("utf-8")).hexdigest()
    idx = int(digest, 16) % len(CITY_LIST)
    return CITY_LIST[idx]


def get_destination_city(account_id, row_index):
    home_city = get_home_city(account_id)
    rng = random.Random(f"geo:{account_id}:{row_index}")

    if rng.random() < 0.95:
        return home_city

    alt_cities = [city for city in CITY_LIST if city != home_city]
    return rng.choice(alt_cities)


def build_event_payload(row, row_index):
    payload = {
        key: clean_value(value)
        for key, value in row.items()
    }

    account_id = str(payload.get("nameOrig", ""))
    home_city = get_home_city(account_id)
    city_name = get_destination_city(account_id, row_index)
    city_info = CITY_DATA[city_name]

    step_value = int(payload.get("step", 0) or 0)
    event_rng = random.Random(f"ts:{account_id}:{row_index}")
    event_time = datetime(2026, 1, 1) + timedelta(hours=step_value)
    event_time += timedelta(
        minutes=event_rng.randint(0, 59),
        seconds=event_rng.randint(0, 59),
    )

    payload["event_time"] = event_time.isoformat()
    payload["lat"] = city_info["lat"]
    payload["lon"] = city_info["lon"]
    payload["country"] = city_info["country"]
    payload["city"] = city_name

    if account_id:
        payload["home_city"] = home_city
        payload["home_country"] = CITY_DATA[home_city]["country"]
        payload["home_lat"] = CITY_DATA[home_city]["lat"]
        payload["home_lon"] = CITY_DATA[home_city]["lon"]

    return payload


def parse_args():
    parser = argparse.ArgumentParser(description="Produce FinTech transaction events to Kafka.")
    parser.add_argument(
        "--delay",
        type=float,
        default=0.05,
        help="Delay in seconds between messages (default: 0.05).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of rows to publish (default: all rows).",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()

    producer = KafkaProducer(
        bootstrap_servers=KAFKA_BOOTSTRAP,
        value_serializer=lambda value: json.dumps(value).encode("utf-8"),
    )

    csv_path = Path(__file__).resolve().parent / "small_dataset.csv"
    df = pd.read_csv(csv_path)

    rows = df if args.limit is None else df.head(args.limit)

    for index, row in rows.iterrows():
        data = build_event_payload(row.to_dict(), index)
        producer.send(TOPIC_TRANSACTIONS, value=data)
        print(f"Sent: {data}")
        time.sleep(args.delay)

    producer.flush()
    producer.close()
