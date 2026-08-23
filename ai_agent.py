import mysql.connector
from langchain_ollama import ChatOllama


# ==============================
# MYSQL CONFIG
# ==============================

DB_HOST = "localhost"
DB_USER = "root"
DB_PASSWORD = "root"
DB_NAME = "fintech_db"


# ==============================
# MYSQL CONNECTION
# ==============================

def get_connection():

    return mysql.connector.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME
    )


# ==============================
# OLLAMA
# ==============================

llm = ChatOllama(
    model="llama3.2",
    temperature=0
)


# ==============================
# AI → SQL
# ==============================

def generate_sql(question):

    prompt = f"""
You are a SQL expert for a FinTech transaction database.

The database contains one table:

transactions

Columns include:

id
step
type
amount
nameOrig
oldbalanceOrg
newbalanceOrig
nameDest
oldbalanceDest
newbalanceDest
isFraud
isFlaggedFraud
city
country
latitude
longitude

Convert the user's question into ONE MySQL SELECT query.

Rules:
- Return ONLY SQL.
- Do not use markdown.
- Do not use INSERT, UPDATE, DELETE or DROP.
- Only query the transactions table.

User question:
{question}
"""

    response = llm.invoke(prompt)

    sql = response.content.strip()

    # Remove markdown if model adds it
    sql = sql.replace("```sql", "")
    sql = sql.replace("```", "")
    sql = sql.strip()

    return sql


# ==============================
# EXECUTE SQL
# ==============================

def execute_sql(sql):

    connection = get_connection()

    cursor = connection.cursor()

    try:

        cursor.execute(sql)

        results = cursor.fetchall()

        columns = [desc[0] for desc in cursor.description]

        return columns, results

    finally:

        cursor.close()
        connection.close()


# ==============================
# START AI AGENT
# ==============================

print("✅ MySQL + Ollama connected")

print("""
🤖 FinTech AI Agent

Ask questions about your transaction database.

Type 'exit' to stop.
""")


while True:

    question = input("You: ")

    if question.lower() == "exit":
        break

    try:

        # AI generates SQL
        sql = generate_sql(question)

        print("\n🔎 Generated SQL:")
        print(sql)

        # Security check
        sql_upper = sql.upper()

        if not sql_upper.startswith("SELECT"):

            print("❌ Only SELECT queries are allowed.")

            continue

        # Execute SQL
        columns, results = execute_sql(sql)

        print("\n📊 Result:")

        print(columns)

        for row in results:
            print(row)

        print()

    except Exception as e:

        print("\n❌ Error:")
        print(e)
