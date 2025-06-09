"""Utility for marking jobs with stale heartbeats as failed."""

from __future__ import annotations

import logging
from datetime import datetime, UTC, timedelta
from typing import Any, Dict


logger = logging.getLogger(__name__)


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
    stale_count = 0

    jobs = _get_jobs_list(client)

    for job in jobs:
        try:
            if _should_mark_job_stale(job, now, cutoff):
                _mark_job_stale(client, job)
                stale_count += 1
        except AssertionError as e:
            logger.warning(f"Skipping invalid job {job.get('id', 'unknown')}: {e}")
        except Exception as e:
            logger.error(f"Failed to process job {job.get('id', 'unknown')}: {e}")

    return stale_count


def _get_jobs_list(client: Any) -> list[Dict[str, Any]]:
    """Get list of jobs from client."""
    if hasattr(client, "list_jobs"):
        return list(client.list_jobs())
    else:  # pragma: no cover - real client path not under test
        resp = (
            client.supabase.table("jobs").select("*").eq("status", "running").execute()
        )
        return resp.data or []


def _should_mark_job_stale(
    job: Dict[str, Any], now: datetime, cutoff: timedelta
) -> bool:
    """Check if job should be marked stale with fail-fast validation.

    Parameters
    ----------
    job : Dict[str, Any]
        Job data dictionary
    now : datetime
        Current timestamp
    cutoff : timedelta
        Maximum allowed age for heartbeat

    Returns
    -------
    bool
        True if job should be marked stale
    """
    # Fail fast - validate job status
    assert job.get("status") == "running", "Job is not in running status"

    # Fail fast - validate heartbeat exists
    hb_str = job.get("heartbeat")
    assert hb_str, "Job missing heartbeat timestamp"

    # Parse heartbeat with specific error handling
    try:
        hb_time = datetime.fromisoformat(hb_str.replace("Z", ""))
    except ValueError as e:
        assert False, f"Invalid timestamp format '{hb_str}': {e}"

    # Check staleness
    return now - hb_time > cutoff


def _mark_job_stale(client: Any, job: Dict[str, Any]) -> None:
    """Mark a job as failed due to stale heartbeat.

    Parameters
    ----------
    client : Any
        Client implementing update_job()
    job : Dict[str, Any]
        Job data dictionary containing 'id' key
    """
    client.update_job(job["id"], {"status": "failed", "status_reason": "manager_died"})


__all__ = ["reap_stale_jobs"]
