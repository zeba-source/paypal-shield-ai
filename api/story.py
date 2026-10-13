import asyncio
import json
import math
import time
from collections import Counter
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from kafka import KafkaProducer

from config import BASE_DIR, KAFKA_BOOTSTRAP, TOPIC_TRANSACTIONS
from db import get_connection, record_txn_event
from scenario_injector import mule_events, night_events, travel_events

router = APIRouter()


def fetch(sql, params=(), one=False):
    conn = get_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(sql, params)
        return cursor.fetchone() if one else cursor.fetchall()
    finally:
        cursor.close()
        conn.close()


def parse_json(value):
    if isinstance(value, (dict, list)):
        return value
    if not value:
        return {}
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return {}


def action_for_status(status):
    return {"APPROVED": "ALLOW", "PENDING_2FA": "REQUEST_2FA", "HELD": "HOLD_FOR_REVIEW", "BLOCKED": "BLOCK"}.get(status, status)


@router.get("/story/overview")
def overview():
    total = fetch("SELECT COUNT(*) AS total, COUNT(DISTINCT nameOrig) AS accounts, MIN(event_time) AS start_time, MAX(event_time) AS end_time, SUM(amount) AS amount_total, AVG(amount) AS amount_average FROM transactions", one=True)
    types = fetch("SELECT type, COUNT(*) AS count, SUM(amount) AS amount FROM transactions GROUP BY type ORDER BY count DESC")
    flagged = fetch("SELECT COUNT(DISTINCT txn_id) AS count FROM risk_alerts", one=True)["count"]
    return {
        "total": total["total"] or 0,
        "counts_by_type": types,
        "amount_total": float(total["amount_total"] or 0),
        "amount_average": float(total["amount_average"] or 0),
        "time_range": {"start": total["start_time"], "end": total["end_time"]},
        "accounts": total["accounts"] or 0,
        "flagged_count": flagged or 0,
        "flagged_share": (flagged / total["total"]) if total["total"] else 0,
        "data_note": "PaySim timestamps and locations are simulated for this demo.",
    }


@router.get("/story/hourly")
def hourly():
    rows = fetch(
        "SELECT HOUR(event_time) AS hour, SUM(action_flagged = 0) AS normal, SUM(action_flagged = 1) AS flagged "
        "FROM (SELECT t.event_time, EXISTS(SELECT 1 FROM risk_alerts r WHERE r.txn_id=t.txn_id) AS action_flagged FROM transactions t) x "
        "GROUP BY hour ORDER BY hour"
    )
    return [{"hour": int(row["hour"]), "normal": int(row["normal"] or 0), "flagged": int(row["flagged"] or 0)} for row in rows]


@router.get("/story/actions")
def actions():
    rows = fetch("SELECT r.action, COUNT(*) AS count, SUM(t.amount) AS amount FROM risk_alerts r JOIN transactions t ON t.txn_id=r.txn_id GROUP BY r.action")
    status = fetch("SELECT status, COUNT(*) AS count FROM txn_status GROUP BY status")
    verification = fetch("SELECT status, COUNT(*) AS count FROM verification_requests GROUP BY status")
    total = fetch("SELECT COUNT(*) AS count FROM transactions", one=True)["count"]
    flagged = fetch("SELECT COUNT(DISTINCT txn_id) AS count FROM risk_alerts", one=True)["count"]
    v = {row["status"]: row["count"] for row in verification}
    s = {row["status"]: row["count"] for row in status}
    return {
        "actions": rows,
        "funnel": {
            "total": total,
            "flagged": flagged,
            "two_fa_requested": v.get("PENDING", 0) + v.get("PASSED", 0) + v.get("FAILED", 0) + v.get("EXPIRED", 0),
            "two_fa_passed": v.get("PASSED", 0),
            "two_fa_failed": v.get("FAILED", 0),
            "final_approved": s.get("APPROVED", 0),
            "final_held": s.get("HELD", 0),
            "final_blocked": s.get("BLOCKED", 0),
        },
    }


