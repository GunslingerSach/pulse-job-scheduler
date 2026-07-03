# Pulse — Distributed Job Scheduler

## 📖 Abstract

**Pulse** is a production-ready distributed background job scheduling platform built to execute, monitor, and retry background jobs across horizontal worker nodes. 

Instead of relying on heavy external message brokers like RabbitMQ or Redis, Pulse uses PostgreSQL row-level concurrency locking (`SELECT ... FOR UPDATE SKIP LOCKED`) to guarantee zero duplicate execution and exactly-once job dispatching even under high concurrency. 

### Key Capabilities
- **⚡ Atomic Concurrency Engine:** PostgreSQL index-scanned row locking prevents race conditions and duplicate job claims across distributed worker processes.
- **🛠️ Standalone Worker Process Fleet:** Modular multi-process worker architecture (`app.worker.runner`) with API-key authentication, real-time load reporting, and graceful drain-on-shutdown.
- **🔄 Fault Tolerance & Dead Letter Queue:** Configurable retry policies (Fixed, Linear, Exponential backoff). Jobs exhausting their retry budget automatically move to an interactive Dead Letter Queue (DLQ) with one-click replay.
- **🕒 Scheduled & Recurring Cron Jobs:** Full ISO 8601 future scheduling and cron expressions (`0 * * * *`) powered by `croniter`.
- **📊 Real-Time Web Console:** Dark-themed React + Tailwind CSS dashboard providing live monitoring of queues, active worker nodes, terminal execution logs, and system throughput.

---

## 📚 Technical Documentation

Full architectural specifications, API schemas, and engineering rationale are organized inside the `docs/` folder:

| Document | Description |
|---|---|
| [`docs/architecture.md`](docs/architecture.md) | High-level system topology, lifecycle diagrams, and concurrency design |
| [`docs/api-documentation.md`](docs/api-documentation.md) | REST API endpoints, request/response schemas, and error codes |
| [`docs/automated-tests.md`](docs/automated-tests.md) | Overview of the 14 automated unit/integration tests running against live PostgreSQL |
| [`docs/design-decisions.md`](docs/design-decisions.md) | Deep dive into engineering tradeoffs, database locking semantics, and security choices |
| [`docs/er-diagram.md`](docs/er-diagram.md) | Entity-Relationship schema definitions (`projects`, `queues`, `jobs`, `workers`, `dead_letter_jobs`) |

---

## 🛠️ Step-by-Step Setup Instructions

### Prerequisites
- **Python 3.11+**
- **Node.js 18+**
- **PostgreSQL 14+** (Local instance or cloud hosted via [Supabase](https://supabase.com))

---

### 1. Database Setup
Obtain your PostgreSQL connection URI. If using **Supabase**, enable the **Connection Pooler (Session Mode)** under **Project Settings $\rightarrow$ Database**:
```text
postgresql+psycopg2://postgres.project_ref:password@aws-1-region.pooler.supabase.com:5432/postgres
```

---

### 2. Backend API Server Setup
```bash
cd backend

# Create and activate Python virtual environment
python -m venv venv
# On Windows PowerShell:
.\venv\Scripts\activate
# On macOS/Linux:
# source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Set database connection variable
export DATABASE_URL="postgresql+psycopg2://postgres:password@localhost:5432/postgres"

# Start the API server
uvicorn app.main:app --reload --port 8000
```
*Note: Database tables and indexes are created automatically upon startup. Interactive API docs are served at `http://localhost:8000/docs`.*

---

### 3. Start Background Worker Node(s)
Open a new terminal tab and start a worker process against the API:
```bash
cd backend
.\venv\Scripts\activate

python -m app.worker.runner --api-base http://localhost:8000 --api-key <YOUR_PROJECT_API_KEY> --name worker-1 --concurrency 5
```
*Retrieve your `<YOUR_PROJECT_API_KEY>` from the dashboard's **Workers** page.*

---

### 4. Frontend Dashboard Setup
```bash
cd frontend
npm install
npm run dev
```
Open **`http://localhost:5173`** in your browser. Register an account to provision your workspace, create your first queue, and monitor live jobs.

---

## 🧪 Running Automated Tests
To run the automated test suite against a real PostgreSQL instance:
```bash
cd backend
.\venv\Scripts\activate
export TEST_DATABASE_URL="postgresql+psycopg2://postgres:password@localhost:5432/pulse_test_db"
pytest -v
```
