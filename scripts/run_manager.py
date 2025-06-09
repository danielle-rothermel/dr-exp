#!/usr/bin/env python3
"""Run a manager using the new architecture."""

import argparse
import os
import sys

from dr_exp.utils.factory import create_system, SystemConfig
from dr_exp.utils.gpu_discovery import discover_gpus
from dr_exp.job_db import JobDBConfig


def main() -> None:
    """Run the manager."""
    parser = argparse.ArgumentParser(description="Run experiment manager")

    # GPU configuration
    parser.add_argument(
        "--gpus", nargs="+", help="List of GPU IDs to use (default: auto-detect)"
    )
    parser.add_argument(
        "--gpus-per-node",
        type=int,
        default=1,
        help="Number of GPUs per node for auto-detection (default: 1)",
    )
    parser.add_argument(
        "--workers-per-gpu",
        type=int,
        default=1,
        help="Number of workers per GPU (default: 1)",
    )

    # Timing configuration
    parser.add_argument(
        "--heartbeat-timeout",
        type=int,
        default=60,
        help="Worker heartbeat timeout in seconds (default: 60)",
    )
    parser.add_argument(
        "--idle-timeout",
        type=int,
        default=30,
        help="Manager idle timeout in minutes (default: 30)",
    )

    # Process configuration
    parser.add_argument(
        "--start-method",
        choices=["fork", "spawn", "forkserver"],
        default="fork",
        help="Multiprocessing start method (default: fork)",
    )

    # Directory configuration
    parser.add_argument(
        "--base-dir", help="Manager base directory (default: job_data/manager)"
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

    # Status check
    parser.add_argument(
        "--status", action="store_true", help="Show system status and exit"
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
            gpus=args.gpus or discover_gpus(args.gpus_per_node),
            workers_per_gpu=args.workers_per_gpu,
            heartbeat_timeout=args.heartbeat_timeout,
            idle_timeout_mins=args.idle_timeout,
            manager_base_dir=args.base_dir,
            multiprocessing_start_method=args.start_method,
        )

        # Create system
        system = create_system(system_config)

        if args.status:
            # Show system status
            status = system.get_system_status()
            print("=== System Status ===")
            print(f"Mode: {status['configuration']['mode']}")
            print(f"GPUs: {status['configuration']['gpus']}")
            print(f"Workers per GPU: {status['configuration']['workers_per_gpu']}")
            print(
                f"Total capacity: {status['configuration']['total_worker_capacity']} workers"
            )
            print(f"Heartbeat timeout: {status['configuration']['heartbeat_timeout']}s")
            print()
            print(f"Running jobs: {status['job_status']['running_jobs']}")
            print(
                f"Queued jobs: {'Yes' if status['job_status']['has_queued_jobs'] else 'No'}"
            )
            print(f"Stale jobs: {status['job_status']['stale_jobs']}")

            if status["queue_preview"]:
                print("\nTop queued jobs:")
                for job in status["queue_preview"]:
                    print(f"  {job['id']}: priority {job['priority']}")

            if status["stale_jobs_preview"]:
                print("\nStale jobs:")
                for job in status["stale_jobs_preview"]:
                    print(
                        f"  {job['job_id']}: worker {job['worker']}, {job['age_seconds']}s old"
                    )

            return

        # Create and run manager
        print("Starting manager...")
        print(
            f"Configuration: {len(system_config.gpus)} GPUs, {system_config.workers_per_gpu} workers/GPU"
        )
        print(f"Mode: {system_config.job_db_config.mode}")
        print(f"Base directory: {system_config.manager_base_dir}")

        manager = system.create_manager()
        manager.run()

    except KeyboardInterrupt:
        print("\nShutdown requested by user")
        sys.exit(0)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
