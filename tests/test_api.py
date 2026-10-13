from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from api.main import app
from db import get_connection


PREFIX = "API_TEST_"


def insert_transaction(cursor, account_id, txn_type="PAYMENT"):
    cursor.execute(
        """
        INSERT INTO transactions (
            step, type, amount, nameOrig, oldbalanceOrg, newbalanceOrig,
            nameDest, oldbalanceDest, newbalanceDest, isFraud, isFlaggedFraud,
            event_time, lat, lon, country, city
        ) VALUES (1, %s, 100, %s, 1000, 900, %s, 0, 0, 0, 0, %s, 19.076, 72.8777, 'India', 'Mumbai')
        """,
        (txn_type, account_id, f"{PREFIX}DEST", datetime.now(UTC).replace(tzinfo=None)),
    )
    return cursor.lastrowid


@pytest.fixture
def api_client():
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM transactions WHERE nameOrig LIKE %s", (f"{PREFIX}%",))
        cursor.execute("DELETE FROM verification_requests WHERE account_id LIKE %s", (f"{PREFIX}%",))
        cursor.execute("DELETE FROM risk_alerts WHERE account_id LIKE %s", (f"{PREFIX}%",))
        cursor.execute(
            "DELETE FROM review_log WHERE txn_id NOT IN (SELECT txn_id FROM transactions)"
        )
        conn.commit()
    finally:
        cursor.close()
        conn.close()
    with TestClient(app) as client:
        yield client
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM transactions WHERE nameOrig LIKE %s", (f"{PREFIX}%",))
        cursor.execute("DELETE FROM verification_requests WHERE account_id LIKE %s", (f"{PREFIX}%",))
        cursor.execute("DELETE FROM risk_alerts WHERE account_id LIKE %s", (f"{PREFIX}%",))
        cursor.execute("DELETE FROM review_log WHERE txn_id NOT IN (SELECT txn_id FROM transactions)")
        conn.commit()
    finally:
        cursor.close()
        conn.close()


def create_txn(account_id):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        txn_id = insert_transaction(cursor, account_id)
        conn.commit()
        return txn_id
    finally:
        cursor.close()
        conn.close()


def test_correct_otp(api_client):
    txn_id = create_txn(f"{PREFIX}CORRECT")
    response = api_client.post("/2fa/start", json={"txn_id": txn_id, "account_id": f"{PREFIX}CORRECT"})
    assert response.status_code == 200
    otp = api_client.get(f"/dev/otp/{txn_id}").json()["otp"]

    response = api_client.post("/2fa/verify", json={"txn_id": txn_id, "otp": otp})
    assert response.status_code == 200
    assert response.json()["status"] == "PASSED"


def test_wrong_otp_three_times_holds_transaction(api_client):
    txn_id = create_txn(f"{PREFIX}WRONG")
    api_client.post("/2fa/start", json={"txn_id": txn_id, "account_id": f"{PREFIX}WRONG"})

    responses = [
        api_client.post("/2fa/verify", json={"txn_id": txn_id, "otp": "000000"})
        for _ in range(3)
    ]
    assert [response.json()["status"] for response in responses] == ["PENDING", "PENDING", "FAILED"]


def test_expired_otp_is_held(api_client):
    txn_id = create_txn(f"{PREFIX}EXPIRED")
    api_client.post("/2fa/start", json={"txn_id": txn_id, "account_id": f"{PREFIX}EXPIRED"})
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "UPDATE verification_requests SET expires_at = %s WHERE txn_id = %s",
            (datetime.now(UTC).replace(tzinfo=None) - timedelta(minutes=1), txn_id),
        )
        conn.commit()
    finally:
        cursor.close()
        conn.close()

    response = api_client.post("/2fa/verify", json={"txn_id": txn_id, "otp": "000000"})
    assert response.status_code == 200
    assert response.json()["status"] == "EXPIRED"


def test_review_updates_status_and_log(api_client):
    account_id = f"{PREFIX}REVIEW"
    txn_id = create_txn(account_id)
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO risk_alerts (txn_id, account_id, final_score, action, reasons) VALUES (%s, %s, 80, 'HOLD_FOR_REVIEW', '[]')",
            (txn_id, account_id),
        )
        conn.commit()
    finally:
        cursor.close()
        conn.close()

    response = api_client.post(
        f"/review/{txn_id}",
        json={"decision": "APPROVE", "analyst": "alice"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "APPROVED"

    response = api_client.get("/stats")
    assert response.status_code == 200
    assert "counts_by_action" in response.json()