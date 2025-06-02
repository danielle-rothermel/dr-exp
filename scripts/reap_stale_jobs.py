import argparse
from datetime import datetime, UTC, timedelta
from typing import Iterable, Optional, Dict, Any

from dr_exp.core.client_provider import get_supabase_client


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


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Mark stale running jobs as failed")
    parser.add_argument(
        "--max-age-mins",
        type=int,
        default=60,
        help="Heartbeat age threshold in minutes",
    )
    parser.add_argument(
        "--base-path", default=".", help="Base path for SupabaseMockClient"
    )
    return parser


def main(argv: Optional[list[str]] = None) -> None:
    args = build_arg_parser().parse_args(argv)
    client = get_supabase_client(base_path=args.base_path)
    count = reap_stale_jobs(client, args.max_age_mins)
    print(f"Marked {count} stale job(s) as failed")


if __name__ == "__main__":
    main()

__all__ = ["reap_stale_jobs", "build_arg_parser", "main"]
