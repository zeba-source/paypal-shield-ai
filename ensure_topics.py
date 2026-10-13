from kafka import KafkaAdminClient
from kafka.admin import NewTopic

from config import KAFKA_BOOTSTRAP

TOPICS = [
    "transactions-topic",
    "risk-decisions-topic",
]


def ensure_topics():
    admin = KafkaAdminClient(bootstrap_servers=KAFKA_BOOTSTRAP, client_id="fintech-admin")
    try:
        existing = set(admin.list_topics())
        missing = [topic for topic in TOPICS if topic not in existing]

        if missing:
            admin.create_topics(
                new_topics=[
                    NewTopic(name=topic, num_partitions=1, replication_factor=1)
                    for topic in missing
                ],
                validate_only=False,
            )
            print(f"Created topics: {missing}")
        else:
            print("All topics already exist.")

        print("Current topics:")
        for topic in sorted(admin.list_topics()):
            if topic in TOPICS:
                print(topic)
    finally:
        admin.close()


if __name__ == "__main__":
    ensure_topics()
