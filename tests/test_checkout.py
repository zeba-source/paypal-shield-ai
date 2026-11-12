import pytest
from fastapi import HTTPException

from api import checkout


class FakePayPal:
    def __init__(self, action="ALLOW", declined=False):
        self.action = action
        self.declined = declined
        self.capture_calls = 0
        self.void_calls = 0

    def authorize_order(self, order_id, request_id=None):
        return {
            "authorization_id": "auth-1",
            "payer": {"payer_id": "payer-1", "email_address": "a@example.com"},
            "order": {
                "id": order_id,
                "payer": {"payer_id": "payer-1", "email_address": "a@example.com"},
                "purchase_units": [{"amount": {"currency_code": "USD", "value": "10.00"}}],
            },
        }

    def capture_authorization(self, auth_id, request_id=None):
        self.capture_calls += 1
        if self.declined:
            raise checkout.PayPalError(422, "INSTRUMENT_DECLINED", "debug-1", "declined")
        return {"id": "capture-1", "status": "COMPLETED"}

    def void_authorization(self, auth_id, request_id=None):
        self.void_calls += 1
        return {"status": "VOIDED"}


def setup_checkout(monkeypatch, action="ALLOW", declined=False):
    fake = FakePayPal(action, declined)
    state = {"paypal_order_id": "order-1", "txn_id": 1, "payment_status": "CREATED", "authorization_id": None}

    def get_order(_order_id):
        return state

    def set_order_status(_order_id, status):
        state["payment_status"] = status

    class FakeRisk:
        def process(self, txn):
            return {"action": action, "scores": {"frequency": 1, "time": 1, "geo": 1}, "reasons": []}

    monkeypatch.setattr(checkout, "get_paypal_client", lambda: fake)
    monkeypatch.setattr(checkout, "get_by_order_id", get_order)
    monkeypatch.setattr(checkout, "get_by_txn_id", lambda _txn_id: state)
    monkeypatch.setattr(checkout, "set_status", set_order_status)
    monkeypatch.setattr(checkout, "update_order_details", lambda _order_id, **kwargs: state.update(kwargs))
    monkeypatch.setattr(checkout, "record_txn_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(checkout, "_demo_for_txn", lambda _txn_id: None)
    monkeypatch.setattr(checkout, "_update_transaction", lambda _txn: None)
    monkeypatch.setattr(checkout, "_start_2fa", lambda *_args: None)
    monkeypatch.setattr(checkout, "RiskOrchestrator", FakeRisk)
    return fake, state


@pytest.mark.parametrize("action", ["ALLOW", "REQUEST_2FA", "HOLD_FOR_REVIEW", "BLOCK"])
def test_authorize_enforces_each_policy_action(monkeypatch, action):
    fake, state = setup_checkout(monkeypatch, action)
    result = checkout.authorize(checkout.AuthorizeRequest(order_id="order-1"))
    assert result["decision"] == action
    assert result["payment_status"] in {"CAPTURED", "PENDING_2FA", "PENDING_REVIEW", "VOIDED"}
    assert fake.capture_calls == (1 if action == "ALLOW" else 0)
    assert fake.void_calls == (1 if action == "BLOCK" else 0)


def test_capture_guard_prevents_double_capture(monkeypatch):
    fake, state = setup_checkout(monkeypatch)
    state.update(payment_status="CAPTURED", capture_id="capture-1")
    result = checkout._capture(state)
    assert result["id"] == "capture-1"
    assert fake.capture_calls == 0


def test_declined_capture_sets_failed_and_logs_event(monkeypatch):
    fake, state = setup_checkout(monkeypatch, declined=True)
    state.update(payment_status="AUTHORIZED", authorization_id="auth-1")
    with pytest.raises(HTTPException) as raised:
        checkout._capture(state)
    assert raised.value.status_code == 502
    assert state["payment_status"] == "FAILED"
    assert fake.capture_calls == 1


def test_demo_override_event_time_is_json_serializable():
    demo = checkout.DemoOverride(event_time="2026-01-01T02:00:00Z", country="GB", amount_multiplier=2)
    payload = demo.model_dump(mode="json")
    assert payload["event_time"] == "2026-01-01T02:00:00Z"