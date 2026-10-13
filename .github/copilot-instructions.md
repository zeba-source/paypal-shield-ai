Project: real-time FinTech fraud detection (Windows, Python venv, VS Code).
Stack: Kafka 3.9.1 at localhost:9092 (ZooKeeper mode), topic "transactions-topic", MySQL database fintech_db, table transactions, kafka-python, mysql-connector-python, FastAPI.
Existing files: producer.py (streams PaySim CSV rows to Kafka), consumer.py (Kafka -> MySQL), ai_agent.py (SQL agent, DO NOT modify).
Transaction fields: step, type, amount, nameOrig, oldbalanceOrg, newbalanceOrig, nameDest, oldbalanceDest, newbalanceDest, isFraud, isFlaggedFraud.
Rules:
- isFraud and isFlaggedFraud are labels for evaluation only. Agents must never use them as inputs.
- Each agent returns {"agent": str, "score": 0-100, "reasons": [str], "features": dict}.
- Final ALLOW / 2FA / HOLD / BLOCK decisions come from a deterministic policy engine, never from an LLM.
- Use a .env file for config (DB creds, Kafka servers). No hardcoded passwords.
- Add logging, type hints and try/except around DB and Kafka calls.