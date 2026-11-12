Real-time FinTech fraud detection. Kafka 3.9.1 at localhost:9092 (ZooKeeper mode), topics transactions-topic and risk-decisions-topic, MySQL 8.0 database fintech_db, kafka-python, mysql-connector-python, FastAPI, Streamlit. Existing: producer.py, consumer.py, ai_agent.py (do not modify ai_agent.py), dashboard.py (will be replaced later). Transaction fields: step,type,amount,nameOrig,oldbalanceOrg,newbalanceOrig,nameDest,oldbalanceDest,newbalanceDest,isFraud,isFlaggedFraud plus event_time,lat,lon,country,city. isFraud and isFlaggedFraud are labels for evaluation only; agents must never read them. Each agent returns {agent, score 0-100, reasons[], features{}}. Final actions come from a deterministic policy engine, never from an LLM. Config only via .env/config.py. MySQL syntax must work on MySQL 8.0 (no ADD COLUMN IF NOT EXISTS).

## PayPal hackathon

- Goal: PayPal AI Hackathon submission "PayPal Shield AI": the risk engine sits inside a real PayPal Sandbox payment flow.
- PayPal: Sandbox only, base URL https://api-m.sandbox.paypal.com, Orders v2 with intent=AUTHORIZE, Payments v2 capture/void. Currency USD. Secrets only in .env (PAYPAL_CLIENT_ID, PAYPAL_CLIENT_SECRET, PAYPAL_MODE=sandbox, LLM_API_KEY, DEV_MODE, LITE_MODE). Never log secrets or full emails.
- Payment state machine: CREATED -> AUTHORIZED -> (CAPTURED | VOIDED | PENDING_REVIEW | PENDING_2FA). Never capture unless status is AUTHORIZED and a policy decision exists. Never capture twice.
- Decisions come only from policy.py (deterministic). The LLM never changes an action.
- isFraud is for evaluation only. Do not modify ai_agent.py.
- Simulated inputs (PaySim stream, demo overrides) must be labelled "simulated" in code and UI.