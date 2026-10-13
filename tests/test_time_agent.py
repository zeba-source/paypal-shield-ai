from datetime import datetime, timedelta

import pytest

from agents.time_agent import TimeAgent
from db import get_connection


PREFIX = "TEST_TIME_"


@pytest.fixture
def clean_profiles():
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM account_profiles WHERE account_id LIKE %s", (f"{PREFIX}%",))
        conn.commit()
        yield
    finally:
        cursor.execute("DELETE FROM account_profiles WHERE account_id LIKE %s", (f"{PREFIX}%",))
        conn.commit()
        cursor.close()
        conn.close()


def test_night_high_amount_scores_high_after_daytime_history(clean_profiles):
    agent = TimeAgent()
    account = f"{PREFIX}ACCOUNT"
    base = datetime(2026, 1, 1, 10, 0)

    for index in range(50):
        agent.update_profile(
            {
                "nameOrig": account,
                "event_time": base - timedelta(days=index),
                "amount": 100,
            }
        )

    result = agent.evaluate(
        {
            "txn_id": 999001,
            "nameOrig": account,
            "event_time": datetime(2026, 2, 1, 2, 14),
            "amount": 620,
        }
    )

    assert result["score"] >= 70
    assert any("02:14" in reason for reason in result["reasons"])
    assert result["features"]["txn_count"] == 50


def test_normal_daytime_transaction_scores_low(clean_profiles):
    agent = TimeAgent()
    account = f"{PREFIX}NORMAL"
    base = datetime(2026, 1, 1, 10, 0)

    for index in range(50):
        agent.update_profile(
            {
                "nameOrig": account,
                "event_time": base - timedelta(days=index),
                "amount": 100,
            }
        )

    result = agent.evaluate(
        {
            "txn_id": 999002,
            "nameOrig": account,
            "event_time": datetime(2026, 2, 1, 10, 30),
            "amount": 100,
        }
    )

    assert result["score"] < 20


def test_cold_start_uses_default_pattern_and_caps_score(clean_profiles):
    result = TimeAgent().evaluate(
        {
            "txn_id": 999003,
            "nameOrig": f"{PREFIX}COLD",
            "event_time": datetime(2026, 2, 1, 2, 0),
            "amount": 1000,
        }
    )

    assert result["score"] <= 60
    assert result["features"]["cold_start"] is True