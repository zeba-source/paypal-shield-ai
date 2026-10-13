from datetime import datetime, timedelta

import pytest

from agents.frequency_agent import FrequencyAgent
from db import get_connection


PREFIX = "TEST_FREQ_"


def insert_transaction(cursor, event_time, sender, receiver, amount, **balances):
    cursor.execute(
        """
        INSERT INTO transactions (
            step, type, amount, nameOrig, oldbalanceOrg, newbalanceOrig,
            nameDest, oldbalanceDest, newbalanceDest, isFraud, isFlaggedFraud,
            event_time, lat, lon, country, city
        ) VALUES (%s, 'TRANSFER', %s, %s, %s, %s, %s, 0, 0, 0, 0, %s, 0, 0, 'Test', 'Test')
        """,
        (
            1,
            amount,
            sender,
            balances.get("oldbalance", 1000),
            balances.get("newbalance", 1000),
            receiver,
            event_time,
        ),
    )
    return cursor.lastrowid


@pytest.fixture
def database_rows():
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "DELETE FROM transactions WHERE nameOrig LIKE %s OR nameDest LIKE %s",
            (f"{PREFIX}%", f"{PREFIX}%"),
        )
        conn.commit()
        yield conn, cursor
    finally:
        cursor.execute(
            "DELETE FROM transactions WHERE nameOrig LIKE %s OR nameDest LIKE %s",
            (f"{PREFIX}%", f"{PREFIX}%"),
        )
        conn.commit()
        cursor.close()
        conn.close()


def test_simulated_mule_chain_scores_high(database_rows):
    conn, cursor = database_rows
    base = datetime(2026, 1, 1, 12, 0)
    mule = f"{PREFIX}MULE"

    for index in range(10):
        insert_transaction(
            cursor,
            base - timedelta(minutes=10 - index),
            f"{PREFIX}SENDER_{index}",
            mule,
            100,
        )
    txn_id = insert_transaction(
        cursor,
        base,
        mule,
        f"{PREFIX}CASHOUT",
        970,
        oldbalance=1000,
        newbalance=5,
    )
    conn.commit()
    cursor.execute(
        "SELECT COUNT(*) FROM transactions WHERE nameDest = %s AND event_time BETWEEN %s AND %s",
        (mule, base - timedelta(hours=24), base),
    )
    assert cursor.fetchone()[0] == 10

    result = FrequencyAgent().evaluate(
        {
            "txn_id": txn_id,
            "event_time": base,
            "nameOrig": mule,
            "nameDest": f"{PREFIX}CASHOUT",
            "amount": 970,
            "oldbalanceOrg": 1000,
            "newbalanceOrig": 5,
        }
    )

    assert result["score"] >= 70
    assert any("10 different accounts" in reason for reason in result["reasons"])


def test_frequent_normal_account_stays_low(database_rows):
    conn, cursor = database_rows
    base = datetime(2026, 1, 2, 12, 0)
    account = f"{PREFIX}NORMAL"

    for index in range(8):
        insert_transaction(
            cursor,
            base - timedelta(hours=index + 1),
            account,
            f"{PREFIX}MERCHANT_{index}",
            20,
        )
    txn_id = insert_transaction(
        cursor,
        base,
        account,
        f"{PREFIX}MERCHANT_FINAL",
        20,
        oldbalance=1000,
        newbalance=980,
    )
    conn.commit()

    result = FrequencyAgent().evaluate(
        {
            "txn_id": txn_id,
            "event_time": base,
            "nameOrig": account,
            "nameDest": f"{PREFIX}MERCHANT_FINAL",
            "amount": 20,
            "oldbalanceOrg": 1000,
            "newbalanceOrig": 980,
        }
    )

    assert result["score"] < 30


def test_cold_start_is_low(database_rows):
    conn, cursor = database_rows
    base = datetime(2026, 1, 3, 12, 0)
    txn_id = insert_transaction(
        cursor,
        base,
        f"{PREFIX}COLD",
        f"{PREFIX}MERCHANT",
        500,
    )
    conn.commit()

    result = FrequencyAgent().evaluate(
        {
            "txn_id": txn_id,
            "event_time": base,
            "nameOrig": f"{PREFIX}COLD",
            "nameDest": f"{PREFIX}MERCHANT",
            "amount": 500,
        }
    )

    assert result["score"] < 30
    assert result["reasons"] == ["insufficient history"]