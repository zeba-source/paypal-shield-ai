import json
import os
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from config import DEV_MODE
from db import get_connection, record_txn_event
from orchestrator import RiskOrchestrator
from paypal_db import (
    get_by_order_id,
    get_by_txn_id,
    set_status,
    update_order_details,
    upsert_order,
)
from api.paypal_client import PayPalClient, PayPalError


router = APIRouter(prefix="/checkout", tags=["checkout"])
_client: PayPalClient | None = None
MERCHANT_ID = os.getenv("PAYPAL_MERCHANT_ID", "PAYPAL_MERCHANT")


class DemoOverride(BaseModel):
    event_time: datetime | None = None
    country: str | None = Field(default=None, min_length=2, max_length=50)
    amount_multiplier: Decimal | None = Field(default=None, gt=0, le=100)


class CreateOrderRequest(BaseModel):
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    description: str = Field(min_length=1, max_length=127)
    demo: DemoOverride | None = None


class AuthorizeRequest(BaseModel):
    order_id: str
    device_hash: str | None = None


class WebAuthnVerifyRequest(BaseModel):
    txn_id: int


def get_paypal_client() -> PayPalClient:
    global _client
    if _client is None:
        _client = PayPalClient()
    return _client


def txn_from_paypal_order(order: dict[str, Any], demo: DemoOverride | None = None) -> dict[str, Any]:
    purchase_unit = (order.get("purchase_units") or [{}])[0]
    amount_data = purchase_unit.get("amount") or {}
    payer = order.get("payer") or {}
    shipping = (purchase_unit.get("shipping") or {}).get("address") or {}
    event_time = datetime.now(UTC).replace(tzinfo=None)
    country = shipping.get("country_code") or payer.get("address", {}).get("country_code")
    amount = Decimal(str(amount_data.get("value", "0")))
    simulated = False
    if DEV_MODE and demo:
        simulated = True
        if demo.event_time:
            event_time = demo.event_time.astimezone(UTC).replace(tzinfo=None) if demo.event_time.tzinfo else demo.event_time
        if demo.country:
            country = demo.country
        if demo.amount_multiplier:
            amount *= demo.amount_multiplier
    return {
        "txn_id": order.get("txn_id"),
        "nameOrig": payer.get("payer_id") or payer.get("payer_id", "UNKNOWN_PAYER"),
        "nameDest": MERCHANT_ID,
        "type": "PAYMENT",
        "amount": amount,
        "currency": amount_data.get("currency_code", "USD"),
        "country": country,
        "event_time": event_time,
        "simulated": simulated,
    }


def _insert_transaction(order_id: str, amount: Decimal) -> int:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO transactions
                (step, type, amount, nameOrig, nameDest, event_time, country, scenario)
            VALUES (0, 'PAYMENT', %s, %s, %s, UTC_TIMESTAMP(), %s, 'paypal')
            """,
            (amount, f"PAYPAL_PENDING_{order_id}", MERCHANT_ID, None),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        cursor.close()
        conn.close()


def _update_transaction(txn: dict[str, Any]) -> None:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE transactions
            SET amount = %s, nameOrig = %s, nameDest = %s, event_time = %s,
                country = %s, scenario = %s
            WHERE txn_id = %s
            """,
            (
                txn["amount"], txn["nameOrig"], txn["nameDest"], txn["event_time"],
                txn.get("country"), "simulated" if txn.get("simulated") else "paypal", txn["txn_id"],
            ),
        )
        conn.commit()
    finally:
        cursor.close()
        conn.close()


def _demo_for_txn(txn_id: int) -> DemoOverride | None:
    conn = get_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT detail FROM txn_events WHERE txn_id = %s AND stage = 'PAYPAL_ORDER_CREATED' ORDER BY id DESC LIMIT 1",
            (txn_id,),
        )
        row = cursor.fetchone()
        detail = row.get("detail") if row else None
        if isinstance(detail, str):
            detail = json.loads(detail)
        return DemoOverride(**detail["demo"]) if detail and detail.get("demo") else None
    finally:
        cursor.close()
        conn.close()


