"""Run one specific job with high priority using reservation system."""

from __future__ import annotations

import argparse
import tempfile
import uuid
from pathlib import Path
from typing import Sequence

from dr_exp.utils import config_upload
from dr_exp.utils.jobdb_factory import get_supabase_client
from dr_exp.job_db.local_job_db import LocalJobDB
from dr_exp.manage.worker_logic import run_worker
from dr_exp.utils.priority import PriorityClass


def add_arguments(parser: argparse.ArgumentParser) -> None:
    """Add arguments for run-one command."""
    self_dir_absolute = Path(__file__).resolve().parents[1]
    parser.add_argument(
        "--base-config-path",
        default=str(self_dir_absolute / "src" / "dr_exp" / "train_examples" / "configs"),
        help="Directory containing Hydra config files",
    )
    parser.add_argument(
        "--config-name",
        default="config.yaml",
        help="Name of the main config file (e.g. config.yaml)",
    )
    parser.add_argument(
        "--overrides",
        default="",
        help="Hydra override string (e.g., 'model=resnet optim=adam')",
    )
    parser.add_argument(
        "--priority",
        type=int,
        default=PriorityClass.URGENT.value[0],  # Start of URGENT range
        help=f"Job priority (0-1000, default: {PriorityClass.URGENT.value[0]} for urgent)",
    )
    parser.add_argument(
        "--reservation-timeout",
        type=int,
        default=300,
        help="Reservation timeout in seconds (default: 300)",
    )
    parser.add_argument(
        "--work-dir",
        help="Working directory for temporary files (default: auto-generated)",
    )
    parser.add_argument(
        "--base-path",
        default=".",
        help="Base path for database client",
    )
    parser.add_argument(
        "--worker-id",
        help="Worker ID for job reservation (default: auto-generated)",
    )


def build_arg_parser() -> argparse.ArgumentParser:
    """Build argument parser for run-one script."""
    parser = argparse.ArgumentParser(
        description="Reserve and run a single high-priority job immediately"
    )
    add_arguments(parser)
    return parser


def run(args: argparse.Namespace) -> str:
    """Execute the run-one workflow.
    
    Returns
    -------
    str
        Final status of the job execution.
    """
    # Get database client
    client = get_supabase_client(base_path=args.base_path)
    
    # Generate worker ID if not provided
    worker_id = args.worker_id or f"run_one_{uuid.uuid4().hex[:8]}"
    
    # Parse overrides into sweep format
    sweep_params = {}
    if args.overrides:
        sweep_params = config_upload.parse_sweep(args.overrides)
    
    # Generate configurations (should be just one for run-one)
    configs = list(config_upload.generate_configs(
        args.base_config_path, args.config_name, sweep_params
    ))
    
    if len(configs) != 1:
        raise ValueError(f"Run-one expects exactly 1 config, got {len(configs)}. "
                        f"Use simple overrides without comma-separated values.")
    
    config = configs[0]
    
    # Create reserved job with high priority
    sweep_id = config_upload.config_hash(config)
    reserved_job = client.add_reserved_job(
        job_config=config,
        sweep_config_id=sweep_id,
        reserved_for_worker=worker_id,
        reservation_timeout=args.reservation_timeout,
        priority=args.priority,
        status="queued"
    )
    
    job_id = reserved_job["id"]
    print(f"Created reserved job {job_id} with priority {args.priority}")
    print(f"Reserved for worker: {worker_id}")
    
    # Set up work directory
    work_dir = args.work_dir
    if work_dir is None:
        work_dir = tempfile.mkdtemp(prefix=f"run_one_{job_id}_")
    
    print(f"Using work directory: {work_dir}")
    print(f"Starting execution...")
    
    # Run the worker targeting this specific job
    try:
        final_status = run_worker(
            base_path=args.base_path,
            work_dir=work_dir,
            max_claim_attempts=3,  # Reduced since we have a reservation
            worker_id=worker_id,
            target_job_id=job_id,
            respect_reservations=True,
            client=client,
        )
        
        print(f"Job execution completed with status: {final_status}")
        return final_status
        
    except Exception as e:
        print(f"Job execution failed with error: {e}")
        # Try to mark job as failed if it wasn't already handled
        try:
            client.record_failure(job_id, "run_one_error", str(e))
            client.finalize_job(job_id, "failed", {"finalize_success": False})
        except:
            pass  # Best effort cleanup
        return "failed"


def main(argv: Sequence[str] | None = None) -> None:
    """Entry point for the run-one script."""
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    
    try:
        status = run(args)
        exit_code = 0 if status in ["completed", "success"] else 1
        exit(exit_code)
    except Exception as e:
        print(f"Run-one failed: {e}")
        exit(1)


if __name__ == "__main__":
    main()