@router.get("/story/agents")
def agents():
    events = fetch("SELECT detail FROM txn_events WHERE stage='AGENTS_SCORED'")
    distributions = {}
    reasons = {}
    for agent in ("frequency", "time", "geo"):
        scores = []
        reason_counts = Counter()
        for row in events:
            detail = parse_json(row["detail"])
            result = detail.get("agents", {}).get(agent, {})
            score = float(result.get("score", detail.get("scores", {}).get(agent, 0)))
            scores.append(score)
            reason_counts.update(result.get("reasons", []))
        buckets = Counter(min(9, int(score // 10)) * 10 for score in scores)
        distributions[agent] = {
            "score_distribution": [{"bucket": bucket, "count": buckets.get(bucket, 0)} for bucket in range(0, 100, 10)],
            "top_reasons": [{"reason": reason, "count": count} for reason, count in reason_counts.most_common(5)],
        }
    return distributions


@router.get("/story/cases")
def cases(limit: int = Query(20, ge=1, le=100)):
    lim = int(limit)
    rows = fetch(
        "SELECT r.*, t.type, t.amount, t.event_time FROM risk_alerts r "
        "JOIN transactions t ON t.txn_id=r.txn_id "
        "ORDER BY r.final_score DESC, r.created_at DESC LIMIT %s",
        (lim,),
    )
    for row in rows:
        row["reasons"] = parse_json(row.get("reasons"))
    return rows


@router.get("/story/case/{txn_id}")
def case(txn_id: int):
    txn = fetch("SELECT * FROM transactions WHERE txn_id=%s", (txn_id,), one=True)
    if not txn:
        raise HTTPException(404, "Transaction not found")
    profile = fetch(
        "SELECT account_id, home_city, home_country, avg_amount, txn_count, hour_histogram, trusted_locations "
        "FROM account_profiles WHERE account_id=%s",
        (txn["nameOrig"],),
        one=True,
    )
    if profile:
        profile["hour_histogram"] = parse_json(profile.get("hour_histogram"))
        profile["trusted_locations"] = parse_json(profile.get("trusted_locations"))
    alert = fetch("SELECT * FROM risk_alerts WHERE txn_id=%s ORDER BY id DESC LIMIT 1", (txn_id,), one=True)
    if alert and isinstance(alert.get("reasons"), str):
        alert["reasons"] = parse_json(alert["reasons"])
    events = fetch("SELECT id, txn_id, stage, detail, created_at FROM txn_events WHERE txn_id=%s ORDER BY created_at, id", (txn_id,))
    previous = fetch("SELECT * FROM transactions WHERE nameOrig=%s AND txn_id<>%s ORDER BY event_time DESC LIMIT 20", (txn["nameOrig"], txn_id))
    
    previous_time = None
    for event in events:
        event["detail"] = parse_json(event["detail"])
        seconds_diff = (event["created_at"] - previous_time).total_seconds() if previous_time else 0.0
        event["seconds_since_previous"] = (event["created_at"] - previous_time).total_seconds() if previous_time else None
        event["seconds_between_steps"] = seconds_diff
        previous_time = event["created_at"]
        
    agent_event = next((event for event in events if event["stage"] == "AGENTS_SCORED"), None)
    policy_event = next((event for event in events if event["stage"] == "POLICY_DECISION"), None)
    
    if agent_event and agent_event.get("detail"):
        agents_data = agent_event["detail"]
    elif alert:
        reasons_list = alert.get("reasons") if isinstance(alert.get("reasons"), list) else parse_json(alert.get("reasons"))
        agents_data = {
            "scores": {
                "frequency": float(alert.get("frequency_score") or 0),
                "time": float(alert.get("time_score") or 0),
                "geo": float(alert.get("geo_score") or 0),
            },
            "agents": {
                "frequency": {"score": float(alert.get("frequency_score") or 0), "reasons": reasons_list},
                "time": {"score": float(alert.get("time_score") or 0), "reasons": reasons_list},
                "geo": {"score": float(alert.get("geo_score") or 0), "reasons": reasons_list},
            },
            "reasons": reasons_list,
        }
    else:
        agents_data = {
            "scores": {"frequency": 0.0, "time": 0.0, "geo": 0.0},
            "agents": {
                "frequency": {"score": 0.0, "reasons": []},
                "time": {"score": 0.0, "reasons": []},
                "geo": {"score": 0.0, "reasons": []},
            },
            "reasons": [],
        }

    if policy_event and policy_event.get("detail"):
        policy_data = policy_event["detail"]
    elif alert:
        policy_data = {
            "final_score": float(alert.get("final_score") or 0),
            "action": alert.get("action") or "ALLOW",
            "scores": agents_data.get("scores", {}),
        }
    else:
        policy_data = {"final_score": 0.0, "action": "ALLOW", "scores": {}}

    status_row = fetch("SELECT status FROM txn_status WHERE txn_id=%s", (txn_id,), one=True)
    outcome_status = status_row["status"] if status_row else (alert.get("action") if alert else "APPROVED")
    outcome = action_for_status(outcome_status)

    return {
        "transaction": txn,
        "profile": profile,
        "account_profile": profile,
        "account_profile_summary": profile,
        "agents": agents_data,
        "three_agent_scores": agents_data,
        "policy": policy_data,
        "policy_decision": policy_data,
        "alert": alert,
        "events": events,
        "ordered_events": events,
        "outcome": outcome,
        "final_outcome": outcome,
        "previous_transactions": previous,
        "last_20_transactions": previous,
    }


@router.get("/story/mule-graph/{account_id}")
def mule_graph(account_id: str):
    rows = fetch(
        "SELECT nameOrig, nameDest, amount FROM transactions WHERE (nameOrig=%s OR nameDest=%s) ORDER BY event_time DESC LIMIT 100",
        (account_id, account_id),
    )
    nodes = {account_id}
    edges = []
    for row in rows:
        nodes.update((row["nameOrig"], row["nameDest"]))
        edges.append({"source": row["nameOrig"], "target": row["nameDest"], "amount": float(row["amount"]) if row.get("amount") is not None else 0.0})
    return {"nodes": [{"id": node} for node in sorted(nodes)], "edges": edges}


@router.get("/story/geo/{account_id}")
def geo(account_id: str):
    rows = fetch("SELECT event_time, lat, lon, city, country FROM transactions WHERE nameOrig=%s ORDER BY event_time", (account_id,))
    impossible = []
    for previous, current in zip(rows, rows[1:]):
        if previous["lat"] is None or current["lat"] is None:
            continue
        distance = 6371 * 2 * math.asin(
            min(
                1,
                math.sqrt(
                    math.sin(math.radians(current["lat"] - previous["lat"]) / 2) ** 2
                    + math.cos(math.radians(previous["lat"]))
                    * math.cos(math.radians(current["lat"]))
                    * math.sin(math.radians(current["lon"] - previous["lon"]) / 2) ** 2
                ),
            )
        )
        hours = (current["event_time"] - previous["event_time"]).total_seconds() / 3600
        speed = distance / hours if hours > 0 else None
        if speed and speed > 900:
            impossible.append({"from": previous, "to": current, "implied_speed_kmh": speed})
    return {"locations": rows, "impossible_travel": impossible}


@router.get("/story/metrics")
def metrics():
    path = BASE_DIR / "results" / "metrics.json"
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {
        "count": 1000,
        "precision": 0.009,
        "recall": 1.0,
        "f1": 0.018,
        "false_positive_rate": 1.0,
        "average_latency_ms": 15.0,
        "confusion_matrix": {"true_positive": 9, "false_positive": 991, "false_negative": 0, "true_negative": 0},
    }


@router.head("/stream")
def stream_head():
    from fastapi.responses import Response
    return Response(media_type="text/event-stream", headers={"Cache-Control": "no-cache", "Connection": "keep-alive"})


@router.get("/stream")
async def stream(request: Request, last_id: int | None = None):
    header_val = request.headers.get("last-event-id")
    if last_id is not None:
        current_last_id = last_id
    elif header_val and header_val.isdigit():
        current_last_id = int(header_val)
    else:
        max_row = fetch("SELECT COALESCE(MAX(id), 0) AS max_id FROM txn_events", one=True)
        max_id = int(max_row["max_id"] or 0)
        current_last_id = max(0, max_id - 5)

    async def events():
        nonlocal current_last_id
        while not await request.is_disconnected():
            rows = fetch(
                "SELECT id, txn_id, stage, detail, created_at FROM txn_events WHERE id > %s ORDER BY id LIMIT 50",
                (current_last_id,),
            )
            for row in rows:
                current_last_id = row["id"]
                row["detail"] = parse_json(row["detail"])
                yield f"id: {row['id']}\ndata: {json.dumps(row, default=str)}\n\n"
            await asyncio.sleep(0.5)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/demo/scenario/{scenario}")
def demo_scenario(scenario: str):
    builders = {"mule": mule_events, "night": night_events, "travel": travel_events}
    if scenario not in builders:
        raise HTTPException(400, "scenario must be mule, night, or travel")
    
    events = builders[scenario]()
    baseline = fetch("SELECT COALESCE(MAX(txn_id), 0) AS max_id FROM transactions", one=True)["max_id"]
    
    kafka_published = False
    try:
        producer = KafkaProducer(
            bootstrap_servers=KAFKA_BOOTSTRAP,
            value_serializer=lambda value: json.dumps(value).encode("utf-8"),
            request_timeout_ms=1000,
            max_block_ms=1000,
        )
        for event in events:
            producer.send(TOPIC_TRANSACTIONS, event)
        producer.flush(timeout=2)
        producer.close(timeout=2)
        kafka_published = True
    except Exception as exc:
        print(f"Kafka publish skipped/failed ({exc}); executing scenario directly.")

    if kafka_published:
        accounts = sorted({event["nameOrig"] for event in events})
        deadline = time.monotonic() + 3.0
        ids = []
        while time.monotonic() < deadline:
            ids = [
                row["txn_id"]
                for row in fetch(
                    "SELECT txn_id FROM transactions WHERE txn_id > %s AND scenario=%s AND nameOrig IN ("
                    + ",".join(["%s"] * len(accounts))
                    + ") ORDER BY txn_id",
                    (baseline, scenario, *accounts),
                )
            ]
            if len(ids) >= len(events):
                return {"scenario": scenario, "published": len(events), "txn_ids": ids}
            time.sleep(0.1)
        if len(ids) >= len(events):
            return {"scenario": scenario, "published": len(events), "txn_ids": ids}

    # Fallback to direct processing through orchestrator
    from orchestrator import RiskOrchestrator
    from risk_consumer import insert_transaction, notify_2fa

    orchestrator = RiskOrchestrator()
    ids = []
    for event in events:
        txn_id = insert_transaction(event)
        txn = dict(event)
        txn["txn_id"] = txn_id
        record_txn_event(txn_id, "RECEIVED", {"type": txn.get("type"), "amount": txn.get("amount"), "scenario": txn.get("scenario")})
        decision = orchestrator.process(txn)
        if decision["action"] == "REQUEST_2FA":
            notify_2fa(txn_id, txn.get("nameOrig"))
        ids.append(txn_id)

    return {"scenario": scenario, "published": len(events), "txn_ids": ids}


@router.post("/demo/reset-demo-accounts")
def reset_demo_accounts():
    accounts = ("C_MULE_%", "C_DAY_%", "C_NIGHT_%", "C_TRAVEL_%")
    conn = get_connection()
    try:
        cursor = conn.cursor()
        for pattern in accounts:
            cursor.execute("DELETE FROM txn_events WHERE txn_id IN (SELECT txn_id FROM transactions WHERE nameOrig LIKE %s OR nameDest LIKE %s)", (pattern, pattern))
            cursor.execute("DELETE FROM risk_alerts WHERE account_id LIKE %s", (pattern,))
            cursor.execute("DELETE FROM transactions WHERE nameOrig LIKE %s OR nameDest LIKE %s", (pattern, pattern))
            cursor.execute("DELETE FROM account_profiles WHERE account_id LIKE %s", (pattern,))
        conn.commit()
    finally:
        cursor.close()
        conn.close()
    return {"status": "reset", "patterns": accounts}
