from app import models
from app.services import job_service


def make_running_job_with_execution(db, queue, worker, max_retries=2):
    job = models.Job(queue_id=queue.id, name="flaky", type=models.JobType.IMMEDIATE, payload={},
                      status=models.JobStatus.RUNNING, retry_policy_id=queue.default_retry_policy_id,
                      max_retries=max_retries, claimed_by_worker_id=worker.id)
    db.add(job)
    db.commit()
    db.refresh(job)
    execution = job_service.start_execution(db, job, worker)
    return job, execution


def test_failed_job_within_retry_budget_is_requeued_as_retrying(db, project_and_queue, worker):
    _, queue = project_and_queue
    job, execution = make_running_job_with_execution(db, queue, worker, max_retries=2)

    job_service.fail_execution(db, job, execution, "boom")

    assert job.status == models.JobStatus.RETRYING
    assert job.retry_count == 1
    assert job.run_at is not None


def test_job_moves_to_dead_letter_after_exhausting_retries(db, project_and_queue, worker):
    _, queue = project_and_queue
    job, execution = make_running_job_with_execution(db, queue, worker, max_retries=1)

    # attempt 1 fails -> retry_count=1 <= max_retries=1 -> RETRYING
    job_service.fail_execution(db, job, execution, "boom 1")
    assert job.status == models.JobStatus.RETRYING

    # simulate second attempt failing too -> retry_count=2 > max_retries=1 -> DEAD_LETTER
    job.status = models.JobStatus.RUNNING
    db.commit()
    execution2 = job_service.start_execution(db, job, worker)
    job_service.fail_execution(db, job, execution2, "boom 2")

    assert job.status == models.JobStatus.DEAD_LETTER
    dlq_entries = db.query(models.DeadLetterJob).filter(models.DeadLetterJob.original_job_id == job.id).all()
    assert len(dlq_entries) == 1
    assert dlq_entries[0].total_attempts == 2


def test_exponential_backoff_delay_grows():
    policy = models.RetryPolicy(name="exp", strategy=models.RetryStrategyType.EXPONENTIAL,
                                 base_delay_seconds=5, multiplier=2.0, max_delay_seconds=1000)
    assert policy.compute_delay(1) == 5
    assert policy.compute_delay(2) == 10
    assert policy.compute_delay(3) == 20


def test_exponential_backoff_caps_at_max_delay():
    policy = models.RetryPolicy(name="exp", strategy=models.RetryStrategyType.EXPONENTIAL,
                                 base_delay_seconds=100, multiplier=10.0, max_delay_seconds=500)
    assert policy.compute_delay(5) == 500


def test_linear_backoff():
    policy = models.RetryPolicy(name="lin", strategy=models.RetryStrategyType.LINEAR,
                                 base_delay_seconds=10, max_delay_seconds=1000)
    assert policy.compute_delay(1) == 10
    assert policy.compute_delay(3) == 30


def test_fixed_backoff():
    policy = models.RetryPolicy(name="fixed", strategy=models.RetryStrategyType.FIXED,
                                 base_delay_seconds=15, max_delay_seconds=1000)
    assert policy.compute_delay(1) == 15
    assert policy.compute_delay(9) == 15


def test_completed_job_clears_worker_assignment(db, project_and_queue, worker):
    _, queue = project_and_queue
    job, execution = make_running_job_with_execution(db, queue, worker)

    job_service.complete_execution(db, job, execution, {"ok": True})

    assert job.status == models.JobStatus.COMPLETED
    assert job.claimed_by_worker_id is None
    assert execution.result == {"ok": True}