def _set_paypal_status(order_id: str, target: str) -> None:
    try:
        set_status(order_id, target)  # type: ignore[arg-type]
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="PayPal order not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


def _start_2fa(txn_id: int, account_id: str) -> None:
    from .main import TwoFAStartRequest, start_2fa

    start_2fa(TwoFAStartRequest(txn_id=txn_id, account_id=account_id))


def _capture(order: dict[str, Any]) -> dict[str, Any]:
    current = get_by_order_id(order["paypal_order_id"])
    if not current:
        raise HTTPException(status_code=404, detail="PayPal order not found")
    if current["payment_status"] == "CAPTURED":
        return {"id": current.get("capture_id"), "status": "COMPLETED"}
    if current["payment_status"] != "AUTHORIZED":
        raise HTTPException(status_code=409, detail="Payment is not authorized for capture")
    try:
        response = get_paypal_client().capture_authorization(
            current["authorization_id"], request_id=f"capture-{uuid.uuid4()}"
        )
    except PayPalError as exc:
        set_status(current["paypal_order_id"], "FAILED")
        record_txn_event(current["txn_id"], "PAYPAL_CAPTURE_FAILED", {"issue": exc.issue, "debug_id": exc.debug_id})
        raise HTTPException(status_code=502, detail="PayPal capture failed") from exc
    capture_id = response.get("id")
    update_order_details(current["paypal_order_id"], capture_id=capture_id)
    set_status(current["paypal_order_id"], "CAPTURED")
    record_txn_event(current["txn_id"], "PAYPAL_CAPTURED", {"capture_id": capture_id})
    return response


def _void(order: dict[str, Any]) -> dict[str, Any]:
    current = get_by_order_id(order["paypal_order_id"])
    if not current:
        raise HTTPException(status_code=404, detail="PayPal order not found")
    if current["payment_status"] == "VOIDED":
        return {"status": "VOIDED"}
    if current["payment_status"] not in {"AUTHORIZED", "PENDING_REVIEW", "PENDING_2FA"}:
        raise HTTPException(status_code=409, detail="Payment is not authorized for void")
    try:
        response = get_paypal_client().void_authorization(
            current["authorization_id"], request_id=f"void-{uuid.uuid4()}"
        )
    except PayPalError as exc:
        set_status(current["paypal_order_id"], "FAILED")
        record_txn_event(current["txn_id"], "PAYPAL_CAPTURE_FAILED", {"issue": exc.issue, "debug_id": exc.debug_id})
        raise HTTPException(status_code=502, detail="PayPal void failed") from exc
    set_status(current["paypal_order_id"], "VOIDED")
    record_txn_event(current["txn_id"], "PAYPAL_VOIDED", {})
    return response


@router.post("/create-order")
def create_order(request: CreateOrderRequest):
    if request.demo and not DEV_MODE:
        raise HTTPException(status_code=403, detail="Demo overrides require DEV_MODE")
    try:
        response = get_paypal_client().create_order(
            str(request.amount), reference_id=f"txn-{uuid.uuid4()}", description=request.description
        )
    except PayPalError as exc:
        raise HTTPException(status_code=502, detail="PayPal order creation failed") from exc
    order_id = response.get("id")
    if not order_id:
        raise HTTPException(status_code=502, detail="PayPal returned no order id")
    txn_id = _insert_transaction(order_id, request.amount)
    upsert_order(order_id, request.amount, txn_id=txn_id)
    record_txn_event(
        txn_id,
        "PAYPAL_ORDER_CREATED",
        {
            "order_id": order_id,
            "simulated": bool(request.demo),
            "demo": request.demo.model_dump(mode="json") if request.demo else None,
        },
    )
    return {"order_id": order_id}


