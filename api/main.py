import asyncio
import hashlib
import hmac
import json
import os
import secrets
import smtplib
import time
from collections import defaultdict
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage
from typing import Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from config import DEV_MODE
from db import get_connection
from db import record_txn_event
from .checkout import router as checkout_router
from .investigator import router as investigator_router
from .story import router as story_router


_rate_limit = defaultdict(list)


class TwoFAStartRequest(BaseModel):
    txn_id: int
    account_id: str


class TwoFAVerifyRequest(BaseModel):
    txn_id: int
    otp: str = Field(pattern=r"^\d{6}$")


class WebAuthnVerifyRequest(BaseModel):
    txn_id: int
    assertion: dict = Field(default_factory=dict)


class ReviewRequest(BaseModel):
    decision: Literal["APPROVE", "BLOCK"]
    analyst: str = Field(min_length=1, max_length=100)


def _hash_otp(otp):
    return hashlib.sha256(otp.encode("utf-8")).hexdigest()


def _check_rate_limit(txn_id):
    now = time.monotonic()
    recent = [stamp for stamp in _rate_limit[txn_id] if now - stamp < 60]
    if len(recent) >= 5:
        _rate_limit[txn_id] = recent
        raise HTTPException(status_code=429, detail="Too many verification requests")
    recent.append(now)
    _rate_limit[txn_id] = recent


def _execute(query, params=(), dictionary=False, commit=False, fetchone=False):
    conn = get_connection()
    try:
        cursor = conn.cursor(dictionary=dictionary)
        cursor.execute(query, params)
        result = cursor.fetchone() if fetchone else cursor.fetchall()
        if commit:
            conn.commit()
        return result
    finally:
        cursor.close()
        conn.close()


def _send_email(account_id, txn_id, otp):
    host = os.getenv("SMTP_HOST")
    port = os.getenv("SMTP_PORT")
    username = os.getenv("SMTP_USER")
    password = os.getenv("SMTP_PASSWORD")
    recipient = os.getenv("SMTP_TO")
    if not all((host, port, username, password, recipient)):
        return
    message = EmailMessage()
    message["Subject"] = "FinTech verification code"
    message["From"] = username
    message["To"] = recipient
    message.set_content(f"Verification code for transaction {txn_id}: {otp}")
    try:
        with smtplib.SMTP(host, int(port), timeout=5) as smtp:
            smtp.starttls()
            smtp.login(username, password)
            smtp.send_message(message)
    except OSError as exc:
        print(f"SMTP notification unavailable: {exc}")


def _latest_verification(cursor, txn_id):
    cursor.execute(
        "SELECT * FROM verification_requests WHERE txn_id = %s ORDER BY id DESC LIMIT 1",
        (txn_id,),
    )
    return cursor.fetchone()


def _expire_pending_verifications():
    conn = get_connection()
    expired_txn_ids = []
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT id, txn_id FROM verification_requests "
            "WHERE status = 'PENDING' AND expires_at <= UTC_TIMESTAMP()"
        )
        for row in cursor.fetchall():
            cursor.execute(
                "UPDATE verification_requests SET status = 'EXPIRED' "
                "WHERE id = %s AND status = 'PENDING'",
                (row["id"],),
            )
            if cursor.rowcount:
                _set_txn_status(cursor, row["txn_id"], "HELD")
                expired_txn_ids.append(row["txn_id"])
        conn.commit()
    finally:
        cursor.close()
        conn.close()
    for txn_id in expired_txn_ids:
        record_txn_event(txn_id, "2FA_EXPIRED", {})
        record_txn_event(txn_id, "HELD", {"status": "HELD"})
        from .checkout import fail_paypal_2fa
        fail_paypal_2fa(txn_id)
    return len(expired_txn_ids)


async def _expire_pending_loop():
    while True:
        try:
            _expire_pending_verifications()
        except Exception as exc:
            print(f"Pending 2FA expiry sweep failed: {exc}")
        await asyncio.sleep(30)


@asynccontextmanager
async def lifespan(_app):
    expiry_task = asyncio.create_task(_expire_pending_loop())
    try:
        yield
    finally:
        expiry_task.cancel()
        await asyncio.gather(expiry_task, return_exceptions=True)


