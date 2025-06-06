"""Command line interface for the experiment manager."""

from __future__ import annotations

import argparse
import os
from typing import Sequence

from dotenv import load_dotenv

from dr_exp.manage.manager_logic import (
    Manager,
    discover_gpus,
    run_worker_main,
)
from dr_exp.utils.job_reaper import reap_stale_jobs
from dr_exp.utils.storage_cleanup import cleanup_uploaded_runs
from dr_exp.utils.jobdb_factory import get_job_db_client
from . import upload_configs, run_one

load_dotenv()


def build_arg_parser() -> argparse.ArgumentParser:
    """Return the top-level CLI argument parser."""
    parser = argparse.ArgumentParser(
        description="Experiment manager command line interface"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser(
        "run",
        help="Start the manager process",
        description="Launch the manager which supervises worker processes",
    )
    run_parser.add_argument(
        "--gpus-per-node",
        type=int,
        default=1,
        help="Number of GPUs available on this node",
    )
    run_parser.add_argument(
        "--workers-per-gpu",
        type=int,
        default=1,
        help="Number of worker processes to spawn per GPU",
    )
    run_parser.add_argument(
        "--heartbeat-interval",
        type=int,
        default=10,
        help="Seconds between heartbeat checks",
    )
    run_parser.add_argument(
        "--idle-timeout-mins",
        type=int,
        default=30,
        help="Minutes of inactivity before the manager shuts down",
    )

    dg_parser = subparsers.add_parser(
        "discover-gpus",
        help="List visible GPU IDs",
        description="Print GPU IDs that the manager would use",
    )
    dg_parser.add_argument(
        "--gpus-per-node",
        type=int,
        default=1,
        help="Total GPUs on the node if CUDA_VISIBLE_DEVICES is not set",
    )

    worker_parser = subparsers.add_parser(
        "run-worker",
        help="Run a single worker process",
        description="Execute a worker directly using run_worker_main",
    )
    worker_parser.add_argument("worker_id", help="Unique worker identifier")
    worker_parser.add_argument("work_dir", help="Working directory for temporary files")

    reap_parser = subparsers.add_parser(
        "reap-stale-jobs",
        help="Mark running jobs with stale heartbeats as failed",
        description="Update stale running jobs to failed status",
    )
    reap_parser.add_argument(
        "--max-age-mins",
        type=int,
        default=60,
        help="Heartbeat age threshold in minutes",
    )
    reap_parser.add_argument(
        "--base-path", default=".", help="Base path for LocalDBClient"
    )

    cleanup_parser = subparsers.add_parser(
        "cleanup-run-data",
        help="Delete run directories that have finished uploading",
        description="Remove run_* folders containing finished.flag",
    )
    cleanup_parser.add_argument(
        "--base-path", default=".", help="Base path for SupabaseMockClient"
    )
    upload_parser = subparsers.add_parser(
        "upload-configs",
        help="Generate and upload sweep configs",
        description="Generate configs and upload them using Supabase",
    )
    upload_configs.add_arguments(upload_parser)

    # Priority management commands
    priority_parser = subparsers.add_parser(
        "list-jobs",
        help="List jobs ordered by priority",
        description="Display jobs in priority order with status filtering",
    )
    priority_parser.add_argument(
        "--status",
        nargs="*",
        default=["queued"],
        help="Filter by job status (default: queued)",
    )
    priority_parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum number of jobs to display (default: 20)",
    )
    priority_parser.add_argument(
        "--base-path", default=".", help="Base path for database client"
    )

    boost_parser = subparsers.add_parser(
        "boost-priority",
        help="Boost the priority of a specific job",
        description="Increase job priority by specified amount",
    )
    boost_parser.add_argument("job_id", help="Job ID to boost")
    boost_parser.add_argument(
        "--amount",
        type=int,
        default=100,
        help="Priority boost amount (default: 100)",
    )
    boost_parser.add_argument(
        "--base-path", default=".", help="Base path for database client"
    )

    set_priority_parser = subparsers.add_parser(
        "set-priority",
        help="Set the priority of a specific job",
        description="Set job priority to exact value",
    )
    set_priority_parser.add_argument("job_id", help="Job ID to update")
    set_priority_parser.add_argument("priority", type=int, help="New priority value (0-1000)")
    set_priority_parser.add_argument(
        "--reason",
        help="Optional reason for priority change",
    )
    set_priority_parser.add_argument(
        "--base-path", default=".", help="Base path for database client"
    )

    # Run one command
    run_one_parser = subparsers.add_parser(
        "run-one",
        help="Reserve and run a single high-priority job immediately",
        description="Create a reserved high-priority job and execute it immediately",
    )
    run_one.add_arguments(run_one_parser)

    return parser


