from app import models
from app.services import job_service


def make_job(db, queue, name="job", priority=0, status=models.JobStatus.QUEUED, run_at=None):
    job = models.Job(queue_id=queue.id, name=name, type=models.JobType.IMMEDIATE, payload={},
                      status=status, priority=priority, run_at=run_at,
                      retry_policy_id=queue.default_retry_policy_id, max_retries=2)
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def test_claim_respects_priority_order(db, project_and_queue, worker):
    _, queue = project_and_queue
    low = make_job(db, queue, name="low", priority=0)
    high = make_job(db, queue, name="high", priority=10)

    claimed = job_service.claim_jobs(db, worker, [queue.id], max_jobs=1)

    assert len(claimed) == 1
    assert claimed[0].id == high.id


def test_claim_respects_queue_concurrency_limit(db, project_and_queue, worker):
    """queue.max_concurrency=2 (see fixture); 5 queued jobs, 0 running -> only 2 claimable."""
    _, queue = project_and_queue
    for i in range(5):
        make_job(db, queue, name=f"job-{i}")

    claimed = job_service.claim_jobs(db, worker, [queue.id], max_jobs=10)

    assert len(claimed) == 2
    for job in claimed:
        assert job.status == models.JobStatus.CLAIMED
        assert job.claimed_by_worker_id == worker.id


def test_claim_does_not_double_claim_already_claimed_jobs(db, project_and_queue, worker):
    _, queue = project_and_queue
    make_job(db, queue, name="only-job")

    first = job_service.claim_jobs(db, worker, [queue.id], max_jobs=5)
    second = job_service.claim_jobs(db, worker, [queue.id], max_jobs=5)

    assert len(first) == 1
    assert len(second) == 0  # already CLAIMED, not QUEUED/RETRYING anymore


def test_claim_ignores_future_scheduled_jobs(db, project_and_queue, worker):
    from datetime import datetime, timedelta, timezone
    _, queue = project_and_queue
    future_job = make_job(db, queue, name="future", status=models.JobStatus.SCHEDULED,
                           run_at=datetime.now(timezone.utc) + timedelta(hours=1))

    claimed = job_service.claim_jobs(db, worker, [queue.id], max_jobs=5)

    assert claimed == []


def test_claim_ignores_paused_queue(db, project_and_queue, worker):
    _, queue = project_and_queue
    queue.is_paused = True
    db.commit()
    make_job(db, queue, name="job")

    claimed = job_service.claim_jobs(db, worker, [queue.id], max_jobs=5)

    assert claimed == []
