# Automated Tests for Critical Functionality

Pulse Job Scheduler includes an automated test suite located in `backend/tests/`. The tests specifically target code paths where concurrency bugs, race conditions, or unhandled errors would silently cause data loss, duplicate job execution, or zombie locks.

## Philosophy: Real PostgreSQL over In-Memory Mocks

Background job schedulers depend heavily on transactional isolation and database-level locking semantics. For this reason, all automated tests run against a **real PostgreSQL instance** rather than an in-memory SQLite database or mocked ORM layer.

Testing against live PostgreSQL guarantees:
1. **Exact Concurrency Semantics:** Verification of `SELECT ... FOR UPDATE SKIP LOCKED`, which prevents multiple worker processes from claiming the same job row simultaneously.
2. **PostgreSQL Column Types:** Native handling of `UUID` primary keys, `JSON`/`JSONB` payloads, and database enum constraints (`JobStatus`, `JobType`, `WorkerStatus`).
3. **Atomic Transactions:** Real verification that failure rollbacks and multi-table cascades (`ON DELETE CASCADE` and `SET NULL`) behave exactly as expected in production.

---

## Test Suite Breakdown

The 14 automated tests are organized into three distinct test suites matching the lifecycle of background jobs and worker instances:

### 1. Atomic Job Claiming (`backend/tests/test_claiming.py`)
Verifies the concurrency engine and claim scanner:
- `test_claim_respects_priority_order`: Ensures higher priority jobs (e.g., priority `10`) are claimed before lower priority jobs (`0`) when both are queued.
- `test_claim_respects_queue_concurrency_limit`: Verifies that when a queue has `max_concurrency=2` and 5 jobs queued, a worker requesting 10 jobs is strictly handed only 2 jobs.
- `test_claim_does_not_double_claim_already_claimed_jobs`: Ensures a second claim attempt immediately following a first claim returns 0 jobs, proving row locks and `CLAIMED` status transitions prevent duplicate dispatch.
- `test_claim_ignores_future_scheduled_jobs`: Verifies that jobs with a future `run_at` timestamp are completely bypassed by the claim scanner.
- `test_claim_ignores_paused_queue`: Confirms that when a queue has `is_paused=True`, workers cannot claim jobs from it regardless of queue depth.

### 2. Retry Budget & Dead Letter Queue (`backend/tests/test_retry_and_dlq.py`)
Verifies fault tolerance, backoff algorithms, and execution audit trails:
- `test_failed_job_within_retry_budget_is_requeued_as_retrying`: Confirms that failing an execution when `retry_count < max_retries` transitions the job to `RETRYING`, increments `retry_count`, and schedules a future `run_at`.
- `test_job_moves_to_dead_letter_after_exhausting_retries`: Confirms that when a job exhausts its retry budget (`retry_count >= max_retries`), it is atomically moved out of `jobs` and inserted into `dead_letter_jobs` with full failure history preserved.
- `test_exponential_backoff_delay_grows`: Validates the mathematical delay curve ($base \times multiplier^{attempt}$).
- `test_exponential_backoff_caps_at_max_delay`: Ensures delay curves never exceed `max_delay_seconds`.
- `test_linear_backoff`: Validates linear delay growth.
- `test_fixed_backoff`: Validates constant delay intervals across retries.
- `test_completed_job_clears_worker_assignment`: Confirms that marking a job `COMPLETED` unassigns `claimed_by_worker_id` and persists the execution result payload.

### 3. Background Reaping & Promotion (`backend/tests/test_worker_reaping.py`)
Verifies the automated self-healing scheduler loop:
- `test_promote_scheduled_jobs_flips_due_jobs_to_queued`: Verifies that `SCHEDULED` jobs whose `run_at` timestamp has arrived are atomically promoted to `QUEUED` so workers can claim them.
- `test_reap_stale_workers_requeues_their_jobs`: Simulates a worker crash (heartbeat older than the offline threshold). Confirms the backend marks the crashed worker `OFFLINE` and automatically requeues any jobs it was executing back to `QUEUED` so healthy workers can adopt them.

---

## How to Run the Tests

To execute the test suite locally using `pytest`:

1. Ensure your Python virtual environment is active:
   ```powershell
   cd backend
   .\venv\Scripts\activate
   ```
2. Provide a PostgreSQL test database URI (to avoid truncating your local development database during test teardown):
   ```powershell
   $env:TEST_DATABASE_URL="postgresql+psycopg2://postgres:password@localhost:5432/pulse_test_db"
   pytest -v
   ```

All 14 tests run in under 3 seconds on standard hardware.
