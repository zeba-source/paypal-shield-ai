# from kafka import KafkaConsumer
# import json

# consumer = KafkaConsumer(
#     'transactions-topic',
#     bootstrap_servers='localhost:9092',
#     auto_offset_reset='earliest',
#     enable_auto_commit=True,
#     value_deserializer=lambda x: json.loads(x.decode('utf-8'))
# )

# print("Waiting for messages...\n")

# for message in consumer:
#     data = message.value

#     print("Received:", data)

#     # Example Fraud Detection
#     if 'amount' in data:
#         try:
#             amount = float(data['amount'])

#             if amount > 50000:
#                 print("⚠️ FRAUD ALERT: High Transaction Detected")

#         except:
#             pass


from kafka import KafkaConsumer
import json
import mysql.connector

# MySQL Connection
db = mysql.connector.connect(
    host="localhost",
    user="root",
    password="root",
    database="fintech_db"
)

cursor = db.cursor()

# Kafka Consumer
consumer = KafkaConsumer(
    'transactions-topic',
    bootstrap_servers='localhost:9092',
    auto_offset_reset='earliest',
    enable_auto_commit=True,
    value_deserializer=lambda x: json.loads(x.decode('utf-8'))
)

print("Waiting for messages...\n")

for message in consumer:

    data = message.value

    print("Received:", data)

    # Insert into MySQL
    sql = """
    INSERT INTO transactions (
        step, type, amount, nameOrig,
        oldbalanceOrg, newbalanceOrig,
        nameDest, oldbalanceDest,
        newbalanceDest, isFraud,
        isFlaggedFraud
    )
    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
    """

    values = (
        data.get('step'),
        data.get('type'),
        data.get('amount'),
        data.get('nameOrig'),
        data.get('oldbalanceOrg'),
        data.get('newbalanceOrig'),
        data.get('nameDest'),
        data.get('oldbalanceDest'),
        data.get('newbalanceDest'),
        int(data.get('isFraud', 0)),
        int(data.get('isFlaggedFraud', 0))
    )

    cursor.execute(sql, values)

    db.commit()

    print("Inserted into MySQL")

    # Fraud Detection
    if data.get('amount', 0) > 50000:
        print("⚠️ FRAUD ALERT: High Transaction Detected")