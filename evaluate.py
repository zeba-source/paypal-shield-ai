import argparse
import json
import math
import time
from pathlib import Path

import pandas as pd

from config import DB_CONFIG
from db import get_connection
from orchestrator import RiskOrchestrator
from producer import build_event_payload

PREFIX = "eval_"
TABLES = ("transactions", "account_profiles", "risk_alerts", "txn_status", "txn_events")


def setup_evaluation_tables(reset=False):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        for table in TABLES:
            cursor.execute(f"CREATE TABLE IF NOT EXISTS `{PREFIX}{table}` LIKE `{table}`")
            if reset:
                cursor.execute(f"TRUNCATE TABLE `{PREFIX}{table}`")
        conn.commit()
    finally:
        cursor.close()
        conn.close()


def insert_transaction(data):
    values = (
        int(data.get("step", 0) or 0), data.get("type"), float(data.get("amount", 0) or 0),
        data.get("nameOrig"), float(data.get("oldbalanceOrg", 0) or 0),
        float(data.get("newbalanceOrig", 0) or 0), data.get("nameDest"),
        float(data.get("oldbalanceDest", 0) or 0), float(data.get("newbalanceDest", 0) or 0),
        int(data.get("isFraud", 0) or 0), int(data.get("isFlaggedFraud", 0) or 0),
        data.get("event_time"), float(data.get("lat", 0) or 0), float(data.get("lon", 0) or 0),
        data.get("country"), data.get("city"),
    )
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            f"""
            INSERT INTO {PREFIX}transactions (
                step, type, amount, nameOrig, oldbalanceOrg, newbalanceOrig,
                nameDest, oldbalanceDest, newbalanceDest, isFraud, isFlaggedFraud,
                event_time, lat, lon, country, city
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            values,
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        cursor.close()
        conn.close()


def sanitized_txn(data, txn_id):
    return {key: value for key, value in data.items() if key not in {"isFraud", "isFlaggedFraud"}} | {"txn_id": txn_id}


def metrics(results):
    actual = [item["actual"] for item in results]
    predicted = [item["predicted"] for item in results]
    tp = sum(a and p for a, p in zip(actual, predicted))
    fp = sum(not a and p for a, p in zip(actual, predicted))
    fn = sum(a and not p for a, p in zip(actual, predicted))
    tn = sum(not a and not p for a, p in zip(actual, predicted))
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    false_positive_rate = fp / (fp + tn) if fp + tn else 0.0
    return {
        "count": len(results),
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "false_positive_rate": false_positive_rate,
        "average_latency_ms": sum(item["latency_ms"] for item in results) / len(results),
        "confusion_matrix": {"true_positive": tp, "false_positive": fp, "false_negative": fn, "true_negative": tn},
    }


def main():
    parser = argparse.ArgumentParser(description="Replay transactions through the offline risk orchestrator.")
    parser.add_argument("--n", type=int, default=5000)
    parser.add_argument("--reset", action="store_true")
    args = parser.parse_args()
    setup_evaluation_tables(args.reset)
    frame = pd.read_csv(Path(__file__).resolve().parent / "small_dataset.csv").head(args.n)
    orchestrator = RiskOrchestrator(PREFIX)
    results = []
    for index, row in frame.iterrows():
        data = build_event_payload(row.to_dict(), index)
        txn_id = insert_transaction(data)
        started = time.perf_counter()
        decision = orchestrator.process(sanitized_txn(data, txn_id))
        results.append({
            "actual": bool(int(data.get("isFraud", 0) or 0)),
            "predicted": decision["action"] != "ALLOW",
            "latency_ms": (time.perf_counter() - started) * 1000,
        })
    report = metrics(results)
    output = Path(__file__).resolve().parent / "results" / "metrics.json"
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Evaluated {report['count']} transactions")
    print(f"Precision: {report['precision']:.3f}  Recall: {report['recall']:.3f}  F1: {report['f1']:.3f}")
    print(f"False-positive rate: {report['false_positive_rate']:.3f}")
    print(f"Average latency: {report['average_latency_ms']:.2f} ms")
    print(f"Confusion matrix: {report['confusion_matrix']}")
    print(f"Saved: {output}")


if __name__ == "__main__":
    main()
