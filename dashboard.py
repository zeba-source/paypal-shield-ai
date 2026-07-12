# import streamlit as st
# import pandas as pd
# import mysql.connector
# import time

# st.title("💳 Real-Time FinTech Dashboard")

# # MySQL Connection
# db = mysql.connector.connect(
#     host="localhost",
#     user="root",
#     password="root",
#     database="fintech_db"
# )

# query = "SELECT * FROM transactions"

# placeholder = st.empty()

# while True:

#     df = pd.read_sql(query, db)

#     with placeholder.container():

#         st.subheader("Live Transactions")

#         st.dataframe(df.tail(10))

#         total_transactions = len(df)

#         fraud_transactions = len(df[df['isFraud'] == 1])

#         total_amount = df['amount'].sum()

#         col1, col2, col3 = st.columns(3)

#         col1.metric("Total Transactions", total_transactions)

#         col2.metric("Fraud Transactions", fraud_transactions)

#         col3.metric("Total Amount", f"₹ {total_amount:,.2f}")

#         st.subheader("Transaction Types")

#         st.bar_chart(df['type'].value_counts())

#         st.subheader("Transaction Amount Trend")

#         st.line_chart(df['amount'])

#     time.sleep(5)



import streamlit as st
import pandas as pd
import mysql.connector
import time

# Page config
st.set_page_config(
    page_title="FinTech Dashboard",
    page_icon="💳",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.title("💳 Real-Time FinTech Dashboard")

# MySQL Connection
db = mysql.connector.connect(
    host="localhost",
    user="root",
    password="root",
    database="fintech_db"
)

query = "SELECT * FROM transactions"

placeholder = st.empty()

while True:
    df = pd.read_sql(query, db)

    with placeholder.container():
        # --- KPIs Row ---
        st.markdown("### 📌 Key Metrics")
        col1, col2, col3 = st.columns(3)

        total_transactions = len(df)
        fraud_transactions = len(df[df['isFraud'] == 1])
        total_amount = df['amount'].sum()

        col1.metric("🧾 Total Transactions", total_transactions)
        col2.metric("⚠️ Fraud Transactions", fraud_transactions)
        col3.metric("💰 Total Amount", f"₹ {total_amount:,.2f}")

        st.markdown("---")

        # --- Live Transactions Table ---
        st.markdown("### 🔄 Latest Transactions")
        st.dataframe(df.tail(10), use_container_width=True)

        st.markdown("---")

        # --- Charts Row ---
        st.markdown("### 📊 Transaction Insights")
        chart_col1, chart_col2 = st.columns(2)

        with chart_col1:
            st.markdown("#### Transaction Types")
            st.bar_chart(df['type'].value_counts())

        with chart_col2:
            st.markdown("#### Transaction Amount Trend")
            st.line_chart(df['amount'])

    time.sleep(5)
