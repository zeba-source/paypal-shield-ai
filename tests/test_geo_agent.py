from datetime import datetime, timedelta

import pytest

from agents.geo_agent import GeoAgent
from db import get_connection


PREFIX = "TEST_GEO_"


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


def transaction(account, event_time, city, country, lat, lon):
    return {
        "nameOrig": account,
        "event_time": event_time,
        "city": city,
        "country": country,
        "lat": lat,
        "lon": lon,
    }


def test_nagpur_to_london_scores_high(clean_profiles):
    agent = GeoAgent()
    account = f"{PREFIX}TRAVELER"
    first = transaction(account, datetime(2026, 1, 1, 12, 0), "Nagpur", "India", 21.1458, 79.0882)
    agent.update_profile(first)

    result = agent.evaluate(
        transaction(account, first["event_time"] + timedelta(minutes=30), "London", "UK", 51.5074, -0.1278)
    )

    assert result["score"] >= 80
    assert any("Nagpur" in reason and "London" in reason for reason in result["reasons"])
    assert result["features"]["implied_speed_kmh"] > 900


def test_same_city_scores_low(clean_profiles):
    agent = GeoAgent()
    account = f"{PREFIX}LOCAL"
    first = transaction(account, datetime(2026, 1, 1, 12, 0), "Nagpur", "India", 21.1458, 79.0882)
    agent.update_profile(first)

    result = agent.evaluate(
        transaction(account, first["event_time"] + timedelta(minutes=30), "Nagpur", "India", 21.1458, 79.0882)
    )

    assert result["score"] < 15


def test_cold_start_has_no_previous_location(clean_profiles):
    result = GeoAgent().evaluate(
        transaction(f"{PREFIX}COLD", datetime(2026, 1, 1, 12, 0), "London", "UK", 51.5074, -0.1278)
    )

    assert result["score"] == 0
    assert result["reasons"] == ["no previous location"]