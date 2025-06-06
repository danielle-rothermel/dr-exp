import argparse
import os
import shutil

from dr_exp.utils.jobdb_factory import get_job_db_client
from dr_exp.job_db import JobDBConfig


def reset_job_db() -> None:
    """Remove all local database and storage files then recreate empty dirs."""
    # Get config to find correct paths
    config = JobDBConfig.from_env()
    
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
    client = get_job_db_client(config)
    print(f"JobDB reset complete")
    print(f"  Job data: {jobs_dir}")
    print(f"  Storage: {storage_dir}")


def main() -> None:
    """CLI wrapper for :func:`reset_job_db`."""

    parser = argparse.ArgumentParser(description="Reset the local jobdb environment.")
    # No longer need base-path argument since we use config
    args = parser.parse_args()
    reset_job_db()


if __name__ == "__main__":
    main()
