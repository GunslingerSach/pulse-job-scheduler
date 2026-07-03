# Pulse — Distributed Job Scheduler

A production-ready distributed background job scheduling platform built with **FastAPI**, **PostgreSQL** (row-locking via `SELECT FOR UPDATE SKIP LOCKED`), **asyncio**, and a real-time **React + Tailwind CSS** monitoring dashboard.

---

## 🏗️ Architecture Overview

```mermaid
flowchart TB
    subgraph Clients["Frontend & API Clients"]
        Dashboard["React Dashboard (Vite + Tailwind)"]
        APIClient["External REST API Consumers"]
    end

    subgraph Server["FastAPI Backend (Stateless & Horizontally Scalable)"]
        Auth["JWT Auth Layer"]
        REST["REST API (Projects, Queues, Jobs, DLQ, Stats)"]
        WorkerAPI["Worker API (x-api-key Authentication)"]
        Loop["Background Scheduler Loop (Job Promotion & Worker Reaping)"]
    end

    subgraph Workers["Distributed Worker Fleet (Independent OS Processes)"]
        W1["Worker Process 1 (concurrency=5)"]
        W2["Worker Process 2 (concurrency=5)"]
        Wn["Worker Process N"]
    end

    DB[("PostgreSQL Database\nAtomic Row-Locking via FOR UPDATE SKIP LOCKED")]

    Dashboard -->|JWT Bearer| Auth
    Dashboard -->|JWT Bearer| REST
    APIClient -->|JWT Bearer| REST
    W1 -->|x-api-key| WorkerAPI
    W2 -->|x-api-key| WorkerAPI
    Wn -->|x-api-key| WorkerAPI

    REST --> DB
    WorkerAPI --> DB
    Loop --> DB
```

---

## ✨ Key Features

- **⚡ Atomic Concurrency Engine:** Replaces complex external brokers (RabbitMQ/Redis) with PostgreSQL-native `SELECT ... FOR UPDATE SKIP LOCKED`. Guarantees exactly-once execution and zero duplicate claims even under high concurrency.
- **🛠️ Distributed Worker Fleet:** Independent background worker processes (`app.worker.runner`) connect from any machine via API keys. Features automatic heartbeat reporting, real-time load tracking, and graceful drain-on-shutdown (`SIGINT`/`SIGTERM`).
- **🎯 Dynamic Queue Controls:** Configure per-queue concurrency ceilings, priority weighting, pause/resume toggles, and attach modular retry policies.
- **🔄 Advanced Retry & Dead Letter Queue (DLQ):** Supports customizable Fixed, Linear, and Exponential backoff curves. Jobs exhausting their retry budget automatically transition to an interactive Dead Letter Queue with full execution timelines and one-click replay.
- **🕒 Cron & Recurring Schedules:** Full ISO 8601 scheduled jobs and cron expressions (`0 * * * *`) powered by `croniter` with automatic occurrence materialization.
- **📊 Real-Time Premium Dashboard:** Dark-themed responsive web console built with React, Vite, and Tailwind CSS for live monitoring of workers, queues, job logs, and throughput analytics.

---

## 🚀 Step-by-Step Setup Instructions

### Prerequisites
- **Python 3.11+** (Tested on Python 3.13)
- **Node.js 18+**
- **PostgreSQL 14+** (Local instance or [Supabase](https://supabase.com))

---

### 1. Database Configuration
Create your PostgreSQL database or grab your connection URL from Supabase (**Project Settings $\rightarrow$ Database $\rightarrow$ URI Connection String**):
```text
postgresql+psycopg2://postgres:password@db.your-project.supabase.co:5432/postgres
```

---

### 2. Backend Setup
Navigate to the `backend` directory, create a virtual environment, install dependencies, and configure environment variables:

```bash
cd backend

# Create and activate virtual environment (Windows PowerShell)
python -m venv venv
.\venv\Scripts\activate

# On Linux/macOS:
# python3 -m venv venv && source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

Create a `.env` file inside `backend/` (`backend/.env`):
```ini
DATABASE_URL=postgresql+psycopg2://postgres:password@your-db-host:5432/postgres
JWT_SECRET=your-secure-jwt-secret-key
```

Start the FastAPI backend server:
```bash
uvicorn app.main:app --reload --port 8000
```
*Note: Database tables and indexes are automatically created on server startup (`Base.metadata.create_all`). Interactive Swagger API documentation is available at `http://localhost:8000/docs`.*

---

### 3. Launching Background Workers
Open a new terminal tab and launch one or more background worker processes. Retrieve your Project API Key from the dashboard's **Workers** page (`http://localhost:5173/workers`):

```bash
cd backend
.\venv\Scripts\activate

python -m app.worker.runner --api-base http://localhost:8000 --api-key <YOUR_PROJECT_API_KEY> --name worker-1 --concurrency 5
```
*Tip: You can open multiple terminals and run `--name worker-2`, `--name worker-3` to simulate a distributed multi-node cluster!*

#### Registering Custom Job Handlers
To execute custom job payloads, register handlers in `backend/app/worker/handlers.py`:
```python
from app.worker.handlers import handler

@handler("send_email")
async def send_email_handler(payload: dict) -> dict:
    recipient = payload.get("email")
    # Execute custom logic...
    return {"status": "sent", "recipient": recipient}
```

---

### 4. Frontend Dashboard Setup
Open a new terminal tab, install Node dependencies, and start the React development server:

```bash
cd frontend
npm install
npm run dev
```
Open your browser to **`http://localhost:5173`**. Register a new user account (which automatically provisions your initial organization and project) to access the dashboard.

---

## 🧪 Automated Testing

Pulse includes an automated test suite verifying atomic concurrency, retry budgets, and worker self-healing:

```bash
cd backend
.\venv\Scripts\activate

# Set test database environment variable
set TEST_DATABASE_URL="postgresql+psycopg2://postgres:password@localhost:5432/pulse_test_db"

pytest -v
```

---

## 📖 REST API Summary

| Endpoint | Method | Description |
|---|---|---|
| `/api/v1/auth/register` | `POST` | Register a new user account + default project |
| `/api/v1/auth/login` | `POST` | Authenticate and receive JWT Bearer token |
| `/api/v1/projects/{id}/queues` | `POST` / `GET` | Create or list project queues |
| `/api/v1/projects/{id}/queues/{qid}/jobs` | `POST` / `GET` | Dispatch or query background jobs |
| `/api/v1/workers/register` | `POST` | Register worker instance (`x-api-key` auth) |
| `/api/v1/workers/{id}/claim` | `POST` | Atomically claim runnable jobs |
| `/api/v1/projects/{id}/dead-letter` | `GET` | Inspect Dead Letter Queue entries |
| `/api/v1/projects/{id}/dead-letter/{dlq_id}/replay` | `POST` | Replay DLQ job back to active queue |

---

## 🔒 Security & Environment Notes
- **API Keys:** Worker commands display masked API keys by default on the UI to prevent screenshot exposure.
- **Git Protection:** `.env` files and internal development docs are excluded via `.gitignore`.
