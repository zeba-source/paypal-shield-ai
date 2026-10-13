from datetime import datetime, timedelta

from config import FREQUENCY_THRESHOLDS
from db import get_connection


class FrequencyAgent:
    """Score transaction frequency and pass-through behaviour from MySQL history."""

    def __init__(self, table_prefix=""):
        self.transactions_table = f"{table_prefix}transactions"

    def evaluate(self, txn: dict) -> dict:
        txn_id = txn.get("txn_id")
        event_time = self._event_time(txn.get("event_time"))
        sender = txn.get("nameOrig")
        receiver = txn.get("nameDest")
        amount = self._number(txn.get("amount"))

        if not event_time or not sender or not receiver:
            return self._result(0, ["insufficient history"], {})

        history = self._load_history(txn_id, event_time, sender, receiver)
        features = self._features(history, event_time, sender, receiver, amount, txn)
        if features["history_count"] < FREQUENCY_THRESHOLDS["minimum_history"]:
            return self._result(5, ["insufficient history"], features)

        score = 0
        reasons = []
        if (
            features["incoming_unique_senders_1h"] >= FREQUENCY_THRESHOLDS["mule_unique_senders"]
            and FREQUENCY_THRESHOLDS["pass_through_min"]
            <= features["pass_through_ratio_1h"]
            <= FREQUENCY_THRESHOLDS["pass_through_max"]
            and features["minutes_since_last_credit"] is not None
            and features["minutes_since_last_credit"] <= FREQUENCY_THRESHOLDS["short_window_minutes"]
        ):
            score += 65
            reasons.append(
                f"Received from {features['incoming_unique_senders_1h']} different accounts into "
                f"{sender} and forwarded {features['pass_through_ratio_1h']:.0%} within "
                f"{features['minutes_since_last_credit']:.0f} min"
            )

        if features["balance_drained"]:
            score += 15
            reasons.append("Sender balance was drained to near zero")

        if features["rate_spike"]:
            score += 20
            reasons.append("Transaction rate is a sudden spike versus the account's own average")

        if not reasons:
            reasons.append("Frequent activity without pass-through or mule behaviour")

        return self._result(min(score, 100), reasons, features)

    def _load_history(self, txn_id, event_time, sender, receiver):
        start = event_time - timedelta(hours=24)
        conn = get_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                f"""
                SELECT txn_id, event_time, amount, nameOrig, nameDest
                FROM {self.transactions_table}
                WHERE event_time >= %s
                  AND event_time <= %s
                  AND txn_id <> %s
                                    AND (nameOrig IN (%s, %s) OR nameDest IN (%s, %s))
                ORDER BY event_time
                """,
                                (start, event_time, txn_id or -1, sender, receiver, sender, receiver),
            )
            return cursor.fetchall()
        finally:
            cursor.close()
            conn.close()

    def _features(self, history, event_time, sender, receiver, amount, txn):
        def within(row, minutes):
            return row["event_time"] >= event_time - timedelta(minutes=minutes)

        outgoing = [row for row in history if row["nameOrig"] == sender]
        incoming = [row for row in history if row["nameDest"] == sender]
        receiver_outgoing = [row for row in history if row["nameOrig"] == receiver]
        receiver_incoming = [row for row in history if row["nameDest"] == receiver]
        outgoing_1h = [row for row in outgoing if within(row, 60)]
        incoming_1h = [row for row in incoming if within(row, 60)]
        outgoing_5m = [row for row in outgoing if within(row, 5)]
        incoming_5m = [row for row in incoming if within(row, 5)]
        outgoing_24h = [row for row in outgoing if within(row, 1440)]
        incoming_24h = [row for row in incoming if within(row, 1440)]
        receiver_outgoing_5m = [row for row in receiver_outgoing if within(row, 5)]
        receiver_outgoing_1h = [row for row in receiver_outgoing if within(row, 60)]
        receiver_outgoing_24h = [row for row in receiver_outgoing if within(row, 1440)]
        receiver_incoming_5m = [row for row in receiver_incoming if within(row, 5)]
        receiver_incoming_1h = [row for row in receiver_incoming if within(row, 60)]
        receiver_incoming_24h = [row for row in receiver_incoming if within(row, 1440)]
        incoming_amount = sum(self._number(row["amount"]) for row in incoming_1h)
        outgoing_amount = amount + sum(self._number(row["amount"]) for row in outgoing_1h)
        last_credit = max((row["event_time"] for row in incoming_1h), default=None)
        minutes_since_credit = (
            (event_time - last_credit).total_seconds() / 60 if last_credit else None
        )
        old_balance = self._number(txn.get("oldbalanceOrg"))
        new_balance = self._number(txn.get("newbalanceOrig"))

        return {
            "history_count": len(history),
            "outgoing_count_5m": len(outgoing_5m),
            "outgoing_amount_5m": self._amount(outgoing_5m),
            "outgoing_count_1h": len(outgoing_1h) + 1,
            "outgoing_amount_1h": outgoing_amount,
            "outgoing_count_24h": len(outgoing_24h) + 1,
            "outgoing_amount_24h": outgoing_amount + self._amount([row for row in outgoing_24h if row not in outgoing_1h]),
            "unique_receivers_1h": len({row["nameDest"] for row in outgoing_1h}),
            "incoming_count_5m": len(incoming_5m),
            "incoming_count_1h": len(incoming_1h),
            "incoming_count_24h": len(incoming_24h),
            "incoming_unique_senders_1h": len({row["nameOrig"] for row in incoming_1h}),
            "incoming_unique_senders_24h": len({row["nameOrig"] for row in incoming_24h}),
            "incoming_amount_1h": incoming_amount,
            "pass_through_ratio_1h": outgoing_amount / incoming_amount if incoming_amount else 0.0,
            "minutes_since_last_credit": minutes_since_credit,
            "balance_drained": old_balance > 0 and new_balance / old_balance <= FREQUENCY_THRESHOLDS["drained_balance_ratio"],
            "rate_spike": self._rate_spike(outgoing_24h, len(outgoing_1h) + 1),
            "receiver_outgoing_count_5m": len(receiver_outgoing_5m),
            "receiver_outgoing_count_1h": len(receiver_outgoing_1h),
            "receiver_outgoing_count_24h": len(receiver_outgoing_24h),
            "receiver_outgoing_amount_5m": self._amount(receiver_outgoing_5m),
            "receiver_outgoing_amount_1h": self._amount(receiver_outgoing_1h),
            "receiver_outgoing_amount_24h": self._amount(receiver_outgoing_24h),
            "receiver_unique_receivers_1h": len({row["nameDest"] for row in receiver_outgoing_1h}),
            "receiver_incoming_count_5m": len(receiver_incoming_5m),
            "receiver_incoming_count_1h": len(receiver_incoming_1h),
            "receiver_incoming_count_24h": len(receiver_incoming_24h),
            "receiver_incoming_unique_senders_1h": len({row["nameOrig"] for row in receiver_incoming_1h}),
            "receiver_incoming_unique_senders_24h": len({row["nameOrig"] for row in receiver_incoming_24h}),
        }

    @staticmethod
    def _rate_spike(outgoing_24h, current_hour_count):
        if len(outgoing_24h) < 3:
            return False
        average_hourly = len(outgoing_24h) / 24
        return current_hour_count >= average_hourly * FREQUENCY_THRESHOLDS["spike_multiplier"]

    @staticmethod
    def _amount(rows):
        return sum(FrequencyAgent._number(row["amount"]) for row in rows)

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
        return {"agent": "frequency", "score": int(score), "reasons": reasons, "features": features}