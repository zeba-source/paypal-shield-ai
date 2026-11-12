import httpx
import pytest

from api.paypal_client import PayPalClient, PayPalError


def make_client(handler, monkeypatch):
    monkeypatch.setenv("PAYPAL_CLIENT_ID", "client-id")
    monkeypatch.setenv("PAYPAL_CLIENT_SECRET", "client-secret")
    monkeypatch.setenv("PAYPAL_MODE", "sandbox")
    return PayPalClient(httpx.Client(transport=httpx.MockTransport(handler)))


def test_token_is_cached(monkeypatch):
    calls = []

    def handler(request):
        calls.append(request)
        if request.url.path.endswith("/oauth2/token"):
            return httpx.Response(200, json={"access_token": "token", "expires_in": 3600})
        return httpx.Response(200, json={"id": "order"})

    client = make_client(handler, monkeypatch)
    assert client.get_token() == "token"
    assert client.get_token() == "token"
    assert len([call for call in calls if call.url.path.endswith("/oauth2/token")]) == 1


def test_error_envelope_is_parsed(monkeypatch):
    def handler(request):
        if request.url.path.endswith("/oauth2/token"):
            return httpx.Response(200, json={"access_token": "token", "expires_in": 3600})
        return httpx.Response(
            422,
            json={
                "name": "UNPROCESSABLE_ENTITY",
                "details": [{"issue": "INSTRUMENT_DECLINED"}],
                "debug_id": "debug-123",
                "message": "The instrument was declined.",
            },
        )

    client = make_client(handler, monkeypatch)
    with pytest.raises(PayPalError) as raised:
        client.get_order("order-id")
    assert raised.value.status == 422
    assert raised.value.issue == "INSTRUMENT_DECLINED"
    assert raised.value.debug_id == "debug-123"
    assert str(raised.value) == "The instrument was declined."


def test_post_has_idempotency_and_mock_headers(monkeypatch):
    requests = []

    def handler(request):
        requests.append(request)
        if request.url.path.endswith("/oauth2/token"):
            return httpx.Response(200, json={"access_token": "token", "expires_in": 3600})
        return httpx.Response(201, json={"id": "order-id"})

    client = make_client(handler, monkeypatch)
    client.create_order(
        "10.00",
        reference_id="reference",
        description="description",
        request_id="fixed-request-id",
        mock_response="INSTRUMENT_DECLINED",
    )
    order_request = requests[-1]
    assert order_request.headers["PayPal-Request-Id"] == "fixed-request-id"
    assert order_request.headers["PayPal-Mock-Response"] == (
        '{"mock_application_codes":"INSTRUMENT_DECLINED"}'
    )