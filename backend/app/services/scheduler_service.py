import asyncio
import logging

from app.database import SessionLocal
from app.config import settings
from app.services.job_service import promote_scheduled_jobs, reap_stale_workers

logger = logging.getLogger("scheduler")


async def scheduler_loop():
    """Runs in-process inside the API server. In a larger deployment this
    would be its own small service so it can be scaled/restarted
    independently of the HTTP API, but a single leader is enough here since
    both operations it performs (UPDATE ... WHERE run_at <= now(), and
    reaping stale workers) are idempotent and safe to run concurrently from
    more than one instance."""
    while True:
        try:
            db = SessionLocal()
            try:
                promoted = promote_scheduled_jobs(db)
                reaped = reap_stale_workers(db, settings.worker_offline_threshold_seconds)
                if promoted:
                    logger.info(f"Promoted {promoted} scheduled job(s) to queued")
                if reaped:
                    logger.info(f"Reaped {len(reaped)} stale worker(s)")
            finally:
                db.close()
        except Exception:
            logger.exception("scheduler_loop iteration failed")
        await asyncio.sleep(settings.worker_poll_interval_seconds)