def _cmd_run(args: argparse.Namespace) -> None:
    gpus = discover_gpus(args.gpus_per_node)
    slurm_job_id = os.environ.get("SLURM_JOB_ID", str(os.getpid()))
    base_dir = os.path.join("./manager_runs", f"job_{slurm_job_id}")
    mgr = Manager(
        gpus=gpus,
        workers_per_gpu=args.workers_per_gpu,
        heartbeat_interval=args.heartbeat_interval,
        idle_timeout_mins=args.idle_timeout_mins,
        base_dir=base_dir,
    )
    mgr.run()


def _cmd_discover_gpus(args: argparse.Namespace) -> None:
    gpus = discover_gpus(args.gpus_per_node)
    for g in gpus:
        print(g)


def _cmd_run_worker(args: argparse.Namespace) -> None:
    run_worker_main(worker_id=args.worker_id, work_dir=args.work_dir)


def _cmd_reap_stale_jobs(args: argparse.Namespace) -> None:
    client = get_job_db_client()
    count = reap_stale_jobs(client, args.max_age_mins)
    print(f"Marked {count} stale job(s) as failed")


def _cmd_cleanup_run_data(args: argparse.Namespace) -> None:
    client = get_job_db_client()
    count = cleanup_uploaded_runs(client)
    print(f"Removed {count} run directory(s)")


def _cmd_list_jobs(args: argparse.Namespace) -> None:
    """List jobs ordered by priority."""
    client = get_job_db_client()
    jobs = client.list_jobs_by_priority(status_filter=args.status, limit=args.limit)
    
    if not jobs:
        print("No jobs found matching criteria")
        return
    
    print(f"{'Job ID':<40} {'Priority':<8} {'Status':<10} {'Created':<20}")
    print("-" * 80)
    for job in jobs:
        job_id = str(job.get("id", ""))[:36]
        priority = job.get("priority", 100)
        status = job.get("status", "unknown")
        created = job.get("created_at", "")[:19] if job.get("created_at") else ""
        print(f"{job_id:<40} {priority:<8} {status:<10} {created:<20}")


def _cmd_boost_priority(args: argparse.Namespace) -> None:
    """Boost job priority by specified amount."""
    client = get_job_db_client()
    result = client.boost_job_priority(args.job_id, boost_amount=args.amount)
    
    if result.get("success"):
        print(f"Priority boosted: {result['old_priority']} -> {result['new_priority']}")
    else:
        print(f"Failed to boost priority: {result.get('message', 'Unknown error')}")


def _cmd_set_priority(args: argparse.Namespace) -> None:
    """Set job priority to exact value."""
    client = get_job_db_client()
    result = client.update_job_priority(args.job_id, args.priority, reason=args.reason)
    
    if result.get("success"):
        print(f"Priority updated to {args.priority}")
        if args.reason:
            print(f"Reason: {args.reason}")
    else:
        print(f"Failed to update priority: {result.get('message', 'Unknown error')}")


def main(argv: Sequence[str] | None = None) -> None:
    """Entry point for the CLI."""
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    if args.command == "run":
        _cmd_run(args)
    elif args.command == "discover-gpus":
        _cmd_discover_gpus(args)
    elif args.command == "run-worker":
        _cmd_run_worker(args)
    elif args.command == "reap-stale-jobs":
        _cmd_reap_stale_jobs(args)
    elif args.command == "cleanup-run-data":
        _cmd_cleanup_run_data(args)
    elif args.command == "upload-configs":
        jobs = upload_configs.run(args)
        print(f"Created {len(jobs)} job(s)")
    elif args.command == "list-jobs":
        _cmd_list_jobs(args)
    elif args.command == "boost-priority":
        _cmd_boost_priority(args)
    elif args.command == "set-priority":
        _cmd_set_priority(args)
    elif args.command == "run-one":
        status = run_one.run(args)
        exit_code = 0 if status in ["completed", "success"] else 1
        exit(exit_code)
    else:  # pragma: no cover - fallback
        parser.print_help()


__all__ = ["main", "build_arg_parser"]