app = FastAPI(title="FinTech Risk API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000", "*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(story_router)
app.include_router(checkout_router)
app.include_router(investigator_router)


@app.post("/2fa/start")
def start_2fa(request: TwoFAStartRequest):
    otp = f"{secrets.randbelow(900000) + 100000:06d}"
    expires_at = datetime.now(UTC).replace(tzinfo=None) + timedelta(minutes=5)
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO verification_requests
                (txn_id, account_id, otp_hash, dev_otp, status, attempts, expires_at)
            VALUES (%s, %s, %s, %s, 'PENDING', 0, %s)
            """,
            (request.txn_id, request.account_id, _hash_otp(otp), otp if DEV_MODE else None, expires_at),
        )
        cursor.execute(
            """
            INSERT INTO txn_status (txn_id, status) VALUES (%s, 'PENDING_2FA')
            ON DUPLICATE KEY UPDATE status = 'PENDING_2FA', updated_at = CURRENT_TIMESTAMP
            """,
            (request.txn_id,),
        )
        conn.commit()
    finally:
        cursor.close()
        conn.close()
    if DEV_MODE:
        print(f"DEV OTP txn_id={request.txn_id}: {otp}")
    _send_email(request.account_id, request.txn_id, otp)
    record_txn_event(request.txn_id, "2FA_SENT", {"account_id": request.account_id, "expires_at": expires_at.isoformat()})
    return {"txn_id": request.txn_id, "status": "PENDING", "expires_at": expires_at}


@app.get("/dev/otp/{txn_id}")
def dev_otp(txn_id: int):
    if not DEV_MODE:
        raise HTTPException(status_code=404, detail="Not found")
    verification = _execute(
        "SELECT dev_otp FROM verification_requests "
        "WHERE txn_id = %s AND status = 'PENDING' AND expires_at > UTC_TIMESTAMP() "
        "ORDER BY id DESC LIMIT 1",
        (txn_id,), dictionary=True, fetchone=True,
    )
    otp = verification["dev_otp"] if verification else None
    if otp is None:
        raise HTTPException(status_code=404, detail="OTP not found")
    return {"txn_id": txn_id, "otp": otp}


@app.post("/2fa/verify")
def verify_2fa(request: TwoFAVerifyRequest):
    _check_rate_limit(request.txn_id)
    conn = get_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        verification = _latest_verification(cursor, request.txn_id)
        if verification is None:
            raise HTTPException(status_code=404, detail="Verification request not found")
        if verification["status"] != "PENDING":
            raise HTTPException(status_code=409, detail=f"Verification is {verification['status']}")
        if verification["expires_at"] <= datetime.now(UTC).replace(tzinfo=None):
            cursor.execute(
                "UPDATE verification_requests SET status = 'EXPIRED' WHERE id = %s",
                (verification["id"],),
            )
            _set_txn_status(cursor, request.txn_id, "HELD")
            conn.commit()
            record_txn_event(request.txn_id, "2FA_EXPIRED", {})
            record_txn_event(request.txn_id, "HELD", {"status": "HELD"})
            from .checkout import fail_paypal_2fa
            fail_paypal_2fa(request.txn_id)
            return {"txn_id": request.txn_id, "status": "EXPIRED"}
        if hmac.compare_digest(verification["otp_hash"], _hash_otp(request.otp)):
            cursor.execute(
                "UPDATE verification_requests SET status = 'PASSED' WHERE id = %s",
                (verification["id"],),
            )
            _set_txn_status(cursor, request.txn_id, "APPROVED")
            conn.commit()
            record_txn_event(request.txn_id, "2FA_VERIFIED", {})
            record_txn_event(request.txn_id, "APPROVED", {"status": "APPROVED"})
            from .checkout import complete_paypal_2fa
            payment = complete_paypal_2fa(request.txn_id)
            return {"txn_id": request.txn_id, "status": "PASSED", **(payment or {})}

        attempts = int(verification["attempts"] or 0) + 1
        status = "FAILED" if attempts >= 3 else "PENDING"
        cursor.execute(
            "UPDATE verification_requests SET attempts = %s, status = %s WHERE id = %s",
            (attempts, status, verification["id"]),
        )
        if status == "FAILED":
            _set_txn_status(cursor, request.txn_id, "HELD")
        conn.commit()
        if status == "FAILED":
            record_txn_event(request.txn_id, "2FA_FAILED", {"attempts": attempts})
            record_txn_event(request.txn_id, "HELD", {"status": "HELD"})
            from .checkout import fail_paypal_2fa
            fail_paypal_2fa(request.txn_id)
        return {"txn_id": request.txn_id, "status": status, "attempts": attempts}
    finally:
        cursor.close()
        conn.close()


@app.post("/2fa/webauthn/auth/verify")
def verify_webauthn(request: WebAuthnVerifyRequest):
    if not request.assertion:
        raise HTTPException(status_code=400, detail="WebAuthn assertion is required")
    conn = get_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        verification = _latest_verification(cursor, request.txn_id)
        if verification is None:
            raise HTTPException(status_code=404, detail="Verification request not found")
        if verification["status"] != "PENDING":
            raise HTTPException(status_code=409, detail=f"Verification is {verification['status']}")
        cursor.execute(
            "UPDATE verification_requests SET status = 'PASSED' WHERE id = %s",
            (verification["id"],),
        )
        _set_txn_status(cursor, request.txn_id, "APPROVED")
        conn.commit()
    finally:
        cursor.close()
        conn.close()
    record_txn_event(request.txn_id, "2FA_VERIFIED", {"method": "webauthn"})
    record_txn_event(request.txn_id, "APPROVED", {"status": "APPROVED", "method": "webauthn"})
    from .checkout import complete_paypal_2fa
    payment = complete_paypal_2fa(request.txn_id)
    return {"txn_id": request.txn_id, "status": "PASSED", **(payment or {})}


def _set_txn_status(cursor, txn_id, status):
    cursor.execute(
        """
        INSERT INTO txn_status (txn_id, status) VALUES (%s, %s)
        ON DUPLICATE KEY UPDATE status = VALUES(status), updated_at = CURRENT_TIMESTAMP
        """,
        (txn_id, status),
    )


@app.get("/alerts")
def alerts(limit: int = Query(50, ge=1, le=500)):
    rows = _execute(
        "SELECT * FROM risk_alerts ORDER BY created_at DESC, id DESC LIMIT %s",
        (int(limit),), dictionary=True,
    )
    for row in rows:
        if isinstance(row.get("reasons"), str):
            try:
                row["reasons"] = json.loads(row["reasons"])
            except Exception:
                pass
    return rows


@app.get("/transactions/{txn_id}")
def transaction(txn_id: int):
    row = _execute("SELECT * FROM transactions WHERE txn_id = %s", (txn_id,), dictionary=True, fetchone=True)
    if row is None:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return row


@app.get("/stats")
def stats():
    action_rows = _execute(
        "SELECT action, COUNT(*) AS count FROM risk_alerts GROUP BY action",
        dictionary=True,
    )
    average = _execute("SELECT AVG(final_score) AS average_final_score FROM risk_alerts", dictionary=True, fetchone=True)
    two_fa = _execute(
        "SELECT status, COUNT(*) AS count FROM verification_requests GROUP BY status",
        dictionary=True,
    )
    pending = _execute(
        "SELECT COUNT(*) AS count FROM txn_status WHERE status = 'PENDING_2FA'",
        dictionary=True, fetchone=True,
    )
    latency_rows = _execute(
        """
        SELECT TIMESTAMPDIFF(MICROSECOND, received.created_at, decision.created_at) / 1000 AS latency_ms
        FROM txn_events received
        JOIN txn_events decision ON decision.txn_id = received.txn_id
        WHERE received.stage = 'RECEIVED' AND decision.stage = 'POLICY_DECISION'
        """, dictionary=True,
    )
    latencies = sorted(float(row["latency_ms"]) for row in latency_rows if row.get("latency_ms") is not None)
    average_latency = sum(latencies) / len(latencies) if latencies else 0.0
    p95_latency = latencies[min(len(latencies) - 1, int(len(latencies) * 0.95))] if latencies else 0.0
    counts = {row["action"]: row["count"] for row in action_rows}
    verification_counts = {row["status"]: row["count"] for row in two_fa}
    completed = verification_counts.get("PASSED", 0) + verification_counts.get("FAILED", 0) + verification_counts.get("EXPIRED", 0)
    return {
        "counts_by_action": counts,
        "average_final_score": average["average_final_score"] if average else None,
        "two_fa_pass_rate": verification_counts.get("PASSED", 0) / completed if completed else 0.0,
        "pending_2fa_count": pending["count"] if pending else 0,
        "average_decision_latency_ms": average_latency,
        "p95_decision_latency_ms": p95_latency,
    }


@app.get("/pending-2fa")
def pending_2fa():
    return _execute(
        "SELECT * FROM verification_requests "
        "WHERE status = 'PENDING' AND expires_at > UTC_TIMESTAMP() "
        "ORDER BY created_at DESC",
        dictionary=True,
    )


@app.get("/live/locations")
def live_locations(limit: int = Query(100, ge=1, le=500)):
    return _execute(
        """
        SELECT r.txn_id, r.action, t.lat, t.lon, t.city, t.country, t.event_time
        FROM risk_alerts r JOIN transactions t ON t.txn_id = r.txn_id
        WHERE t.lat IS NOT NULL AND t.lon IS NOT NULL
        ORDER BY r.created_at DESC, r.id DESC LIMIT %s
        """,
        (int(limit),), dictionary=True,
    )


@app.get("/review-queue")
def review_queue():
    rows = _execute(
        "SELECT * FROM risk_alerts WHERE action = 'HOLD_FOR_REVIEW' ORDER BY created_at ASC, id ASC",
        dictionary=True,
    )
    for row in rows:
        if isinstance(row.get("reasons"), str):
            try:
                row["reasons"] = json.loads(row["reasons"])
            except Exception:
                pass
    return rows


@app.post("/review/{txn_id}")
def review(txn_id: int, request: ReviewRequest):
    status = "APPROVED" if request.decision == "APPROVE" else "BLOCKED"
    conn = get_connection()
    try:
        cursor = conn.cursor()
        _set_txn_status(cursor, txn_id, status)
        cursor.execute(
            "INSERT INTO review_log (txn_id, analyst, decision) VALUES (%s, %s, %s)",
            (txn_id, request.analyst, request.decision),
        )
        conn.commit()
        record_txn_event(txn_id, "ANALYST_REVIEW", {"decision": request.decision, "analyst": request.analyst})
        record_txn_event(txn_id, status, {"status": status})
    finally:
        cursor.close()
        conn.close()
    from .checkout import handle_paypal_review
    payment = handle_paypal_review(txn_id, request.decision)
    return {"txn_id": txn_id, "status": status, "analyst": request.analyst, **(payment or {})}