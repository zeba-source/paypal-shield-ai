from kafka import KafkaProducer
import pandas as pd
import json
import time

# Kafka Producer
producer = KafkaProducer(
    bootstrap_servers='localhost:9092',
    value_serializer=lambda v: json.dumps(v).encode('utf-8')
)

# Read CSV File
file_path = 'small_dataset.csv'
df = pd.read_csv("small_dataset.csv")

# Stream rows one-by-one
for index, row in df.iterrows():
    data = row.to_dict()

    producer.send('transactions-topic', value=data)

    print(f"Sent: {data}")

    time.sleep(1)

producer.flush()
