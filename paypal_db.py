import hashlib
from decimal import Decimal
from typing import Any, Final, Literal, TypedDict

from db import get_connection


PaymentStatus = Literal[
    "CREATED",
    "AUTHORIZED",
    "PENDING_2FA",
    "PENDING_REVIEW",
    "CAPTURED",
    "VOIDED",
    "FAILED",
]

ALLOWED_TRANSITIONS: Final[dict[PaymentStatus, frozenset[PaymentStatus]]] = {
    "CREATED": frozenset({"AUTHORIZED", "FAILED"}),
    "AUTHORIZED": frozenset({"CAPTURED", "VOIDED", "PENDING_REVIEW", "PENDING_2FA"}),
    "PENDING_2FA": frozenset({"AUTHORIZED", "VOIDED", "FAILED"}),
    "PENDING_REVIEW": frozenset({"AUTHORIZED", "VOIDED", "FAILED"}),
    "CAPTURED": frozenset(),
    "VOIDED": frozenset(),
    "FAILED": frozenset(),
}


class PayPalOrder(TypedDict, total=False):
    id: int
    txn_id: int | None
    paypal_order_id: str
    authorization_id: str | None
    capture_id: str | None
    payer_id: str | None
    payer_email_masked: str | None
    payer_country: str | None
    shipping_country: str | None
    amount: Decimal
    currency: str
    payment_status: PaymentStatus
    client_ip_hash: str | None
    device_hash: str | None


def validate_transition(current: PaymentStatus, target: PaymentStatus) -> None:
    if target not in ALLOWED_TRANSITIONS[current]:
        raise ValueError(f"Illegal PayPal payment transition: {current} -> {target}")


def mask_email(email: str | None) -> str | None:
    if not email:
        return None
    local, separator, domain = email.partition("@")
    if not separator or not local or not domain:
        return "***"
    suffix = ""
    if "." in domain:
        suffix = "." + domain.rsplit(".", 1)[1]
    return f"{local[0]}***@{domain[0]}***{suffix}"


def hash_identifier(value: str | None) -> str | None:
    return hashlib.sha256(value.encode("utf-8")).hexdigest() if value else None


def upsert_order(
    paypal_order_id: str,
    amount: Decimal | str,
    currency: str = "USD",
    *,
    txn_id: int | None = None,
    authorization_id: str | None = None,
    capture_id: str | None = None,
    payer_id: str | None = None,
    payer_email: str | None = None,
    payer_country: str | None = None,
    shipping_country: str | None = None,
    payment_status: PaymentStatus = "CREATED",
    client_ip: str | None = None,
    device_id: str | None = None,
) -> int:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO paypal_orders (
                txn_id, paypal_order_id, authorization_id, capture_id, payer_id,
                payer_email_masked, payer_country, shipping_country, amount, currency,
                payment_status, client_ip_hash, device_hash
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                txn_id = VALUES(txn_id), authorization_id = VALUES(authorization_id),
                capture_id = VALUES(capture_id), payer_id = VALUES(payer_id),
                payer_email_masked = VALUES(payer_email_masked), payer_country = VALUES(payer_country),
                shipping_country = VALUES(shipping_country), amount = VALUES(amount),
                currency = VALUES(currency), payment_status = VALUES(payment_status),
                client_ip_hash = VALUES(client_ip_hash), device_hash = VALUES(device_hash)
            """,
            (
                txn_id, paypal_order_id, authorization_id, capture_id, payer_id,
                mask_email(payer_email), payer_country, shipping_country, amount, currency,
                payment_status, hash_identifier(client_ip), hash_identifier(device_id),
            ),
        )
        conn.commit()
        return cursor.lastrowid or _get_id(cursor, paypal_order_id)
    finally:
        cursor.close()
        conn.close()


def set_status(paypal_order_id: str, target: PaymentStatus) -> None:
    conn = get_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT payment_status FROM paypal_orders WHERE paypal_order_id = %s FOR UPDATE",
            (paypal_order_id,),
        )
        row = cursor.fetchone()
        if not row:
            raise KeyError(f"Unknown PayPal order: {paypal_order_id}")
        validate_transition(row["payment_status"], target)
        cursor.execute(
            "UPDATE paypal_orders SET payment_status = %s WHERE paypal_order_id = %s",
            (target, paypal_order_id),
        )
        conn.commit()
    finally:
        cursor.close()
        conn.close()


def update_order_details(
    paypal_order_id: str,
    *,
    authorization_id: str | None = None,
    capture_id: str | None = None,
    payer_id: str | None = None,
    payer_email: str | None = None,
    payer_country: str | None = None,
    shipping_country: str | None = None,
    device_hash: str | None = None,
) -> None:
    fields = {
        "authorization_id": authorization_id,
        "capture_id": capture_id,
        "payer_id": payer_id,
        "payer_email_masked": mask_email(payer_email),
        "payer_country": payer_country,
        "shipping_country": shipping_country,
        "device_hash": device_hash,
    }
    updates = [(name, value) for name, value in fields.items() if value is not None]
    if not updates:
        return
    conn = get_connection()
    try:
        cursor = conn.cursor()
        assignments = ", ".join(f"`{name}` = %s" for name, _ in updates)
        cursor.execute(
            f"UPDATE paypal_orders SET {assignments} WHERE paypal_order_id = %s",
            tuple(value for _, value in updates) + (paypal_order_id,),
        )
        conn.commit()
    finally:
        cursor.close()
        conn.close()


def get_by_order_id(paypal_order_id: str) -> PayPalOrder | None:
    return _fetch_one("WHERE paypal_order_id = %s", (paypal_order_id,))


def get_by_txn_id(txn_id: int) -> PayPalOrder | None:
    return _fetch_one("WHERE txn_id = %s", (txn_id,))


def _fetch_one(where: str, params: tuple[Any, ...]) -> PayPalOrder | None:
    conn = get_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(f"SELECT * FROM paypal_orders {where} LIMIT 1", params)
        return cursor.fetchone()
    finally:
        cursor.close()
        conn.close()


def _get_id(cursor: Any, paypal_order_id: str) -> int:
    cursor.execute(
        "SELECT id FROM paypal_orders WHERE paypal_order_id = %s",
        (paypal_order_id,),
    )
    return cursor.fetchone()[0]