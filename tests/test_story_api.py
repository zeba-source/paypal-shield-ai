from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from api.main import app
from db import get_connection
from orchestrator import RiskOrchestrator


PREFIX = "STORY_TEST_"


@pytest.fixture
def story_case():
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM txn_events WHERE txn_id IN (SELECT txn_id FROM transactions WHERE nameOrig LIKE %s)", (f"{PREFIX}%",))
        cursor.execute("DELETE FROM risk_alerts WHERE account_id LIKE %s", (f"{PREFIX}%",))
        cursor.execute("DELETE FROM txn_status WHERE txn_id IN (SELECT txn_id FROM transactions WHERE nameOrig LIKE %s)", (f"{PREFIX}%",))
        cursor.execute("DELETE FROM transactions WHERE nameOrig LIKE %s", (f"{PREFIX}%",))
        cursor.execute("DELETE FROM account_profiles WHERE account_id LIKE %s", (f"{PREFIX}%",))
        cursor.execute(
            """
            INSERT INTO transactions (
                step, type, amount, nameOrig, oldbalanceOrg, newbalanceOrig,
                nameDest, oldbalanceDest, newbalanceDest, isFraud, isFlaggedFraud,
                event_time, lat, lon, country, city, scenario
            ) VALUES (1, 'PAYMENT', 100, %s, 1000, 900, %s, 0, 0, 0, 0, %s, 19.076, 72.8777, 'India', 'Mumbai', 'story-test')
            """,
            (f"{PREFIX}ACCOUNT", f"{PREFIX}DEST", datetime(2026, 6, 1, 12, 0)),
        )
        txn_id = cursor.lastrowid
        conn.commit()
        txn = {
            "txn_id": txn_id, "type": "PAYMENT", "amount": 100,
            "nameOrig": f"{PREFIX}ACCOUNT", "nameDest": f"{PREFIX}DEST",
            "event_time": datetime(2026, 6, 1, 12, 0), "lat": 19.076,
            "lon": 72.8777, "country": "India", "city": "Mumbai",
            "oldbalanceOrg": 1000, "newbalanceOrig": 900,
        }
        RiskOrchestrator().process(txn)
        yield txn_id
    finally:
        cursor.execute("DELETE FROM txn_events WHERE txn_id IN (SELECT txn_id FROM transactions WHERE nameOrig LIKE %s)", (f"{PREFIX}%",))
        cursor.execute("DELETE FROM risk_alerts WHERE account_id LIKE %s", (f"{PREFIX}%",))
        cursor.execute("DELETE FROM txn_status WHERE txn_id IN (SELECT txn_id FROM transactions WHERE nameOrig LIKE %s)", (f"{PREFIX}%",))
        cursor.execute("DELETE FROM transactions WHERE nameOrig LIKE %s", (f"{PREFIX}%",))
        cursor.execute("DELETE FROM account_profiles WHERE account_id LIKE %s", (f"{PREFIX}%",))
        conn.commit()
        cursor.close()
        conn.close()


def test_story_case_has_ordered_events_and_funnel(story_case):
    with TestClient(app) as client:
        case = client.get(f"/story/case/{story_case}")
        assert case.status_code == 200
        stages = [event["stage"] for event in case.json()["events"]]
        assert stages[:3] == ["AGENTS_SCORED", "POLICY_DECISION", "APPROVED"] or stages[:3] == ["RECEIVED", "AGENTS_SCORED", "POLICY_DECISION"]
        assert "AGENTS_SCORED" in stages
        assert "POLICY_DECISION" in stages
        funnel = client.get("/story/actions")
        assert funnel.status_code == 200
        data = funnel.json()["funnel"]
        assert data["total"] >= data["flagged"]
        assert data["final_approved"] + data["final_held"] + data["final_blocked"] <= data["total"]
