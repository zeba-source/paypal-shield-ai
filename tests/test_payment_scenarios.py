from datetime import datetime, timedelta

import pytest

from agents.frequency_agent import FrequencyAgent
from agents.geo_agent import GeoAgent
from agents.time_agent import TimeAgent
from db import get_connection
from orchestrator import RiskOrchestrator


PREFIX = "TEST_PAYMENT_"


@pytest.fixture
def payment_scenarios():
    payer = f"{PREFIX}PAYER"
    merchant = f"{PREFIX}MERCHANT"
    base = datetime(2026, 3, 10, 10, 0)
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM transactions WHERE nameOrig LIKE %s OR nameDest LIKE %s", (f"{PREFIX}%", f"{PREFIX}%"))
        cursor.execute("DELETE FROM account_profiles WHERE account_id = %s", (payer,))
        conn.commit()
        time_agent = TimeAgent()
        geo_agent = GeoAgent()
        for index in range(40):
            time_agent.update_profile({"nameOrig": payer, "event_time": base - timedelta(days=index + 1), "amount": 60})
        geo_agent.update_profile({"nameOrig": payer, "event_time": base, "country": "US"})
        yield payer, merchant, base
    finally:
        cursor.execute("DELETE FROM transactions WHERE nameOrig LIKE %s OR nameDest LIKE %s", (f"{PREFIX}%", f"{PREFIX}%"))
        cursor.execute("DELETE FROM account_profiles WHERE account_id = %s", (payer,))
        conn.commit()
        cursor.close()
        conn.close()


def insert_payment(cursor, payer, merchant, event_time, amount, country="US"):
    cursor.execute(
        """
        INSERT INTO transactions (step, type, amount, nameOrig, nameDest, event_time, country, scenario)
        VALUES (0, 'PAYMENT', %s, %s, %s, %s, %s, 'simulated')
        """,
        (amount, payer, merchant, event_time, country),
    )
    return cursor.lastrowid


def evaluate_scenario(payer, merchant, event_time, amount, country="US"):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        txn_id = insert_payment(cursor, payer, merchant, event_time, amount, country)
        conn.commit()
    finally:
        cursor.close()
        conn.close()
    return RiskOrchestrator().process({
        "txn_id": txn_id, "type": "PAYMENT", "amount": amount,
        "nameOrig": payer, "nameDest": merchant, "event_time": event_time,
        "country": country, "shipping_country": country,
    })


def test_payment_scenarios_and_print_table(payment_scenarios, capsys):
    payer, merchant, base = payment_scenarios
    normal = evaluate_scenario(payer, merchant, base, 50)
    night = evaluate_scenario(payer, merchant, base.replace(hour=2, minute=30) + timedelta(days=1), 500)
    foreign = evaluate_scenario(payer, merchant, base.replace(hour=11) + timedelta(days=2), 500, "GB")
    burst = None
    for index in range(6):
        burst = evaluate_scenario(payer, merchant, base.replace(hour=12) + timedelta(minutes=index), 50)

    assert normal["action"] == "ALLOW"
    assert night["scores"]["time"] >= 70
    assert foreign["action"] in {"REQUEST_2FA", "HOLD_FOR_REVIEW"}
    assert burst["scores"]["frequency"] > normal["scores"]["frequency"]

    print("| scenario | scores | action |")
    print("|---|---|---|")
    for name, result in (("daytime $50", normal), ("2:30 AM $500", night), ("foreign $500", foreign), ("6 payments / 5 min", burst)):
        print(f"| {name} | {result['scores']} | {result['action']} |")