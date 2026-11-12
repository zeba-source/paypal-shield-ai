import json
import logging
import os
import threading
import time
import uuid
from typing import Any

import httpx

from config import load_dotenv


load_dotenv()

LOGGER = logging.getLogger(__name__)
SANDBOX_BASE_URL = "https://api-m.sandbox.paypal.com"


class PayPalError(RuntimeError):
    def __init__(self, status: int, issue: str, debug_id: str | None, message: str):
        self.status = status
        self.issue = issue
        self.debug_id = debug_id
        self.message = message
        super().__init__(message)


class PayPalClient:
    def __init__(self, client: httpx.Client | None = None):
        self.client_id = os.getenv("PAYPAL_CLIENT_ID", "")
        self.client_secret = os.getenv("PAYPAL_CLIENT_SECRET", "")
        self.mode = os.getenv("PAYPAL_MODE", "sandbox").lower()
        if self.mode != "sandbox":
            raise ValueError("Only PAYPAL_MODE=sandbox is supported")
        if not self.client_id or not self.client_secret:
            raise ValueError("PAYPAL_CLIENT_ID and PAYPAL_CLIENT_SECRET are required")
        self.base_url = SANDBOX_BASE_URL
        self.client = client or httpx.Client(timeout=10.0)
        self._token: str | None = None
        self._token_expires_at = 0.0
        self._token_lock = threading.Lock()

    def get_token(self) -> str:
        with self._token_lock:
            if self._token and time.monotonic() < self._token_expires_at:
                return self._token
            response = self.client.post(
                f"{self.base_url}/v1/oauth2/token",
                auth=(self.client_id, self.client_secret),
                data={"grant_type": "client_credentials"},
                headers={"PayPal-Request-Id": str(uuid.uuid4())},
            )
            payload = self._decode_response(response)
            self._token = payload["access_token"]
            self._token_expires_at = time.monotonic() + max(
                0, float(payload.get("expires_in", 0)) - 60
            )
            return self._token

    def create_order(
        self,
        amount: str,
        currency: str = "USD",
        reference_id: str | None = None,
        description: str | None = None,
        request_id: str | None = None,
        mock_response: str | None = None,
    ) -> dict[str, Any]:
        purchase_unit: dict[str, Any] = {
            "amount": {"currency_code": currency, "value": amount}
        }
        if reference_id:
            purchase_unit["reference_id"] = reference_id
        if description:
            purchase_unit["description"] = description
        return self._post(
            "/v2/checkout/orders",
            {"intent": "AUTHORIZE", "purchase_units": [purchase_unit]},
            request_id=request_id,
            mock_response=mock_response,
        )

    def get_order(self, order_id: str) -> dict[str, Any]:
        return self._get(f"/v2/checkout/orders/{order_id}")

    def authorize_order(
        self,
        order_id: str,
        request_id: str | None = None,
        mock_response: str | None = None,
    ) -> dict[str, Any]:
        response = self._post(
            f"/v2/checkout/orders/{order_id}/authorize",
            request_id=request_id,
            mock_response=mock_response,
        )
        authorization = response.get("purchase_units", [{}])[0].get("payments", {}).get(
            "authorizations", [{}]
        )[0]
        return {
            "authorization_id": authorization.get("id"),
            "payer": response.get("payer"),
            "order": response,
        }

    def get_authorization(self, auth_id: str) -> dict[str, Any]:
        return self._get(f"/v2/payments/authorizations/{auth_id}")

    def capture_authorization(
        self,
        auth_id: str,
        final_capture: bool = True,
        request_id: str | None = None,
        mock_response: str | None = None,
    ) -> dict[str, Any]:
        return self._post(
            f"/v2/payments/authorizations/{auth_id}/capture",
            {"final_capture": final_capture},
            request_id=request_id,
            mock_response=mock_response,
        )

    def void_authorization(
        self,
        auth_id: str,
        request_id: str | None = None,
        mock_response: str | None = None,
    ) -> dict[str, Any]:
        return self._post(
            f"/v2/payments/authorizations/{auth_id}/void",
            request_id=request_id,
            mock_response=mock_response,
        )

    def _headers(
        self,
        request_id: str | None = None,
        mock_response: str | None = None,
    ) -> dict[str, str]:
        headers = {"Authorization": f"Bearer {self.get_token()}"}
        headers["PayPal-Request-Id"] = request_id or str(uuid.uuid4())
        if mock_response and self.mode == "sandbox":
            headers["PayPal-Mock-Response"] = json.dumps(
                {"mock_application_codes": mock_response}, separators=(",", ":")
            )
        return headers

    def _get(self, path: str) -> dict[str, Any]:
        return self._request("GET", path)

    def _post(
        self,
        path: str,
        payload: dict[str, Any] | None = None,
        request_id: str | None = None,
        mock_response: str | None = None,
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            path,
            json_payload=payload,
            request_id=request_id,
            mock_response=mock_response,
        )

    def _request(
        self,
        method: str,
        path: str,
        json_payload: dict[str, Any] | None = None,
        request_id: str | None = None,
        mock_response: str | None = None,
    ) -> dict[str, Any]:
        attempts = 3 if method == "GET" else 1
        for attempt in range(attempts):
            try:
                response = self.client.request(
                    method,
                    f"{self.base_url}{path}",
                    headers=self._headers(request_id, mock_response),
                    json=json_payload,
                )
            except httpx.HTTPError:
                if attempt + 1 == attempts:
                    raise
                continue
            if response.status_code >= 500 and attempt + 1 < attempts:
                continue
            return self._decode_response(response)
        raise RuntimeError("PayPal request failed")

    @staticmethod
    def _decode_response(response: httpx.Response) -> dict[str, Any]:
        try:
            payload = response.json()
        except ValueError:
            payload = {}
        if response.is_error:
            details = payload.get("details") or [{}]
            issue = details[0].get("issue") or payload.get("name") or "PAYPAL_ERROR"
            debug_id = payload.get("debug_id")
            if debug_id:
                LOGGER.error("PayPal request failed; debug_id=%s", debug_id)
            message = payload.get("message") or issue
            raise PayPalError(response.status_code, issue, debug_id, message)
        return payload