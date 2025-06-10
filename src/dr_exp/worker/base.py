"""Base worker implementation for job execution."""

import os
import traceback
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime

import hydra
from omegaconf import OmegaConf

from ..core.job_db import JobDB


class Worker:
    """Base worker that executes jobs from JobDB."""

    def __init__(
        self, job_db: JobDB, worker_id: str, working_dir: Optional[str] = None
    ):
        """Initialize worker.

        Args:
            job_db: JobDB instance to get jobs from
            worker_id: Unique identifier for this worker
            working_dir: Directory to run jobs in (defaults to current dir)
        """
        self.job_db = job_db
        self.worker_id = worker_id
        self.working_dir = Path(working_dir) if working_dir else Path.cwd()
        self.current_job_id: Optional[str] = None

        # Ensure working directory exists
        self.working_dir.mkdir(parents=True, exist_ok=True)

    def execute_job(self, job: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a single job using Hydra.

        Args:
            job: Job data from JobDB

        Returns:
            Result dict with status and optional error
        """
        job_id = job["id"]
        config = job["config"]

        # Create job-specific working directory
        job_dir = self.working_dir / f"job_{job_id}"
        job_dir.mkdir(parents=True, exist_ok=True)

        # Change to job directory
        original_cwd = Path.cwd()
        os.chdir(job_dir)

        try:
            # Convert config to OmegaConf
            if isinstance(config, dict):
                config = OmegaConf.create(config)

            # Inject job metadata into config
            config.job_id = job_id
            config.worker_id = self.worker_id
            config.storage_path = str(self.job_db.get_storage_path(job_id))

            # Ensure storage directory exists
            Path(config.storage_path).mkdir(parents=True, exist_ok=True)

            # Execute using Hydra's call mechanism
            print(
                f"[{self.worker_id}] Executing job {job_id} with _target_={config._target_}"
            )
            result = hydra.utils.call(config)

            # Job succeeded
            return {
                "status": "success",
                "result": result,
                "completed_at": datetime.utcnow().isoformat(),
            }

        except Exception as e:
            # Job failed
            error_msg = f"{type(e).__name__}: {str(e)}"
            tb = traceback.format_exc()

            print(f"[{self.worker_id}] Job {job_id} failed: {error_msg}")
            print(f"Traceback:\n{tb}")

            return {
                "status": "failed",
                "error": error_msg,
                "traceback": tb,
                "completed_at": datetime.utcnow().isoformat(),
            }

        finally:
            # Always return to original directory
            os.chdir(original_cwd)

    def run_one_job(self) -> str:
        """Claim and execute one job.

        Returns:
            Status: 'completed', 'failed', or 'no_job'
        """
        # Try to claim a job
        job = self.job_db.claim_next_job(self.worker_id)

        if not job:
            print(f"[{self.worker_id}] No jobs available")
            return "no_job"

        self.current_job_id = job["id"]
        print(
            f"[{self.worker_id}] Claimed job {job['id']} (priority={job['priority']})"
        )

        # Execute the job
        result = self.execute_job(job)

        # Update job status based on result
        if result["status"] == "success":
            # Extract metrics if provided
            metrics = None
            if isinstance(result.get("result"), dict):
                metrics = result["result"].get("metrics")

            self.job_db.complete_job(job["id"], metrics)
            print(f"[{self.worker_id}] Job {job['id']} completed successfully")
            status = "completed"
        else:
            self.job_db.fail_job(job["id"], result["error"])
            print(f"[{self.worker_id}] Job {job['id']} failed")
            status = "failed"

        self.current_job_id = None
        return status

    def run(self, max_jobs: Optional[int] = None) -> Dict[str, int]:
        """Run worker until no more jobs or max_jobs reached.

        Args:
            max_jobs: Maximum number of jobs to execute (None = unlimited)

        Returns:
            Dict with counts of completed, failed, and total jobs
        """
        stats = {"completed": 0, "failed": 0, "total": 0}

        print(f"[{self.worker_id}] Worker started")

        while max_jobs is None or stats["total"] < max_jobs:
            status = self.run_one_job()

            if status == "no_job":
                break
            elif status == "completed":
                stats["completed"] += 1
            elif status == "failed":
                stats["failed"] += 1

            stats["total"] += 1

        print(f"[{self.worker_id}] Worker finished: {stats}")
        return stats
