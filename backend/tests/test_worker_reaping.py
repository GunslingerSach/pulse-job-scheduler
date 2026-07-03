from datetime import datetime, timedelta, timezone

from app import models
from app.services import job_service


def test_promote_scheduled_jobs_flips_due_jobs_to_queued(db, project_and_queue):
    _, queue = project_and_queue
    due = models.Job(queue_id=queue.id, name="due", type=models.JobType.SCHEDULED, payload={},
                      status=models.JobStatus.SCHEDULED,
                      run_at=datetime.now(timezone.utc) - timedelta(seconds=1))
    not_due = models.Job(queue_id=queue.id, name="not-due", type=models.JobType.SCHEDULED, payload={},
                          status=models.JobStatus.SCHEDULED,
                          run_at=datetime.now(timezone.utc) + timedelta(hours=1))
    db.add_all([due, not_due])
    db.commit()

    promoted = job_service.promote_scheduled_jobs(db)

    db.refresh(due)
    db.refresh(not_due)
    assert promoted == 1
    assert due.status == models.JobStatus.QUEUED
    assert not_due.status == models.JobStatus.SCHEDULED


def test_reap_stale_workers_requeues_their_jobs(db, project_and_queue):
    _, queue = project_and_queue
    dead_worker = models.Worker(name="dead", status=models.WorkerStatus.ACTIVE,
                                 last_heartbeat_at=datetime.now(timezone.utc) - timedelta(minutes=5))
    db.add(dead_worker)
    db.commit()

    orphaned = models.Job(queue_id=queue.id, name="orphan", type=models.JobType.IMMEDIATE, payload={},
                           status=models.JobStatus.RUNNING, claimed_by_worker_id=dead_worker.id)
    db.add(orphaned)
    db.commit()

    reaped = job_service.reap_stale_workers(db, offline_threshold_seconds=20)

    db.refresh(dead_worker)
    db.refresh(orphaned)
    assert dead_worker.id in reaped
    assert dead_worker.status == models.WorkerStatus.OFFLINE
    assert orphaned.status == models.JobStatus.QUEUED
    assert orphaned.claimed_by_worker_id is None
