import json
from datetime import datetime

import pandas as pd
import requests
import streamlit as st

from config import API_URL, DEV_MODE
from db import get_connection

st.set_page_config(page_title="FinTech Risk Command Center", page_icon="R", layout="wide")
ACTION_COLORS = {"ALLOW": "#1f9d72", "REQUEST_2FA": "#d99a2b", "HOLD_FOR_REVIEW": "#e06c4f", "BLOCK": "#b83b5e"}


def api_get(path, params=None):
    response = requests.get(f"{API_URL}{path}", params=params, timeout=3)
    response.raise_for_status()
    return response.json()


def api_post(path, payload):
    response = requests.post(f"{API_URL}{path}", json=payload, timeout=3)
    response.raise_for_status()
    return response.json()


def query(sql, params=()):
    conn = get_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(sql, params)
        return cursor.fetchall()
    finally:
        cursor.close()
        conn.close()


def style_actions(row):
    color = ACTION_COLORS.get(row.get("action"), "#536273")
    return [f"color: {color}; font-weight: 700" if column == "action" else "" for column in row.index]


def render_overview():
    try:
        stats = api_get("/stats")
        transactions = query("SELECT COUNT(*) AS count FROM transactions")[0]["count"]
        status_rows = query("SELECT status, COUNT(*) AS count FROM txn_status GROUP BY status")
        status_counts = {row["status"]: row["count"] for row in status_rows}
        total = sum(status_counts.values()) or transactions or 1
    except Exception as exc:
        st.error(f"Dashboard API unavailable: {exc}")
        return
    action_counts = {"ALLOW": status_counts.get("APPROVED", 0), "REQUEST_2FA": status_counts.get("PENDING_2FA", 0), "HOLD_FOR_REVIEW": status_counts.get("HELD", 0), "BLOCK": status_counts.get("BLOCKED", 0)}
    st.title("Risk Command Center")
    st.caption(f"Live monitoring · refreshes every 2 seconds · {datetime.now():%H:%M:%S}")
    cards = st.columns(6)
    cards[0].metric("Transactions", f"{transactions:,}")
    cards[1].metric("ALLOW", f"{action_counts['ALLOW'] / total:.1%}")
    cards[2].metric("2FA", f"{action_counts['REQUEST_2FA'] / total:.1%}")
    cards[3].metric("HOLD", f"{action_counts['HOLD_FOR_REVIEW'] / total:.1%}")
    cards[4].metric("BLOCK", f"{action_counts['BLOCK'] / total:.1%}")
    latency = stats.get("average_latency_ms")
    cards[5].metric("Avg latency", f"{latency:.1f} ms" if latency is not None else "n/a")
    st.subheader("Live alerts")
    alerts = api_get("/alerts", {"limit": 50})
    if alerts:
        frame = pd.DataFrame(alerts)
        frame["reasons"] = frame["reasons"].apply(lambda value: " · ".join(value) if isinstance(value, list) else value)
        columns = ["id", "txn_id", "account_id", "frequency_score", "time_score", "geo_score", "final_score", "action", "reasons", "created_at"]
        st.dataframe(frame[[column for column in columns if column in frame]].style.apply(style_actions, axis=1), use_container_width=True, hide_index=True)
    else:
        st.info("No risk alerts yet.")


def render_account_inspector():
    st.subheader("Account inspector")
    accounts = query("SELECT DISTINCT nameOrig FROM transactions WHERE nameOrig IS NOT NULL ORDER BY nameOrig")
    names = [row["nameOrig"] for row in accounts]
    if not names:
        st.info("No accounts available.")
        return
    account = st.selectbox("Account", names)
    rows = query("SELECT event_time, lat, lon, amount, type, city, country FROM transactions WHERE nameOrig = %s ORDER BY event_time", (account,))
    data = pd.DataFrame(rows)
    profile = query("SELECT hour_histogram FROM account_profiles WHERE account_id = %s", (account,))
    left, right = st.columns(2)
    with left:
        st.caption("Transaction locations")
        if not data.empty:
            st.map(data.rename(columns={"lat": "latitude", "lon": "longitude"})[["latitude", "longitude"]].dropna())
        else:
            st.info("No location history.")
    with right:
        st.caption("Hour-of-day activity")
        histogram = []
        if profile and profile[0]["hour_histogram"]:
            value = profile[0]["hour_histogram"]
            histogram = value if isinstance(value, list) else json.loads(value)
        if histogram:
            st.bar_chart(pd.DataFrame({"hour": range(24), "transactions": histogram}).set_index("hour"))
        else:
            st.info("No timing profile.")


def render_2fa():
    st.subheader("2FA operations")
    pending = api_get("/pending-2fa")
    if not pending:
        st.success("No pending verifications.")
        return
    selected = st.selectbox("Pending transaction", pending, format_func=lambda row: f"txn {row['txn_id']} · {row['account_id']}")
    txn_id = selected["txn_id"]
    if DEV_MODE:
        if st.button("Reveal dev OTP", key=f"otp-{txn_id}"):
            st.session_state[f"otp-{txn_id}"] = api_get(f"/dev/otp/{txn_id}")["otp"]
        if f"otp-{txn_id}" in st.session_state:
            st.code(st.session_state[f"otp-{txn_id}"])
    otp = st.text_input("6-digit OTP", max_chars=6, key=f"input-{txn_id}")
    if st.button("Verify OTP", key=f"verify-{txn_id}"):
        try:
            st.success(api_post("/2fa/verify", {"txn_id": txn_id, "otp": otp})["status"])
        except requests.HTTPError as exc:
            st.error(exc.response.text)


def render_review_queue():
    st.subheader("Review queue")
    for alert in api_get("/review-queue"):
        with st.container(border=True):
            st.write(f"**txn {alert['txn_id']}** · {alert['account_id']} · score {alert['final_score']}")
            st.caption(" · ".join(alert.get("reasons") or []))
            analyst = st.text_input("Analyst", value="dashboard", key=f"analyst-{alert['txn_id']}")
            approve, block = st.columns(2)
            if approve.button("Approve", key=f"approve-{alert['txn_id']}"):
                api_post(f"/review/{alert['txn_id']}", {"decision": "APPROVE", "analyst": analyst})
                st.rerun()
            if block.button("Block", key=f"block-{alert['txn_id']}"):
                api_post(f"/review/{alert['txn_id']}", {"decision": "BLOCK", "analyst": analyst})
                st.rerun()


def render_sql_agent():
    st.subheader("SQL Agent")
    st.caption("Ask the existing read-only Ollama SQL agent about the transactions table.")
    question = st.text_input("Question", key="sql-agent-question")
    if st.button("Run SQL Agent") and question:
        try:
            from ai_agent import execute_sql, generate_sql
            sql = generate_sql(question)
            if not sql.upper().startswith("SELECT"):
                st.error("Only SELECT queries are allowed.")
                return
            columns, rows = execute_sql(sql)
            st.code(sql, language="sql")
            st.dataframe(pd.DataFrame(rows, columns=columns), use_container_width=True)
        except Exception as exc:
            st.error(f"SQL Agent unavailable: {exc}")


@st.fragment(run_every="2s")
def live_dashboard():
    render_overview()
    render_account_inspector()
    render_2fa()
    render_review_queue()


tab_live, tab_sql = st.tabs(["Live Risk", "SQL Agent"])
with tab_live:
    live_dashboard()
with tab_sql:
    render_sql_agent()
