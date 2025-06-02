"""Utility for marking jobs with stale heartbeats as failed."""

from __future__ import annotations

from datetime import datetime, UTC, timedelta
from typing import Any, Dict, Iterable


def reap_stale_jobs(client: Any, max_age_mins: int) -> int:
    """Mark running jobs with stale heartbeats as failed.

    Parameters
    ----------
    client : object
        Client implementing ``list_jobs()`` and ``update_job()``.
    max_age_mins : int
        Maximum allowed age of the heartbeat in minutes.

    Returns
    -------
    int
        Number of jobs updated.
    """
    now = datetime.now(UTC)
    cutoff = timedelta(minutes=max_age_mins)
    stale = 0

    jobs: Iterable[Dict[str, Any]]
    if hasattr(client, "list_jobs"):
        jobs = client.list_jobs()
    else:  # pragma: no cover - real client path not under test
        resp = (
            client.supabase.table("jobs").select("*").eq("status", "running").execute()
        )
        jobs = resp.data or []

    for job in jobs:
        if job.get("status") != "running":
            continue
        hb_str = job.get("heartbeat")
        if not hb_str:
            continue
        try:
            hb_time = datetime.fromisoformat(hb_str.replace("Z", ""))
        except ValueError:
            continue
        if now - hb_time > cutoff:
            client.update_job(
                job["id"], {"status": "failed", "status_reason": "manager_died"}
            )
            stale += 1
    return stale


__all__ = ["reap_stale_jobs"]
