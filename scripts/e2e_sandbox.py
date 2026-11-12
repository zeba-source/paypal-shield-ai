import argparse
import os
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from api.paypal_client import PayPalClient, PayPalError
from config import API_URL, load_dotenv
from db import record_txn_event
from paypal_db import set_status
from scripts.seed_demo_profiles import seed


class SandboxE2E:
    def __init__(self, api_url: str):
        self.api_url = api_url.rstrip("/")
        self.http = httpx.Client(timeout=30.0)
        self.paypal = PayPalClient()

    def close(self):
        self.http.close()

    def api(self, method: str, path: str, **kwargs):
        response = self.http.request(method, f"{self.api_url}{path}", **kwargs)
        response.raise_for_status()
        return response.json()

    def create_and_approve(self, amount: float, description: str, demo: dict | None = None):
        payload = {"amount": amount, "description": description}
        if demo:
            payload["demo"] = demo
        created = self.api("POST", "/checkout/create-order", json=payload)
        order_id = created["order_id"]
        order = self.paypal.get_order(order_id)
        approval = next(link["href"] for link in order.get("links", []) if link.get("rel") == "approve")
        print(f"Approve {description} in the PayPal Sandbox buyer account: {approval}")
        input("After approval, press Enter to continue...")
        return order_id, self.api("POST", "/checkout/authorize", json={"order_id": order_id})

    def status(self, order_id: str):
        return self.api("GET", f"/checkout/{order_id}/status")

    def wait_for_status(self, order_id: str, expected: str, attempts: int = 8):
        for _ in range(attempts):
            status = self.status(order_id)
            if status.get("payment_status") == expected:
                return status
        raise AssertionError(f"Expected {expected}, got {status.get('payment_status')}")


def run_case(name, action):
    try:
        action()
        return name, "PASS", ""
    except Exception as exc:
        return name, "FAIL", str(exc).replace("\n", " ")[:120]


def main() -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Run interactive PayPal Sandbox checkout scenarios.")
    parser.add_argument("--api-url", default=API_URL)
    args = parser.parse_args()
    runner = SandboxE2E(args.api_url)
    results = []
    try:
        def normal():
            order_id, response = runner.create_and_approve(50, "Sandbox normal payment")
            if response["payment_status"] != "CAPTURED":
                raise AssertionError(f"normal payment returned {response['payment_status']}")
            payer_id = runner.status(order_id).get("payer_id")
            if not payer_id:
                raise AssertionError("Sandbox order returned no payer id for profile seeding")
            seed(payer_id, os.getenv("DEMO_HOME_COUNTRY", "US").upper(), reset=True)

        def high_risk_verified():
            order_id, response = runner.create_and_approve(
                60,
                "Sandbox high-risk verified payment",
                {"country": "GB", "amount_multiplier": 10},
            )
            if response["payment_status"] != "PENDING_2FA":
                raise AssertionError(f"high-risk payment returned {response['payment_status']}")
            otp = runner.api("GET", f"/dev/otp/{response['txn_id']}")["otp"]
            runner.api("POST", "/2fa/verify", json={"txn_id": response["txn_id"], "otp": otp})
            runner.wait_for_status(order_id, "CAPTURED")

        def wrong_otp_then_block():
            order_id, response = runner.create_and_approve(
                60,
                "Sandbox wrong-OTP review payment",
                {"country": "GB", "amount_multiplier": 10},
            )
            if response["payment_status"] != "PENDING_2FA":
                raise AssertionError(f"wrong-OTP payment returned {response['payment_status']}")
            for _ in range(3):
                runner.api("POST", "/2fa/verify", json={"txn_id": response["txn_id"], "otp": "000000"})
            runner.wait_for_status(order_id, "PENDING_REVIEW")
            runner.api("POST", f"/review/{response['txn_id']}", json={"decision": "BLOCK", "analyst": "sandbox-e2e"})
            runner.wait_for_status(order_id, "VOIDED")

        def declined_capture():
            order_id, response = runner.create_and_approve(
                60,
                "Sandbox mocked decline",
                {"country": "GB", "amount_multiplier": 10},
            )
            if response["payment_status"] != "PENDING_2FA":
                raise AssertionError(f"decline setup returned {response['payment_status']}")
            status = runner.status(order_id)
            try:
                runner.paypal.capture_authorization(
                    status["authorization_id"],
                    request_id=f"sandbox-e2e-decline-{status['txn_id']}",
                    mock_response="INSTRUMENT_DECLINED",
                )
            except PayPalError as exc:
                set_status(order_id, "FAILED")
                record_txn_event(status["txn_id"], "PAYPAL_CAPTURE_FAILED", {"issue": exc.issue, "source": "sandbox-e2e"})
            else:
                raise AssertionError("PayPal mock decline did not fail")
            runner.wait_for_status(order_id, "FAILED")

        results.append(run_case("normal payment -> CAPTURED", normal))
        results.append(run_case("high-risk + correct OTP -> CAPTURED", high_risk_verified))
        results.append(run_case("wrong OTP x3 -> review BLOCK -> VOIDED", wrong_otp_then_block))
        results.append(run_case("mock INSTRUMENT_DECLINED -> FAILED", declined_capture))
    finally:
        runner.close()

    print("\n| scenario | result | detail |")
    print("|---|---|---|")
    for name, result, detail in results:
        print(f"| {name} | {result} | {detail or '-'} |")
    return 0 if all(result == "PASS" for _, result, _ in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
