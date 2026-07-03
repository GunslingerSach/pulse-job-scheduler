# Entity-Relationship Diagram

This diagram reflects the actual schema in `backend/app/models.py`. All primary
keys are UUIDs generated application-side; all foreign keys have explicit
`ON DELETE` behavior chosen per relationship (see notes below the diagram).

```mermaid
erDiagram
    USERS ||--o{ ORGANIZATION_MEMBERS : "has"
    ORGANIZATIONS ||--o{ ORGANIZATION_MEMBERS : "has"
    ORGANIZATIONS ||--o{ PROJECTS : "owns"
    PROJECTS ||--o{ QUEUES : "owns"
    RETRY_POLICIES ||--o{ QUEUES : "default for"
    RETRY_POLICIES ||--o{ JOBS : "overrides for"
    QUEUES ||--o{ JOBS : "contains"
    JOBS ||--o{ JOB_EXECUTIONS : "has attempts"
    JOBS ||--o{ JOB_LOGS : "has logs"
    JOBS ||--o{ JOBS : "recurring template -> occurrences"
    JOBS ||--o| DEAD_LETTER_JOBS : "moves to"
    QUEUES ||--o{ DEAD_LETTER_JOBS : "contains"
    WORKERS ||--o{ JOB_EXECUTIONS : "executes"
    WORKERS ||--o{ WORKER_HEARTBEATS : "reports"
    JOB_EXECUTIONS ||--o{ JOB_LOGS : "has logs"

    USERS {
        uuid id PK
        string email UK
        string hashed_password
        string full_name
        bool is_active
        datetime created_at
    }

    ORGANIZATIONS {
        uuid id PK
        string name
        uuid owner_id FK
        datetime created_at
    }

    ORGANIZATION_MEMBERS {
        uuid id PK
        uuid organization_id FK
        uuid user_id FK
        enum role "admin | member | viewer"
    }

    PROJECTS {
        uuid id PK
        uuid organization_id FK
        string name
        string description
        string api_key UK
        datetime created_at
    }

    RETRY_POLICIES {
        uuid id PK
        string name
        enum strategy "fixed | linear | exponential | none"
        int max_retries
        int base_delay_seconds
        int max_delay_seconds
        float multiplier
    }

    QUEUES {
        uuid id PK
        uuid project_id FK
        string name
        int priority
        int max_concurrency
        bool is_paused
        uuid default_retry_policy_id FK
        datetime created_at
    }

    JOBS {
        uuid id PK
        uuid queue_id FK
        enum type "immediate | delayed | scheduled | recurring | batch"
        string name
        json payload
        enum status "queued|scheduled|claimed|running|completed|failed|retrying|dead_letter|cancelled"
        int priority
        datetime run_at
        string cron_expression
        bool is_recurring_template
        uuid parent_recurring_job_id FK
        uuid batch_id
        uuid retry_policy_id FK
        int max_retries
        int retry_count
        string idempotency_key
        int timeout_seconds
        uuid claimed_by_worker_id FK
        datetime claimed_at
        datetime created_at
        datetime updated_at
    }

    JOB_EXECUTIONS {
        uuid id PK
        uuid job_id FK
        uuid worker_id FK
        int attempt_number
        enum status
        datetime started_at
        datetime finished_at
        int duration_ms
        json result
        text error_message
        text error_stacktrace
    }

    JOB_LOGS {
        uuid id PK
        uuid job_id FK
        uuid execution_id FK
        enum level "debug|info|warning|error"
        text message
        datetime created_at
    }

    DEAD_LETTER_JOBS {
        uuid id PK
        uuid original_job_id FK
        uuid queue_id FK
        string name
        json payload
        text failure_reason
        int total_attempts
        datetime failed_at
        bool replayed
    }

    WORKERS {
        uuid id PK
        string name
        string hostname
        enum status "active|idle|draining|offline"
        int concurrency
        int current_load
        json queues_subscribed
        datetime last_heartbeat_at
        datetime started_at
    }

    WORKER_HEARTBEATS {
        uuid id PK
        uuid worker_id FK
        datetime timestamp
        int active_jobs
        float cpu_usage
        float memory_usage_mb
    }
```

## Key design decisions

**Primary keys.** Every table uses an application-generated UUID (`str(uuid.uuid4())`)
rather than an auto-increment integer. This lets any component (API server,
worker, or a future event producer) mint a valid ID before an INSERT commits,
which matters for idempotency-key checks and for correlating a job across
logs/executions before all writes land.

**Indexing.** The single most important index is
`ix_jobs_claim_scan (queue_id, status, run_at, priority)` on `jobs` — it is
shaped exactly like the worker's claim query's `WHERE`/`ORDER BY`, so claiming
stays an index scan even with millions of historical job rows. Supporting
indexes: `ix_jobs_batch` for batch lookups, `ix_job_executions_job` for the
per-job execution timeline, `ix_job_logs_job_created` for log tailing,
`ix_heartbeats_worker_ts` for the worker health chart, and
`ix_dlq_queue_failed_at` for the DLQ page.

**Normalization.** The schema is in 3NF. `RetryPolicy` is factored out of
`Queue`/`Job` so the same policy can be reused and so a job can override its
queue's default without duplicating the strategy/backoff fields. `JobExecution`
is a separate table from `Job` (1:N) specifically so retry history is never
lost — `Job` holds current state, `JobExecution` holds the append-only attempt
log.

**Cascading.** `ON DELETE CASCADE` is used for strictly-owned children
(Project→Queue→Job→JobExecution/JobLog, Organization→Project,
Organization→OrganizationMember) so deleting a parent can't leave orphaned
rows. `ON DELETE SET NULL` is used for references that should survive their
target's deletion for audit purposes (`Job.claimed_by_worker_id`,
`DeadLetterJob.original_job_id`, `Queue.default_retry_policy_id`) — a DLQ
entry, for instance, must remain readable even if the original job row is
later purged.

**Separating `dead_letter_jobs` from `jobs`.** A job that has exhausted retries
is moved to its own table instead of just being flagged `status='dead_letter'`
and left in `jobs`. This keeps the hot claim-scan index free of permanently-dead
rows that would otherwise accumulate forever and bloat that index.
