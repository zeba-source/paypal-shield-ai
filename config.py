import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

MYSQL_HOST = os.getenv("MYSQL_HOST", "localhost")
MYSQL_USER = os.getenv("MYSQL_USER", "root")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "")
MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "fintech_db")
KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "localhost:9092")
API_URL = os.getenv("API_URL", "http://localhost:8000")

DB_CONFIG = {
    "host": MYSQL_HOST,
    "user": MYSQL_USER,
    "password": MYSQL_PASSWORD,
    "database": MYSQL_DATABASE,
    "autocommit": False,
    "charset": "utf8mb4",
    "use_unicode": True,
}

TOPIC_TRANSACTIONS = os.getenv("KAFKA_TRANSACTIONS_TOPIC", "transactions-topic")
TOPIC_RISK_DECISIONS = os.getenv("KAFKA_RISK_DECISIONS_TOPIC", "risk-decisions-topic")
TOPIC_EVENTS = TOPIC_TRANSACTIONS

AGENT_THRESHOLDS = {
    "amount_anomaly": 0.75,
    "velocity": 0.70,
    "geo_risk": 0.80,
    "timing_risk": 0.65,
}

POLICY_THRESHOLDS = {
    "ALLOW": 0,
    "PENDING_2FA": 50,
    "HOLD": 75,
    "BLOCK": 90,
}

RISK_SCORES = {
    "frequency_score": 0.35,
    "time_score": 0.25,
    "geo_score": 0.40,
}

__all__ = [
    "BASE_DIR",
    "DB_CONFIG",
    "MYSQL_HOST",
    "MYSQL_USER",
    "MYSQL_PASSWORD",
    "MYSQL_DATABASE",
    "KAFKA_BOOTSTRAP",
    "API_URL",
    "TOPIC_TRANSACTIONS",
    "TOPIC_RISK_DECISIONS",
    "TOPIC_EVENTS",
    "AGENT_THRESHOLDS",
    "POLICY_THRESHOLDS",
    "RISK_SCORES",
    "load_dotenv",
]
