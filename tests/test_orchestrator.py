from datetime import datetime, timedelta

import pytest

from agents.geo_agent import GeoAgent
from agents.time_agent import TimeAgent
from db import get_connection
from orchestrator import RiskOrchestrator


PREFIX = "TEST_ORCH_"


def insert_transaction(cursor, txn):
    cursor.execute(
        """
        INSERT INTO transactions (
            step, type, amount, nameOrig, oldbalanceOrg, newbalanceOrig,
            nameDest, oldbalanceDest, newbalanceDest, isFraud, isFlaggedFraud,
            event_time, lat, lon, country, city
        ) VALUES (1, %s, %s, %s, %s, %s, %s, 0, 0, 0, 0, %s, %s, %s, %s, %s)
        """,
        (
            txn["type"], txn["amount"], txn["nameOrig"],
            txn.get("oldbalanceOrg", 1000), txn.get("newbalanceOrig", 1000),
            txn["nameDest"], txn["event_time"], txn["lat"], txn["lon"],
            txn["country"], txn["city"],
        ),
    )
    return cursor.lastrowid


@pytest.fixture
def orchestrator_data():
    conn = get_connection()
    cursor = conn.cursor()
    accounts = [f"{PREFIX}NORMAL", f"{PREFIX}NIGHT", f"{PREFIX}TRAVEL"]
    try:
        cursor.execute(
            "DELETE FROM transactions WHERE nameOrig LIKE %s OR nameDest LIKE %s",
            (f"{PREFIX}%", f"{PREFIX}%"),
        )
        cursor.execute("DELETE FROM account_profiles WHERE account_id LIKE %s", (f"{PREFIX}%",))
        conn.commit()

        time_agent = TimeAgent()
        geo_agent = GeoAgent()
        daytime = datetime(2026, 1, 1, 10, 0)
        for index in range(10):
            seed = {
                "nameOrig": accounts[1], "event_time": daytime - timedelta(days=index),
                "amount": 100, "lat": 19.076, "lon": 72.8777,
                "city": "Mumbai", "country": "India",
            }
            time_agent.update_profile(seed)
        geo_agent.update_profile({
            "nameOrig": accounts[2], "event_time": daytime,
            "lat": 21.1458, "lon": 79.0882, "city": "Nagpur", "country": "India",
        })

        txns = [
            {
                "type": "PAYMENT", "amount": 25, "nameOrig": accounts[0],
                "nameDest": f"{PREFIX}SHOP", "event_time": daytime,
                "lat": 19.076, "lon": 72.8777, "city": "Mumbai", "country": "India",
            },
            {
                "type": "PAYMENT", "amount": 600, "nameOrig": accounts[1],
                "nameDest": f"{PREFIX}NIGHT_SHOP", "event_time": datetime(2026, 1, 2, 2, 0),
                "lat": 19.076, "lon": 72.8777, "city": "Mumbai", "country": "India",
                "oldbalanceOrg": 1000, "newbalanceOrig": 400,
            },
            {
                "type": "TRANSFER", "amount": 100, "nameOrig": accounts[2],
                "nameDest": f"{PREFIX}TRAVEL_DEST", "event_time": daytime + timedelta(minutes=30),
                "lat": 51.5074, "lon": -0.1278, "city": "London", "country": "UK",
            },
        ]
        for txn in txns:
            txn["txn_id"] = insert_transaction(cursor, txn)
        conn.commit()
        yield txns
    finally:
        cursor.execute(
            "DELETE FROM transactions WHERE nameOrig LIKE %s OR nameDest LIKE %s",
            (f"{PREFIX}%", f"{PREFIX}%"),
        )
        cursor.execute("DELETE FROM account_profiles WHERE account_id LIKE %s", (f"{PREFIX}%",))
        cursor.execute(
            "DELETE FROM txn_status WHERE txn_id NOT IN (SELECT txn_id FROM transactions)"
        )
        cursor.execute(
            "DELETE FROM risk_alerts WHERE account_id LIKE %s", (f"{PREFIX}%",)
        )
        conn.commit()
        cursor.close()
        conn.close()


def test_processes_normal_night_and_travel_transactions(orchestrator_data):
    results = [RiskOrchestrator().process(txn) for txn in orchestrator_data]

    assert len(results) == 3
    assert all(set(result) >= {"txn_id", "scores", "final_score", "action"} for result in results)
    assert results[0]["action"] == "ALLOW"
    assert results[1]["final_score"] >= 40
    assert results[2]["final_score"] >= 70