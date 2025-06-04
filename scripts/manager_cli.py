"""Command line interface for the experiment manager."""

from __future__ import annotations

import argparse
import os
from typing import Sequence

from dotenv import load_dotenv

from dr_exp.manage.manager_logic import Manager, discover_gpus, run_worker_main
from dr_exp.utils.job_reaper import reap_stale_jobs
from dr_exp.utils.storage_cleanup import cleanup_uploaded_runs
from dr_exp.utils.jobdb_factory import get_supabase_client
from scripts import upload_configs

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
    client = get_supabase_client(base_path=args.base_path)
    count = reap_stale_jobs(client, args.max_age_mins)
    print(f"Marked {count} stale job(s) as failed")


def _cmd_cleanup_run_data(args: argparse.Namespace) -> None:
    client = get_supabase_client(base_path=args.base_path)
    count = cleanup_uploaded_runs(client)
    print(f"Removed {count} run directory(s)")


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
    else:  # pragma: no cover - fallback
        parser.print_help()


__all__ = ["main", "build_arg_parser"]
