import json
from concurrent.futures import ThreadPoolExecutor, TimeoutError

from agents.frequency_agent import FrequencyAgent
from agents.geo_agent import GeoAgent
from agents.time_agent import TimeAgent
from db import get_connection, record_txn_event
from policy import decide


AGENT_TIMEOUT_SECONDS = 0.5
ACTION_STATUS = {
    "ALLOW": "APPROVED",
    "REQUEST_2FA": "PENDING_2FA",
    "HOLD_FOR_REVIEW": "HELD",
    "BLOCK": "BLOCKED",
}


class RiskOrchestrator:
    def __init__(self, table_prefix=""):
        self.table_prefix = table_prefix
        self.agents = {
            "frequency": FrequencyAgent(table_prefix),
            "time": TimeAgent(table_prefix),
            "geo": GeoAgent(table_prefix),
        }

    def process(self, txn: dict) -> dict:
        agent_results = self._evaluate_agents(txn)
        scores = {name: result["score"] for name, result in agent_results.items()}
        record_txn_event(txn["txn_id"], "AGENTS_SCORED", {"scores": scores, "agents": agent_results}, self.table_prefix)
        final_score, action = decide(scores)
        reasons = [
            reason
            for result in agent_results.values()
            for reason in result.get("reasons", [])
        ]
        decision = {
            "txn_id": txn.get("txn_id"),
            "account_id": txn.get("nameOrig"),
            "scores": scores,
            "agents": agent_results,
            "final_score": final_score,
            "action": action,
            "reasons": reasons,
        }
        record_txn_event(txn["txn_id"], "POLICY_DECISION", {"final_score": final_score, "action": action, "scores": scores}, self.table_prefix)
        self._persist_decision(decision)
        if action != "REQUEST_2FA":
            record_txn_event(txn["txn_id"], {"APPROVED": "APPROVED", "HELD": "HELD", "BLOCKED": "BLOCKED"}[ACTION_STATUS[action]], {"action": action, "final_score": final_score}, self.table_prefix)
        self._update_profiles(txn)
        return decision

    def _evaluate_agents(self, txn):
        executor = ThreadPoolExecutor(max_workers=len(self.agents), thread_name_prefix="risk-agent")
        futures = {
            name: executor.submit(agent.evaluate, txn)
            for name, agent in self.agents.items()
        }
        results = {}
        try:
            for name, future in futures.items():
                try:
                    result = future.result(timeout=AGENT_TIMEOUT_SECONDS)
                    results[name] = result if isinstance(result, dict) else self._unavailable()
                except (TimeoutError, Exception):
                    future.cancel()
                    results[name] = self._unavailable()
        finally:
            executor.shutdown(wait=False, cancel_futures=True)
        return results

    @staticmethod
    def _unavailable():
        return {"agent": "unavailable", "score": 0, "reasons": ["agent_unavailable"], "features": {}}

    def _persist_decision(self, decision):
        conn = get_connection()
        try:
            cursor = conn.cursor()
            if decision["action"] != "ALLOW":
                scores = decision["scores"]
                cursor.execute(
                    f"""
                    INSERT INTO {self.table_prefix}risk_alerts (
                        txn_id, account_id, frequency_score, time_score, geo_score,
                        final_score, action, reasons
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        decision["txn_id"], decision["account_id"],
                        scores.get("frequency", 0), scores.get("time", 0),
                        scores.get("geo", 0), decision["final_score"],
                        decision["action"], json.dumps(decision["reasons"]),
                    ),
                )
            cursor.execute(
                f"""
                INSERT INTO {self.table_prefix}txn_status (txn_id, status)
                VALUES (%s, %s)
                ON DUPLICATE KEY UPDATE status = VALUES(status), updated_at = CURRENT_TIMESTAMP
                """,
                (decision["txn_id"], ACTION_STATUS[decision["action"]]),
            )
            conn.commit()
        finally:
            cursor.close()
            conn.close()

    def _update_profiles(self, txn):
        for name in ("time", "geo"):
            try:
                self.agents[name].update_profile(txn)
            except Exception:
                continue