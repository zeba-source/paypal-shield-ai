import json
import math
from collections import Counter
from datetime import datetime

from db import get_connection


class GeoAgent:
    """Score geographic movement against an account's stored location profile."""

    EARTH_RADIUS_KM = 6371.0
    IMPOSSIBLE_SPEED_KMH = 900.0
    FOREIGN_COUNTRY_SCORE = 30
    FAR_FROM_HOME_SCORE = 15
    IMPOSSIBLE_TRAVEL_SCORE = 60
    TRUSTED_LOCATION_REDUCTION = 15
    HOME_DISTANCE_KM = 500.0
    MAX_TRUSTED_LOCATIONS = 5

    def __init__(self, table_prefix=""):
        self.profiles_table = f"{table_prefix}account_profiles"

    def evaluate(self, txn: dict) -> dict:
        account_id = txn.get("nameOrig")
        current = self._location(txn)
        event_time = self._event_time(txn.get("event_time"))
        if not account_id or current["lat"] is None or current["lon"] is None or event_time is None:
            return self._result(0, ["no previous location"], {})

        profile = self._load_profile(account_id)
        if not profile or profile.get("last_lat") is None or profile.get("last_lon") is None:
            return self._result(0, ["no previous location"], {
                "account_id": account_id,
                "current_city": current["city"],
                "current_country": current["country"],
            })

        previous = (self._number(profile["last_lat"]), self._number(profile["last_lon"]))
        distance = self._haversine(previous[0], previous[1], current["lat"], current["lon"])
        last_time = self._event_time(profile.get("last_txn_time"))
        elapsed_hours = (event_time - last_time).total_seconds() / 3600 if last_time else None
        implied_speed = distance / elapsed_hours if elapsed_hours and elapsed_hours > 0 else None
        home_distance = self._haversine(
            self._number(profile.get("home_lat")),
            self._number(profile.get("home_lon")),
            current["lat"],
            current["lon"],
        ) if profile.get("home_lat") is not None and profile.get("home_lon") is not None else 0.0
        trusted = self._trusted_locations(profile.get("trusted_locations"))
        score = 0
        reasons = []

        if implied_speed is not None and implied_speed > self.IMPOSSIBLE_SPEED_KMH:
            score += self.IMPOSSIBLE_TRAVEL_SCORE
            reasons.append(
                f"{profile.get('last_city') or 'Previous location'} -> {current['city'] or 'current location'} "
                f"in {self._format_minutes(elapsed_hours * 60)} (implied {implied_speed:,.0f} km/h)"
            )
        if profile.get("home_country") and current["country"] and current["country"] != profile["home_country"]:
            score += self.FOREIGN_COUNTRY_SCORE
            reasons.append(f"Current country {current['country']} differs from home country {profile['home_country']}")
        if home_distance > self.HOME_DISTANCE_KM:
            score += self.FAR_FROM_HOME_SCORE
            reasons.append(f"Current city is {home_distance:,.0f} km from the account home location")
        if current["city"] and current["city"] in trusted:
            score = max(0, score - self.TRUSTED_LOCATION_REDUCTION)
            reasons.append(f"Current city {current['city']} is a trusted location")
        if not reasons:
            reasons.append("Location is consistent with the account profile")

        features = {
            "account_id": account_id,
            "distance_km": distance,
            "implied_speed_kmh": implied_speed,
            "elapsed_hours": elapsed_hours,
            "home_distance_km": home_distance,
            "trusted_location": current["city"] in trusted if current["city"] else False,
            "last_city": profile.get("last_city"),
            "current_city": current["city"],
            "home_country": profile.get("home_country"),
            "current_country": current["country"],
        }
        return self._result(min(score, 100), reasons, features)

    def update_profile(self, txn: dict):
        account_id = txn.get("nameOrig")
        event_time = self._event_time(txn.get("event_time"))
        current = self._location(txn)
        if not account_id or event_time is None or current["lat"] is None or current["lon"] is None:
            return None

        conn = get_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                f"SELECT * FROM {self.profiles_table} WHERE account_id = %s FOR UPDATE",
                (account_id,),
            )
            profile = cursor.fetchone()
            locations = self._trusted_locations(profile.get("trusted_locations") if profile else None)
            if current["city"]:
                locations.append(current["city"])
            trusted = [city for city, _ in Counter(locations).most_common(self.MAX_TRUSTED_LOCATIONS)]
            home = profile or {}
            home_city = home.get("home_city") or current["city"]
            home_country = home.get("home_country") or current["country"]
            home_lat = home.get("home_lat") if home.get("home_lat") is not None else current["lat"]
            home_lon = home.get("home_lon") if home.get("home_lon") is not None else current["lon"]
            cursor.execute(
                f"""
                INSERT INTO {self.profiles_table} (
                    account_id, home_city, home_country, home_lat, home_lon,
                    trusted_locations, last_txn_time, last_lat, last_lon, last_city
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    home_city = VALUES(home_city),
                    home_country = VALUES(home_country),
                    home_lat = VALUES(home_lat),
                    home_lon = VALUES(home_lon),
                    trusted_locations = VALUES(trusted_locations),
                    last_txn_time = VALUES(last_txn_time),
                    last_lat = VALUES(last_lat),
                    last_lon = VALUES(last_lon),
                    last_city = VALUES(last_city)
                """,
                (
                    account_id, home_city, home_country, home_lat, home_lon,
                    json.dumps(trusted), event_time, current["lat"], current["lon"], current["city"],
                ),
            )
            conn.commit()
            return {
                "account_id": account_id,
                "home_city": home_city,
                "home_country": home_country,
                "trusted_locations": trusted,
                "last_txn_time": event_time,
                "last_lat": current["lat"],
                "last_lon": current["lon"],
                "last_city": current["city"],
            }
        finally:
            cursor.close()
            conn.close()

    def _load_profile(self, account_id):
        conn = get_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(f"SELECT * FROM {self.profiles_table} WHERE account_id = %s", (account_id,))
            return cursor.fetchone()
        finally:
            cursor.close()
            conn.close()

    @staticmethod
    def _location(txn):
        return {
            "lat": GeoAgent._optional_number(txn.get("lat")),
            "lon": GeoAgent._optional_number(txn.get("lon")),
            "city": txn.get("city"),
            "country": txn.get("country"),
        }

    @staticmethod
    def _trusted_locations(value):
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except json.JSONDecodeError:
                return []
        return [str(item) for item in value] if isinstance(value, list) else []

    @staticmethod
    def _haversine(lat1, lon1, lat2, lon2):
        lat1, lon1, lat2, lon2 = map(math.radians, (lat1, lon1, lat2, lon2))
        delta_lat = lat2 - lat1
        delta_lon = lon2 - lon1
        value = math.sin(delta_lat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lon / 2) ** 2
        return 6371.0 * 2 * math.atan2(math.sqrt(value), math.sqrt(1 - value))

    @staticmethod
    def _format_minutes(minutes):
        return f"{minutes:.0f} min" if minutes < 120 else f"{minutes / 60:.1f} h"

    @staticmethod
    def _optional_number(value):
        if value in (None, ""):
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _number(value):
        try:
            return float(value or 0)
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _event_time(value):
        if isinstance(value, datetime):
            return value
        if not value:
            return None
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
        except ValueError:
            return None

    @staticmethod
    def _result(score, reasons, features):
        return {"agent": "geo", "score": int(score), "reasons": reasons, "features": features}