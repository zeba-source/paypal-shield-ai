# FinTech Fraud Detection Agent Guidelines & Architecture

Real-time FinTech fraud detection. Kafka (transactions-topic, risk-decisions-topic), MySQL 8.0 fintech_db, FastAPI backend in api/ on http://localhost:8000, three agents (frequency/mule, time-of-transaction, geolocation) in agents/, deterministic policy engine in policy.py (<40 ALLOW, 40-69 REQUEST_2FA, 70-89 HOLD_FOR_REVIEW, >=90 BLOCK), 2FA via /2fa/start and /2fa/verify. isFraud is a label for evaluation only. PaySim has no real timestamps or locations, so event_time and location are simulated and the UI must say so. Frontend lives in frontend/ (Next.js App Router, TypeScript, Tailwind, Recharts, framer-motion, react-leaflet). Colours: ALLOW green, REQUEST_2FA amber, HOLD_FOR_REVIEW orange, BLOCK red; Frequency agent violet, Time agent cyan, Geo agent emerald. Never put secrets in the frontend. Never modify ai_agent.py.

---

## 1. System Architecture
- **Messaging**: Apache Kafka on `127.0.0.1:9092` with topics:
  - `transactions-topic`: Streaming incoming financial transactions.
  - `risk-decisions-topic`: Streaming evaluated risk decisions and actions.
- **Database**: MySQL 8.0 (`fintech_db`) storing transactions, risk alerts, verification requests, transaction statuses, analyst review logs, account profiles, and `txn_events`.
- **Backend API**: FastAPI application in `api/` served on `http://localhost:8000`.
- **Agents**: Located in `agents/`:
  - `frequency_agent.py`: Evaluates velocity, burst activity, and mule patterns (Violet).
  - `time_agent.py`: Evaluates transaction timing, off-hours, and unusual hour histograms (Cyan).
  - `geo_agent.py`: Evaluates impossible travel speed, international divergence, and unfamiliar locations (Emerald).
- **Deterministic Policy Engine**: Located in `policy.py`:
  - Score `< 40`: `ALLOW`
  - Score `40 - 69`: `REQUEST_2FA`
  - Score `70 - 89`: `HOLD_FOR_REVIEW`
  - Score `>= 90`: `BLOCK`
- **Two-Factor Authentication (2FA)**:
  - Triggered via `POST /2fa/start`
  - Validated via `POST /2fa/verify`

## 2. Data and Evaluation Rules
- `isFraud` is a ground-truth label strictly for evaluation and offline model scoring; it is never used as an input feature for real-time scoring.
- PaySim has no native timestamps or geographic coordinates; `event_time` and `location` (lat/lon, city, country) are simulated, and the UI must clearly display that data note.

## 3. Frontend Specifications
- **Stack**: Next.js App Router, TypeScript, Tailwind CSS, Recharts, framer-motion, react-leaflet (located in `frontend/`).
- **Color Coding**:
  - Decision Actions:
    - `ALLOW`: Green
    - `REQUEST_2FA`: Amber
    - `HOLD_FOR_REVIEW`: Orange
    - `BLOCK`: Red
  - Risk Agents:
    - Frequency agent: Violet
    - Time agent: Cyan
    - Geo agent: Emerald
- **Security & Integrity**:
  - Never put secrets, private keys, or credentials in the frontend.
  - Never modify `ai_agent.py`.
