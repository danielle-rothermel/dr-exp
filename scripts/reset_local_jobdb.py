import argparse
import os
import shutil
from typing import Optional

from dr_exp.utils.jobdb_factory import get_job_db_client
from dr_exp.job_db import JobDBConfig


def reset_job_db(base_path: str, mode: str, storage_path: Optional[str] = None) -> None:
    """Remove all local database and storage files then recreate empty dirs."""
    # Create config from parameters
    config = JobDBConfig(
        base_path=base_path,
        mode=mode,
        storage_path=storage_path or os.path.join(base_path, "storage"),
    )

    if config.mode != "files_local":
        raise ValueError("Can only reset database in files_local mode")

    # Get paths from config
    jobs_dir = os.path.join(config.base_path, "job_data")
    storage_dir = config.storage_path

    # Remove directories if they exist
    for path in (jobs_dir, storage_dir):
        if os.path.exists(path):
            print(f"Removing {path}")
            shutil.rmtree(path)

    # Create a new client to reinitialize directories
    get_job_db_client(config)
    print("JobDB reset complete")
    print(f"  Job data: {jobs_dir}")
    print(f"  Storage: {storage_dir}")


def main() -> None:
    """CLI wrapper for :func:`reset_job_db`."""

    parser = argparse.ArgumentParser(description="Reset the local jobdb environment.")
    parser.add_argument(
        "--base-path", required=True, help="Base directory for experiment data"
    )
    parser.add_argument(
        "--mode",
        required=True,
        choices=["files_local"],  # Only files_local supported for reset
        help="Database mode (only files_local supported)",
    )
    parser.add_argument(
        "--storage-path",
        help="Storage directory for artifacts (default: {base-path}/storage)",
    )

    args = parser.parse_args()
    reset_job_db(args.base_path, args.mode, args.storage_path)


if __name__ == "__main__":
    main()
