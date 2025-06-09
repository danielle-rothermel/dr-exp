#!/usr/bin/env python3
"""Run a worker using the new architecture."""

import argparse
import os
import sys

from dr_exp.utils.factory import create_system, SystemConfig
from dr_exp.job_db import JobDBConfig


def main() -> None:
    """Run the worker."""
    parser = argparse.ArgumentParser(description="Run experiment worker")

    # Worker identification
    parser.add_argument(
        "--worker-id", default="worker", help="Worker identifier (default: worker)"
    )

    # Job targeting
    parser.add_argument(
        "--target-job-id",
        help="Specific job ID to target (for 'run one' functionality)",
    )
    parser.add_argument(
        "--no-respect-reservations",
        action="store_true",
        help="Ignore job reservations when claiming jobs",
    )

    # Work directory
    parser.add_argument(
        "--work-dir",
        help="Work directory for job execution (default: temporary directory)",
    )

    # Claiming configuration
    parser.add_argument(
        "--max-attempts",
        type=int,
        default=5,
        help="Maximum job claiming attempts (default: 5)",
    )
    parser.add_argument(
        "--heartbeat-interval",
        type=float,
        default=5.0,
        help="Heartbeat interval in seconds (default: 5.0)",
    )

    # Required configuration
    parser.add_argument(
        "--base-path", required=True, help="Base directory for experiment data"
    )
    parser.add_argument(
        "--mode",
        required=True,
        choices=["files_local", "supabase_local", "supabase_remote"],
        help="Database mode",
    )
    parser.add_argument(
        "--storage-path",
        help="Storage directory for artifacts (default: {base-path}/storage)",
    )

    # Continuous operation
    parser.add_argument(
        "--continuous",
        action="store_true",
        help="Run continuously, claiming new jobs after completion",
    )
    parser.add_argument(
        "--continuous-delay",
        type=float,
        default=10.0,
        help="Delay between job attempts in continuous mode (default: 10.0s)",
    )

    args = parser.parse_args()

    try:
        # Create job database config from CLI arguments
        storage_path = args.storage_path or os.path.join(args.base_path, "storage")
        job_db_config = JobDBConfig(
            base_path=args.base_path, storage_path=storage_path, mode=args.mode
        )

        # Create system configuration
        system_config = SystemConfig(
            job_db_config=job_db_config,
            max_claim_attempts=args.max_attempts,
            worker_heartbeat_interval=args.heartbeat_interval,
        )

        # Create system
        system = create_system(system_config)

        print(f"Starting worker: {args.worker_id}")
        print(f"Mode: {system_config.job_db_config.mode}")
        if args.target_job_id:
            print(f"Target job: {args.target_job_id}")
        if args.work_dir:
            print(f"Work directory: {args.work_dir}")
        print(f"Heartbeat interval: {args.heartbeat_interval}s")
        print()

        if args.continuous:
            # Continuous mode - keep running until interrupted
            import time

            job_count = 0

            print("Running in continuous mode (Ctrl+C to stop)")

            while True:
                try:
                    status = system.run_worker(
                        worker_id=args.worker_id,
                        work_dir=args.work_dir,
                        target_job_id=args.target_job_id,
                        respect_reservations=not args.no_respect_reservations,
                    )

                    job_count += 1
                    print(f"Job {job_count} completed with status: {status}")

                    if status == "no_job":
                        print(f"No jobs available, waiting {args.continuous_delay}s...")
                        time.sleep(args.continuous_delay)
                    elif args.target_job_id:
                        # If targeting specific job, exit after processing it
                        break
                    else:
                        # Brief pause between jobs
                        time.sleep(1.0)

                except KeyboardInterrupt:
                    print(f"\nStopping after {job_count} jobs")
                    break
        else:
            # Single job mode
            status = system.run_worker(
                worker_id=args.worker_id,
                work_dir=args.work_dir,
                target_job_id=args.target_job_id,
                respect_reservations=not args.no_respect_reservations,
            )

            print(f"Worker completed with status: {status}")

            # Set exit code based on status
            if status in ["completed", "no_job"]:
                sys.exit(0)
            else:
                sys.exit(1)

    except KeyboardInterrupt:
        print("\nShutdown requested by user")
        sys.exit(0)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