@router.post("/authorize")
def authorize(request: AuthorizeRequest):
    order = get_by_order_id(request.order_id)
    if not order:
        raise HTTPException(status_code=404, detail="PayPal order not found")
    if order["payment_status"] != "CREATED":
        raise HTTPException(status_code=409, detail="PayPal order is not awaiting authorization")
    try:
        result = get_paypal_client().authorize_order(request.order_id, request_id=f"authorize-{uuid.uuid4()}")
    except PayPalError as exc:
        _set_paypal_status(request.order_id, "FAILED")
        raise HTTPException(status_code=502, detail="PayPal authorization failed") from exc
    payer = result.get("payer") or {}
    update_order_details(
        request.order_id,
        authorization_id=result.get("authorization_id"), payer_id=payer.get("payer_id"),
        payer_email=payer.get("email_address"), payer_country=(payer.get("address") or {}).get("country_code"),
        device_hash=request.device_hash,
    )
    _set_paypal_status(request.order_id, "AUTHORIZED")
    record_txn_event(order["txn_id"], "PAYPAL_AUTHORIZED", {"authorization_id": result.get("authorization_id")})
    paypal_order = result.get("order") or get_paypal_client().get_order(request.order_id)
    paypal_order["txn_id"] = order["txn_id"]
    txn = txn_from_paypal_order(paypal_order, _demo_for_txn(order["txn_id"]))
    txn["txn_id"] = order["txn_id"]
    _update_transaction(txn)
    decision = RiskOrchestrator().process(txn)
    action = decision["action"]
    methods = ["PAYPAL", "RISK_ORCHESTRATOR"]
    if action == "ALLOW":
        _capture(get_by_order_id(request.order_id) or order)
        payment_status = "CAPTURED"
    elif action == "REQUEST_2FA":
        _set_paypal_status(request.order_id, "PENDING_2FA")
        _start_2fa(order["txn_id"], txn["nameOrig"])
        methods.append("2FA")
        payment_status = "PENDING_2FA"
    elif action == "HOLD_FOR_REVIEW":
        _set_paypal_status(request.order_id, "PENDING_REVIEW")
        payment_status = "PENDING_REVIEW"
    else:
        _void(get_by_order_id(request.order_id) or order)
        payment_status = "VOIDED"
    return {"txn_id": order["txn_id"], "payment_status": payment_status, "decision": action, "scores": decision["scores"], "reasons": decision["reasons"], "methods": methods}


@router.get("/{order_id}/status")
def checkout_status(order_id: str):
    order = get_by_order_id(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="PayPal order not found")
    return order


def complete_paypal_2fa(txn_id: int) -> dict[str, Any] | None:
    order = get_by_txn_id(txn_id)
    if not order or order["payment_status"] != "PENDING_2FA":
        return None
    verification = get_connection()
    try:
        cursor = verification.cursor(dictionary=True)
        cursor.execute(
            "SELECT status FROM verification_requests WHERE txn_id = %s ORDER BY id DESC LIMIT 1",
            (txn_id,),
        )
        row = cursor.fetchone()
    finally:
        cursor.close()
        verification.close()
    if not row or row["status"] != "PASSED":
        raise HTTPException(status_code=409, detail="2FA verification has not passed")
    _set_paypal_status(order["paypal_order_id"], "AUTHORIZED")
    response = _capture(get_by_order_id(order["paypal_order_id"]) or order)
    return {"payment_status": "CAPTURED", "capture_id": response.get("id")}


def fail_paypal_2fa(txn_id: int) -> None:
    order = get_by_txn_id(txn_id)
    if order and order["payment_status"] == "PENDING_2FA":
        _set_paypal_status(order["paypal_order_id"], "PENDING_REVIEW")


def handle_paypal_review(txn_id: int, decision: str) -> dict[str, Any] | None:
    order = get_by_txn_id(txn_id)
    if not order:
        return None
    if decision == "APPROVE":
        _set_paypal_status(order["paypal_order_id"], "AUTHORIZED")
        response = _capture(get_by_order_id(order["paypal_order_id"]) or order)
        return {"payment_status": "CAPTURED", "capture_id": response.get("id")}
    _void(order)
    return {"payment_status": "VOIDED"}