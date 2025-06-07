"""Command line interface for the experiment manager."""

from __future__ import annotations

import argparse
import sys
from typing import Sequence

from dotenv import load_dotenv

from dr_exp.utils.factory import create_system, SystemConfig
from dr_exp.utils.job_reaper import reap_stale_jobs
from dr_exp.utils.storage_cleanup import cleanup_uploaded_runs
from dr_exp.utils.gpu_discovery import discover_gpus
from dr_exp.utils.cli_config import CLI_DEFAULTS
from dr_exp.utils.cli_validation import (
    ValidationError, validate_priority, validate_job_id, 
    validate_positive_int, validate_job_statuses, validate_config_overrides
)
from dr_exp.utils.run_one_config import create_run_one_job, get_default_config_path
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
        default=CLI_DEFAULTS.GPUS_PER_NODE,
        help=f"Number of GPUs available on this node (default: {CLI_DEFAULTS.GPUS_PER_NODE})",
    )
    run_parser.add_argument(
        "--workers-per-gpu",
        type=int,
        default=CLI_DEFAULTS.WORKERS_PER_GPU,
        help=f"Number of worker processes to spawn per GPU (default: {CLI_DEFAULTS.WORKERS_PER_GPU})",
    )
    run_parser.add_argument(
        "--heartbeat-timeout",
        type=int,
        default=CLI_DEFAULTS.HEARTBEAT_TIMEOUT,
        help=f"Worker heartbeat timeout in seconds (default: {CLI_DEFAULTS.HEARTBEAT_TIMEOUT})",
    )
    run_parser.add_argument(
        "--idle-timeout-mins",
        type=int,
        default=CLI_DEFAULTS.IDLE_TIMEOUT_MINS,
        help=f"Minutes of inactivity before the manager shuts down (default: {CLI_DEFAULTS.IDLE_TIMEOUT_MINS})",
    )

    dg_parser = subparsers.add_parser(
        "discover-gpus",
        help="List visible GPU IDs",
        description="Print GPU IDs that the manager would use",
    )
    dg_parser.add_argument(
        "--gpus-per-node",
        type=int,
        default=CLI_DEFAULTS.GPUS_PER_NODE,
        help=f"Total GPUs on the node if CUDA_VISIBLE_DEVICES is not set (default: {CLI_DEFAULTS.GPUS_PER_NODE})",
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
        default=CLI_DEFAULTS.DEFAULT_MAX_AGE_MINS,
        help=f"Heartbeat age threshold in minutes (default: {CLI_DEFAULTS.DEFAULT_MAX_AGE_MINS})",
    )

    cleanup_parser = subparsers.add_parser(
        "cleanup-run-data",
        help="Delete run directories that have finished uploading",
        description="Remove run_* folders containing finished.flag",
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
        default=CLI_DEFAULTS.DEFAULT_JOB_STATUS,
        help=f"Filter by job status (default: {CLI_DEFAULTS.DEFAULT_JOB_STATUS})",
    )
    priority_parser.add_argument(
        "--limit",
        type=int,
        default=CLI_DEFAULTS.DEFAULT_JOB_LIMIT,
        help=f"Maximum number of jobs to display (default: {CLI_DEFAULTS.DEFAULT_JOB_LIMIT})",
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
        default=CLI_DEFAULTS.PRIORITY_BOOST_AMOUNT,
        help=f"Priority boost amount (default: {CLI_DEFAULTS.PRIORITY_BOOST_AMOUNT})",
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

    # Run one command
    run_one_parser = subparsers.add_parser(
        "run-one",
        help="Reserve and run a single high-priority job immediately",
        description="Create a reserved high-priority job and execute it immediately",
    )
    run_one_parser.add_argument(
        "--overrides", default="", help="Hydra-style config overrides (e.g., 'model=resnet,lr=0.001')"
    )
    run_one_parser.add_argument(
        "--priority", type=int, default=CLI_DEFAULTS.RUN_ONE_PRIORITY, 
        help=f"Job priority (default: {CLI_DEFAULTS.RUN_ONE_PRIORITY})"
    )
    run_one_parser.add_argument(
        "--config-path", default=get_default_config_path(),
        help="Path to config directory (default: auto-detected)"
    )
    run_one_parser.add_argument(
        "--config-name", default="config.yaml",
        help="Config file name (default: config.yaml)"
    )

    return parser


def _cmd_run(args: argparse.Namespace) -> None:
    """Run the manager."""
    try:
        # Validate inputs
        validate_positive_int(args.gpus_per_node, "gpus-per-node")
        validate_positive_int(args.workers_per_gpu, "workers-per-gpu")
        validate_positive_int(args.heartbeat_timeout, "heartbeat-timeout")
        validate_positive_int(args.idle_timeout_mins, "idle-timeout-mins")
        
        # Discover GPUs
        gpus = discover_gpus(args.gpus_per_node)
        
        # Create system configuration
        system_config = SystemConfig(
            gpus=gpus,
            workers_per_gpu=args.workers_per_gpu,
            heartbeat_timeout=args.heartbeat_timeout,
            idle_timeout_mins=args.idle_timeout_mins,
        )
        
        # Create and run manager
        system = create_system(system_config)
        manager = system.create_manager()
        manager.run()
        
    except ValidationError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Failed to run manager: {e}", file=sys.stderr)
        sys.exit(1)


def _cmd_discover_gpus(args: argparse.Namespace) -> None:
    """Discover and list available GPUs."""
    try:
        validate_positive_int(args.gpus_per_node, "gpus-per-node")
        gpus = discover_gpus(args.gpus_per_node)
        for g in gpus:
            print(g)
    except ValidationError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Failed to discover GPUs: {e}", file=sys.stderr)
        sys.exit(1)


def _cmd_run_worker(args: argparse.Namespace) -> None:
    """Run a worker."""
    try:
        # Basic validation
        if not args.worker_id.strip():
            raise ValidationError("Worker ID cannot be empty")
        if not args.work_dir.strip():
            raise ValidationError("Work directory cannot be empty")
            
        system = create_system()
        status = system.run_worker(
            worker_id=args.worker_id,
            work_dir=args.work_dir
        )
        print(f"Worker completed with status: {status}")
        
        # Set exit code based on status
        if status not in ["completed", "success"]:
            sys.exit(1)
            
    except ValidationError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Failed to run worker: {e}", file=sys.stderr)
        sys.exit(1)


def _cmd_reap_stale_jobs(args: argparse.Namespace) -> None:
    """Mark stale jobs as failed."""
    try:
        validate_positive_int(args.max_age_mins, "max-age-mins")
        
        system = create_system()
        client = system.job_db
        count = reap_stale_jobs(client, args.max_age_mins)
        print(f"Marked {count} stale job(s) as failed")
        
    except ValidationError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Failed to reap stale jobs: {e}", file=sys.stderr)
        sys.exit(1)


def _cmd_cleanup_run_data(args: argparse.Namespace) -> None:
    """Clean up uploaded run data."""
    try:
        system = create_system()
        client = system.job_db
        count = cleanup_uploaded_runs(client)
        print(f"Removed {count} run directory(s)")
        
    except Exception as e:
        print(f"Failed to cleanup run data: {e}", file=sys.stderr)
        sys.exit(1)


def _cmd_list_jobs(args: argparse.Namespace) -> None:
    """List jobs ordered by priority."""
    try:
        validate_job_statuses(args.status)
        validate_positive_int(args.limit, "limit")
        
        system = create_system()
        client = system.job_db
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
            
    except ValidationError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Failed to list jobs: {e}", file=sys.stderr)
        sys.exit(1)


def _cmd_boost_priority(args: argparse.Namespace) -> None:
    """Boost job priority by specified amount."""
    try:
        validate_job_id(args.job_id)
        validate_positive_int(args.amount, "amount")
        
        system = create_system()
        client = system.job_db
        result = client.boost_job_priority(args.job_id, boost_amount=args.amount)
        
        if result.get("success"):
            print(f"Priority boosted: {result['old_priority']} -> {result['new_priority']}")
        else:
            print(f"Failed to boost priority: {result.get('message', 'Unknown error')}")
            sys.exit(1)
            
    except ValidationError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Failed to boost priority: {e}", file=sys.stderr)
        sys.exit(1)


def _cmd_set_priority(args: argparse.Namespace) -> None:
    """Set job priority to exact value."""
    try:
        validate_job_id(args.job_id)
        validate_priority(args.priority)
        
        system = create_system()
        client = system.job_db
        result = client.update_job_priority(args.job_id, args.priority, reason=args.reason)
        
        if result.get("success"):
            print(f"Priority updated to {args.priority}")
            if args.reason:
                print(f"Reason: {args.reason}")
        else:
            print(f"Failed to update priority: {result.get('message', 'Unknown error')}")
            sys.exit(1)
            
    except ValidationError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Failed to set priority: {e}", file=sys.stderr)
        sys.exit(1)


def _cmd_run_one(args: argparse.Namespace) -> str:
    """Create and immediately run a high-priority job."""
    try:
        validate_priority(args.priority)
        overrides = validate_config_overrides(args.overrides)
        
        system = create_system()
        client = system.job_db
        
        # Create job using proper config generation
        job = create_run_one_job(
            client=client,
            base_config_path=args.config_path,
            config_name=args.config_name,
            overrides=overrides,
            priority=args.priority
        )
        print(f"Created job {job['id']} with priority {args.priority}")
        
        # Run worker targeting this specific job
        status = system.run_worker(
            worker_id="run_one_worker",
            target_job_id=job["id"]
        )
        print(f"Job completed with status: {status}")
        return status
        
    except ValidationError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Failed to run job: {e}", file=sys.stderr)
        sys.exit(1)


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
        try:
            jobs = upload_configs.run(args)
            print(f"Created {len(jobs)} job(s)")
        except Exception as e:
            print(f"Failed to upload configs: {e}", file=sys.stderr)
            sys.exit(1)
    elif args.command == "list-jobs":
        _cmd_list_jobs(args)
    elif args.command == "boost-priority":
        _cmd_boost_priority(args)
    elif args.command == "set-priority":
        _cmd_set_priority(args)
    elif args.command == "run-one":
        status = _cmd_run_one(args)
        exit_code = 0 if status in ["completed", "success"] else 1
        sys.exit(exit_code)
    else:  # pragma: no cover - fallback
        parser.print_help()
        sys.exit(1)


__all__ = ["main", "build_arg_parser"]
