# Design Decisions

## 1. Postgres row-locking instead of a message broker

The obvious alternative to `SELECT ... FOR UPDATE SKIP LOCKED` is a dedicated
broker — Redis lists/streams, RabbitMQ, SQS, Kafka. We chose Postgres-native
locking instead, for this project's scope, because:

- **One less moving part.** Job state, execution history, retry policy, and
  the "who currently owns this row" fact all live in the same transactional
  store. There's no risk of the queue and the database disagreeing about a
  job's state (a real failure mode with broker + DB pairs, usually solved with
  an outbox pattern — extra complexity we don't need at this scale).
- **`SKIP LOCKED` gives us exactly the semantics we need**: at-most-one-worker-
  claims-a-row, without blocking other workers on rows they don't care about,
  and the lock is automatically released if a worker dies mid-transaction.
- **Trade-off we accepted:** this doesn't scale as far as a purpose-built
  broker (Postgres write throughput on the `jobs` table becomes the ceiling).
  For most background-job workloads (thousands, not millions, of jobs/sec)
  this ceiling is well above what's needed, and the claim query's index
  (`ix_jobs_claim_scan`) keeps individual claims cheap even at large table
  sizes. If throughput ever became the bottleneck, the natural next step is
  moving *only* the hot claim path to Redis while keeping Postgres as the
  system of record — not a full broker migration.

## 2. Separate `job_executions` table instead of a `retry_count` column alone

We could have tracked retries with just a counter on `jobs`. Instead every
attempt gets its own `JobExecution` row. This costs one extra table and one
extra write per attempt, but it means the dashboard's execution history and
"why did this fail three times" debugging view are queries, not reconstructed
from log lines — and it gives us a durable place to store per-attempt duration,
worker, and error independent of the job's current (mutable) state.

## 3. Configurable retry strategy as a reusable policy, not a per-job field

`RetryPolicy` is its own table rather than columns inlined on `Queue`/`Job`,
so an ops team can define "aggressive-retry" and "no-retry" policies once and
attach them by reference. A job can still override its queue's default policy
(`Job.retry_policy_id`), which matters for e.g. a batch of jobs that should
never retry even though their queue's default is exponential backoff.

Backoff math (`RetryPolicy.compute_delay`) is intentionally simple and
synchronous — fixed, linear, and exponential (capped at `max_delay_seconds`)
— because more exotic strategies (jitter, decorrelated backoff) are a
one-line change to that single method without touching anything else.

## 4. Worker authentication via API key, dashboard auth via JWT

These are different trust boundaries. A logged-in human gets a short-lived
JWT tied to their identity, used for anything that changes configuration
(pausing a queue, creating a project). A worker process is unattended,
long-running, and represents "this project," not a specific person — so it
authenticates with a per-project API key instead. This also means rotating a
compromised worker key doesn't touch any user's session, and a worker never
needs to "log in" as a human.

## 5. In-process scheduler loop, not a separate service (for now)

Promoting due `SCHEDULED` jobs and reaping stale workers currently run as an
`asyncio` task inside the API server. We considered making this its own
deployable service from day one. We didn't, because:
- Both operations are single atomic SQL statements that are safe to run from
  multiple API instances concurrently (no leader election needed), so
  "in-process" doesn't create a scaling ceiling the way it would if this loop
  held state.
- **Trade-off we accepted:** the loop's cadence is coupled to however many API
  replicas happen to be running, and it can't be scaled or restarted
  independently of the HTTP API. If job-scheduling volume grew enough that
  this mattered, the fix is mechanical: move `scheduler_service.py` into its
  own process reading from the same database — no schema or API change
  required, because it was already written as pure functions over the DB.

## 6. Idempotency key is scoped per-queue, not global

`(queue_id, idempotency_key)` is a unique constraint, not a global unique
constraint on `idempotency_key` alone. This lets two different queues (e.g.
"emails" and "reports") reuse the same natural key ("user-42-welcome") without
collision, while still preventing accidental duplicate submission within a
single queue — the actual failure mode idempotency keys are meant to prevent
(a client retrying a `POST` after a timeout).

## 7. Recurring jobs as a template + materialized occurrences, not a live cron parser in the claim path

A `RECURRING` job is stored as a template row (`is_recurring_template=True`,
holds the `cron_expression`) that never itself becomes claimable. On creation,
and again after each successful completion, the next occurrence is computed
with `croniter` and inserted as an ordinary `SCHEDULED` job pointing back at
the template via `parent_recurring_job_id`. This keeps the hot claim query
completely ignorant of cron semantics — it only ever looks at plain
`run_at`/`status` — and means a paused/deleted recurring template simply stops
producing new occurrences without needing special-case logic in the worker.

## 8. What we deprioritized

Per the assignment's own evaluation criteria ("prioritize engineering quality
... over simply implementing the largest number of features"), we implemented
all core requirements solidly and picked a small number of bonus features
(RBAC via org membership, a functioning DLQ with replay) rather than
shallow-implementing all of them. Explicitly out of scope for this pass:

- **WebSocket live updates** — the dashboard polls every 3–5s instead. Given
  typical background-job dashboards are monitoring tools, not real-time
  collaboration tools, polling is simpler, needs no connection-management
  code, and is easy to swap for WebSockets later without changing the API
  shape (the same endpoints would just also push over a socket).
- **Workflow dependencies (DAGs between jobs)** — a real feature, but a
  meaningfully separate design problem (needs a `job_dependencies` table and
  claim-query changes to check upstream completion) that we chose not to
  bolt on shallowly.
- **Queue sharding / distributed locking beyond Postgres row locks** — not
  needed at the scale this design targets; see decision #1.
- **AI-generated failure summaries** — straightforward to add (summarize
  `JobLog`/`error_message` via an LLM call in the DLQ view) but adds an
  external dependency without changing any core reliability property, so it
  was left out in favor of finishing the required lifecycle/DB/API work to a
  higher standard.
- **Alembic migrations** — the codebase is structured for them (models are
  already the source of truth) but for this deliverable schema creation uses
  `Base.metadata.create_all`. Wiring in Alembic is mechanical and noted in the
  README as the first thing to add before a real production deployment.

## 9. Automated tests for critical functionality

Tests target the code where a bug would silently cause data loss or duplicate
execution — the claim/retry/reap logic in `job_service.py` — and run against a
real PostgreSQL instance (not SQLite) specifically because the correctness of
`SELECT FOR UPDATE SKIP LOCKED` and Postgres-specific column types cannot be
verified against a different database engine. All 14 tests were run and pass
against a live Postgres instance as part of building this project. For a full
breakdown of the test suite and execution instructions, see
[Automated Tests Documentation](file:///c:/Users/sachi/OneDrive/Desktop/pulse-job-scheduler/docs/automated-tests.md).
