"""HTTP entrypoint for the Cadence render worker on Cloud Run.

Cloud Run is request-driven, not a long-lived daemon, so the worker is woken by a
Cloud Scheduler POST to /process (about once a minute). Each call drains the queue —
claim, render, repeat — until it's empty or a time budget elapses, then returns so the
instance can scale back to zero. The whisper model loads lazily, so idle ticks against
an empty queue stay cheap. Run with: uvicorn server:app --host 0.0.0.0 --port $PORT
"""

from __future__ import annotations

import os

from fastapi import FastAPI

from cadence_worker import Worker

app = FastAPI(title="cadence-worker")
_worker: Worker | None = None


def _get_worker() -> Worker:
    global _worker
    if _worker is None:
        _worker = Worker()
    return _worker


@app.get("/healthz")
def healthz() -> dict:
    """Liveness probe — must not construct the Worker (no Supabase round-trip needed)."""
    return {"ok": True}


@app.post("/process")
def process() -> dict:
    """Drain the render queue. Triggered by Cloud Scheduler (and safe to call anytime)."""
    budget = float(os.environ.get("WORKER_DRAIN_BUDGET_SEC", "2700"))
    return _get_worker().drain(budget_sec=budget)
