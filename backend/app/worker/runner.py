"""
Standalone worker process.

Run one or many of these (same machine or different machines) against the
same API server:

    python -m app.worker.runner --name worker-1 --concurrency 5

Each worker:
  1. Registers itself with the API (gets a worker_id).
  2. Loops: claims up to (concurrency - in_flight) jobs via the atomic
     claim endpoint, and starts executing each concurrently as an asyncio
     task bounded by a semaphore.
  3. Sends a heartbeat on a fixed interval, independent of the claim loop,
     so a worker busy running long jobs still reports liveness.
  4. On SIGINT/SIGTERM, stops claiming new work, marks itself DRAINING, and
     waits for in-flight jobs to finish (or a timeout) before exiting - a
     graceful shutdown that never abandons a job mid-execution.
"""

import argparse
import asyncio
import logging
import signal
import socket
import time
import traceback

import httpx

from app.worker.handlers import execute

logger = logging.getLogger("worker")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


class WorkerRunner:
    def __init__(self, api_base: str, api_key: str, name: str, concurrency: int, poll_interval: float):
        self.api_base = api_base.rstrip("/")
        self.api_key = api_key
        self.name = name
        self.concurrency = concurrency
        self.poll_interval = poll_interval
        self.worker_id: str | None = None
        self.in_flight = 0
        self.shutting_down = False
        self.client = httpx.AsyncClient(base_url=self.api_base, headers={"x-api-key": api_key}, timeout=30)
        self._tasks: set[asyncio.Task] = set()

    async def register(self):
        resp = await self.client.post("/api/v1/workers/register", json={
            "name": self.name, "hostname": socket.gethostname(), "concurrency": self.concurrency,
        })
        resp.raise_for_status()
        self.worker_id = resp.json()["id"]
        logger.info(f"Registered as worker {self.worker_id}")

    async def heartbeat_loop(self, interval: float):
        while not self.shutting_down:
            try:
                await self.client.post(f"/api/v1/workers/{self.worker_id}/heartbeat",
                                        json={"active_jobs": self.in_flight})
            except Exception:
                logger.warning("heartbeat failed", exc_info=True)
            await asyncio.sleep(interval)

    async def claim_loop(self):
        while not self.shutting_down:
            capacity = self.concurrency - self.in_flight
            if capacity <= 0:
                await asyncio.sleep(self.poll_interval)
                continue
            try:
                resp = await self.client.post(f"/api/v1/workers/{self.worker_id}/claim",
                                               json={"worker_id": self.worker_id, "max_jobs": capacity})
                resp.raise_for_status()
                jobs = resp.json()
            except Exception:
                logger.warning("claim request failed", exc_info=True)
                jobs = []

            for job in jobs:
                task = asyncio.create_task(self._run_job(job))
                self._tasks.add(task)
                task.add_done_callback(self._tasks.discard)

            if not jobs:
                await asyncio.sleep(self.poll_interval)

    async def _run_job(self, job: dict):
        self.in_flight += 1
        job_id = job["id"]
        try:
            start_resp = await self.client.post(f"/api/v1/workers/{self.worker_id}/jobs/{job_id}/start")
            start_resp.raise_for_status()
            execution_id = start_resp.json()["id"]

            timeout = job.get("timeout_seconds", 300)
            try:
                result = await asyncio.wait_for(execute(job["name"], job["payload"]), timeout=timeout)
                await self.client.post(
                    f"/api/v1/workers/{self.worker_id}/jobs/{job_id}/complete",
                    params={"execution_id": execution_id}, json=result if isinstance(result, dict) else {"result": result},
                )
                logger.info(f"Job {job_id} ({job['name']}) completed")
            except asyncio.TimeoutError:
                await self.client.post(
                    f"/api/v1/workers/{self.worker_id}/jobs/{job_id}/fail",
                    params={"execution_id": execution_id, "error_message": f"Timed out after {timeout}s"},
                )
                logger.warning(f"Job {job_id} timed out")
            except Exception as e:
                await self.client.post(
                    f"/api/v1/workers/{self.worker_id}/jobs/{job_id}/fail",
                    params={"execution_id": execution_id, "error_message": str(e),
                            "stacktrace": traceback.format_exc()},
                )
                logger.warning(f"Job {job_id} failed: {e}")
        except Exception:
            logger.exception(f"Unexpected error handling job {job_id}")
        finally:
            self.in_flight -= 1

    async def run(self):
        await self.register()
        hb_task = asyncio.create_task(self.heartbeat_loop(interval=5.0))
        claim_task = asyncio.create_task(self.claim_loop())

        loop = asyncio.get_event_loop()
        stop_event = asyncio.Event()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, stop_event.set)
            except NotImplementedError:
                pass  # signal handlers aren't available on some platforms (e.g. Windows)

        await stop_event.wait()
        logger.info("Shutdown signal received, draining...")
        self.shutting_down = True
        try:
            await self.client.post(f"/api/v1/workers/{self.worker_id}/drain")
        except Exception:
            pass

        claim_task.cancel()
        deadline = time.monotonic() + 60
        while self._tasks and time.monotonic() < deadline:
            logger.info(f"Waiting for {len(self._tasks)} in-flight job(s) to finish...")
            await asyncio.sleep(1)

        hb_task.cancel()
        try:
            await self.client.post(f"/api/v1/workers/{self.worker_id}/shutdown")
        except Exception:
            pass
        await self.client.aclose()
        logger.info("Worker shut down cleanly")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-base", default="http://localhost:8000")
    parser.add_argument("--api-key", required=True)
    parser.add_argument("--name", default=f"worker-{socket.gethostname()}")
    parser.add_argument("--concurrency", type=int, default=5)
    parser.add_argument("--poll-interval", type=float, default=1.0)
    args = parser.parse_args()

    runner = WorkerRunner(args.api_base, args.api_key, args.name, args.concurrency, args.poll_interval)
    asyncio.run(runner.run())


if __name__ == "__main__":
    main()
