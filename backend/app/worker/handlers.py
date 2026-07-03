"""
Job handlers. A handler is any callable registered under a job `name`; it
receives the job payload and returns a JSON-serializable result, or raises to
signal failure (which the worker turns into a retry/DLQ transition).

This is intentionally the extension point for the whole system: adding a new
kind of background job means writing one function and registering it here,
nothing else in the platform needs to change.
"""

import asyncio
import random
from typing import Callable, Awaitable, Any

HANDLERS: dict[str, Callable[[dict], Awaitable[Any]]] = {}


def handler(name: str):
    def decorator(fn):
        HANDLERS[name] = fn
        return fn
    return decorator


@handler("send_email")
async def send_email(payload: dict) -> dict:
    await asyncio.sleep(0.5)
    return {"sent_to": payload.get("to"), "subject": payload.get("subject")}


@handler("generate_report")
async def generate_report(payload: dict) -> dict:
    await asyncio.sleep(2)
    return {"report_id": payload.get("report_id"), "rows_processed": random.randint(100, 5000)}


@handler("resize_image")
async def resize_image(payload: dict) -> dict:
    await asyncio.sleep(1)
    return {"url": payload.get("url"), "sizes": ["thumb", "medium", "large"]}


@handler("flaky_demo_job")
async def flaky_demo_job(payload: dict) -> dict:
    """Fails ~50% of the time; useful for exercising the retry/backoff/DLQ
    path end to end from the demo dashboard."""
    await asyncio.sleep(0.3)
    if random.random() < 0.5:
        raise RuntimeError("Simulated transient failure")
    return {"ok": True}


async def execute(job_name: str, payload: dict) -> Any:
    fn = HANDLERS.get(job_name)
    if fn is None:
        # Unknown job names still "succeed" with a no-op so the demo/dashboard
        # isn't blocked on writing a handler for every ad-hoc job name typed
        # into the UI.
        await asyncio.sleep(0.2)
        return {"note": f"no handler registered for '{job_name}', treated as no-op"}
    return await fn(payload)
