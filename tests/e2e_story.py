"""End-to-end checks for the dashboard story and demo journeys.

Run with the API, Kafka, and risk_consumer already started:
    ..\\.venv\\Scripts\\python.exe tests\\e2e_story.py
"""

from __future__ import annotations

import sys
import time
from typing import Any

import requests

API = "http://localhost:8000"
SCENARIOS = ("mule", "night", "travel")


def request(method: str, path: str, **kwargs: Any) -> requests.Response:
    response = requests.request(method, f"{API}{path}", timeout=8, **kwargs)
    response.raise_for_status()
    return response


def wait_for_case(txn_id: int, required: set[str], timeout: float = 25) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    latest: dict[str, Any] = {}
    while time.monotonic() < deadline:
        response = requests.get(f"{API}/story/case/{txn_id}", timeout=8)
        if response.status_code == 200:
            latest = response.json()
            stages = {event["stage"] for event in latest.get("events", [])}
            if required.issubset(stages):
                return latest
        time.sleep(0.25)
    raise AssertionError(f"txn {txn_id} did not reach {sorted(required)}; got {latest.get('events', [])}")


def publish(name: str) -> tuple[list[int], dict[str, Any]]:
    request("POST", "/demo/reset-demo-accounts")
    result = request("POST", f"/demo/scenario/{name}").json()
    txn_ids = result["txn_ids"]
    assert txn_ids, f"{name} returned no transaction IDs"
    case = wait_for_case(txn_ids[-1], {"RECEIVED", "AGENTS_SCORED", "POLICY_DECISION"})
    print(f"{name}: {len(txn_ids)} published, txn {txn_ids[-1]} stages={[event['stage'] for event in case['events']]}")
    return txn_ids, case


def verify_2fa_branch(name: str, wrong: bool) -> int:
    request("POST", "/demo/reset-demo-accounts")
    result = request("POST", f"/demo/scenario/{name}").json()
    txn_id = result["txn_ids"][-1]
    case = wait_for_case(txn_id, {"POLICY_DECISION", "2FA_SENT"})
    action = case["policy"].get("action")
    assert action == "REQUEST_2FA", f"{name} expected REQUEST_2FA, got {action}"
    otp = request("GET", f"/dev/otp/{txn_id}").json()["otp"]
    if wrong:
        for attempt in range(3):
            response = requests.post(f"{API}/2fa/verify", json={"txn_id": txn_id, "otp": "000000" if otp != "000000" else "999999"}, timeout=8)
            response.raise_for_status()
        case = wait_for_case(txn_id, {"2FA_FAILED", "HELD"})
        assert case["outcome"] == "HOLD_FOR_REVIEW", case
        print(f"2FA failure: txn {txn_id} reached HELD after three wrong codes")
    else:
        response = request("POST", "/2fa/verify", json={"txn_id": txn_id, "otp": otp})
        assert response.json()["status"] == "PASSED"
        case = wait_for_case(txn_id, {"2FA_VERIFIED", "APPROVED"})
        assert case["outcome"] == "ALLOW", case
        print(f"2FA success: txn {txn_id} reached APPROVED with the dev OTP")
    return txn_id


def main() -> int:
    results = {name: publish(name) for name in SCENARIOS}
    two_fa_name = next((name for name, (_, case) in results.items() if case["policy"].get("action") == "REQUEST_2FA"), None)
    if two_fa_name is None:
        raise AssertionError("No deterministic demo scenario requested 2FA")
    verify_2fa_branch(two_fa_name, wrong=True)
    verify_2fa_branch(two_fa_name, wrong=False)
    print("E2E story checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
