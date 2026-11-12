import json
from datetime import datetime

from db import get_connection


class TimeAgent:
    """Score transaction timing against the sender account's observed profile."""

    ACTIVE_START = 7
    ACTIVE_END = 22
    NIGHT_END = 5
    RARE_PROBABILITY = 0.02
    NIGHT_HISTORY_LIMIT = 0.05
    MIN_PROFILE_TRANSACTIONS = 10

    def __init__(self, table_prefix=""):
        self.profiles_table = f"{table_prefix}account_profiles"

    def evaluate(self, txn: dict) -> dict:
        account_id = txn.get("payer_id") or txn.get("nameOrig")
        event_time = self._event_time(txn.get("event_time"))
        if not account_id or event_time is None:
            return self._result(0, ["insufficient history"], {})

        profile = self._load_profile(account_id)
        txn_count = int(profile.get("txn_count") or 0) if profile else 0
        histogram = self._histogram(profile.get("hour_histogram") if profile else None)
        amount = self._number(txn.get("amount"))
        is_payment = txn.get("type") == "PAYMENT"
        average_amount = self._number(profile.get("avg_amount")) if profile else 0.0
        hour = event_time.hour
        total = sum(histogram)
        hour_probability = histogram[hour] / total if total else 0.0
        night_count = sum(histogram[: self.NIGHT_END + 1])
        night_ratio = night_count / total if total else 0.0
        is_night = hour <= self.NIGHT_END
        first_night = is_night and night_count == 0
        amount_multiple = amount / average_amount if average_amount else 0.0
        cold_start = txn_count < self.MIN_PROFILE_TRANSACTIONS

        score = 0
        reasons = []
        if hour_probability < self.RARE_PROBABILITY:
            score += 40
            reasons.append(f"Transaction hour {hour:02d}:00 is rare for this account")
        if is_night and night_ratio < self.NIGHT_HISTORY_LIMIT:
            score += 25
            reasons.append(f"Transaction at {event_time:%H:%M} is in the account's low-activity night window")
        if amount_multiple > 3:
            score += 25
            reasons.append(f"Amount is {amount_multiple:.1f}x the account's average amount")
        if first_night:
            score += 10
            reasons.append("First-ever night transaction for this account")

        active_percent = self._active_percent(histogram)
        if is_night and average_amount and amount_multiple > 3:
            reasons.insert(
                0,
                f"Account active {active_percent:.0%} in {self.ACTIVE_START:02d}:00-"
                f"{self.ACTIVE_END:02d}:00; this txn at {event_time:%H:%M} with "
                f"{amount_multiple:.1f}x average amount",
            )
        if not reasons:
            reasons.append("Transaction timing and amount are consistent with the account profile")

        if cold_start:
            score = min(score, 60)
            reasons.append("Cold-start account: limited timing history")
        elif is_payment and is_night and amount_multiple > 3:
            reasons.append("Payment is outside the payer's established daytime order pattern")

        features = {
            "account_id": account_id,
            "hour": hour,
            "hour_probability": hour_probability,
            "night_history_ratio": night_ratio,
            "amount_multiple": amount_multiple,
            "avg_amount": average_amount,
            "txn_count": txn_count,
            "first_night_transaction": first_night,
            "cold_start": cold_start,
            "hour_histogram": histogram,
        }
        return self._result(min(score, 100), reasons, features)

    def update_profile(self, txn: dict):
        account_id = txn.get("payer_id") or txn.get("nameOrig")
        event_time = self._event_time(txn.get("event_time"))
        if not account_id or event_time is None:
            return None

        amount = self._number(txn.get("amount"))
        conn = get_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                f"SELECT hour_histogram, avg_amount, txn_count FROM {self.profiles_table} WHERE account_id = %s FOR UPDATE",
                (account_id,),
            )
            profile = cursor.fetchone()
            histogram = self._histogram(profile.get("hour_histogram") if profile else None)
            txn_count = int(profile.get("txn_count") or 0) if profile else 0
            average = self._number(profile.get("avg_amount")) if profile else 0.0
            histogram[event_time.hour] += 1
            new_count = txn_count + 1
            new_average = ((average * txn_count) + amount) / new_count
            cursor.execute(
                f"""
                INSERT INTO {self.profiles_table} (
                    account_id, hour_histogram, avg_amount, txn_count, last_txn_time
                ) VALUES (%s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    hour_histogram = VALUES(hour_histogram),
                    avg_amount = VALUES(avg_amount),
                    txn_count = VALUES(txn_count),
                    last_txn_time = VALUES(last_txn_time)
                """,
                (account_id, json.dumps(histogram), new_average, new_count, event_time),
            )
            conn.commit()
            return {
                "account_id": account_id,
                "hour_histogram": histogram,
                "avg_amount": new_average,
                "txn_count": new_count,
                "last_txn_time": event_time,
            }
        finally:
            cursor.close()
            conn.close()

    def _load_profile(self, account_id):
        conn = get_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                f"SELECT hour_histogram, avg_amount, txn_count FROM {self.profiles_table} WHERE account_id = %s",
                (account_id,),
            )
            return cursor.fetchone()
        finally:
            cursor.close()
            conn.close()

    def _histogram(self, value):
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except json.JSONDecodeError:
                value = None
        if isinstance(value, list) and len(value) == 24:
            return [self._number(item) for item in value]
        return [1.0 if self.ACTIVE_START <= hour < self.ACTIVE_END else 0.0 for hour in range(24)]

    def _active_percent(self, histogram):
        total = sum(histogram)
        if not total:
            return 0.0
        return sum(histogram[self.ACTIVE_START:self.ACTIVE_END]) / total

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
        return {"agent": "time", "score": int(score), "reasons": reasons, "features": features}