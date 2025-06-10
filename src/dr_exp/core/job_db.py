"""Simple file-based job database for ML experiments."""

import fcntl
import json
import uuid
import logging
from datetime import datetime, UTC
from pathlib import Path
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)


class JobDB:
    """File-based job database with priority queue."""

    def __init__(self, base_path: str, experiment_name: str, validate: bool = True):
        """Initialize JobDB with base path and experiment name.

        Args:
            base_path: Base directory for all experiments (e.g., /scratch/users/jane/experiments)
            experiment_name: Name of this experiment (e.g., resnet_sweep)
            validate: Whether to validate directory structure exists
        """
        # Validate inputs
        assert base_path, "base_path cannot be empty"
        assert experiment_name, "experiment_name cannot be empty"
        assert "/" not in experiment_name, "experiment_name cannot contain '/'"

        self.base_path = Path(base_path)
        self.experiment_name = experiment_name
        self.experiment_path = self.base_path / experiment_name

        # Define directory structure
        self.jobs_dir = self.experiment_path / "jobs"
        self.storage_dir = self.experiment_path / "storage"
        self.sync_queue_dir = self.experiment_path / "sync_queue"
        self.logs_dir = self.experiment_path / "logs"
        self.control_dir = self.experiment_path / "control"

        if validate:
            # Check that experiment is initialized
            required_dirs = [
                self.jobs_dir,
                self.storage_dir,
                self.sync_queue_dir,
                self.logs_dir,
                self.control_dir,
            ]

            missing = [d for d in required_dirs if not d.exists()]
            if missing:
                missing_names = [d.name for d in missing]
                raise RuntimeError(
                    f"Experiment not initialized. Missing directories: {missing_names}\n"
                    f"Run: dr_exp --base-path {base_path} --experiment {experiment_name} init"
                )
        else:
            # Create directories if they don't exist (for init command)
            for dir_path in [
                self.jobs_dir,
                self.storage_dir,
                self.sync_queue_dir,
                self.logs_dir,
                self.control_dir,
            ]:
                dir_path.mkdir(parents=True, exist_ok=True)

        logger.info(
            f"JobDB initialized for experiment '{experiment_name}' at {self.experiment_path}"
        )

    def create_job(self, config: Dict[str, Any], priority: int = 100) -> str:
        """Create a new job with given config and priority.

        Args:
            config: Job configuration dict (must include _target_ field)
            priority: Job priority (0-1000, higher runs first)

        Returns:
            job_id: Unique ID for the created job
        """
        # Validate priority
        assert 0 <= priority <= 1000, f"Priority must be 0-1000, got {priority}"

        # Validate _target_ exists
        assert "_target_" in config, "Config must include _target_ field"

        # Validate target is importable
        target = config["_target_"]
        module_path, func_name = target.rsplit(".", 1)
        try:
            import importlib

            importlib.import_module(module_path)
        except ImportError as e:
            assert False, f"Cannot import target module {module_path}: {e}"

        # Create job metadata
        job_id = str(uuid.uuid4())
        job_data = {
            "id": job_id,
            "experiment_name": self.experiment_name,
            "config": config,
            "priority": priority,
            "status": "queued",
            "created_at": datetime.now(UTC).isoformat(),
            "updated_at": datetime.now(UTC).isoformat(),
            "attempts": 0,
            "worker_id": None,
            "error": None,
            "completed_at": None,
        }

        # Write to file
        job_path = self.jobs_dir / f"{job_id}.json"
        with open(job_path, "w") as f:
            json.dump(job_data, f, indent=2)

        logger.info(f"Created job {job_id} with priority {priority}")
        return job_id

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a job by ID.

        Args:
            job_id: Job ID to retrieve

        Returns:
            Job data dict or None if not found
        """
        job_path = self.jobs_dir / f"{job_id}.json"
        if not job_path.exists():
            return None

        with open(job_path, "r") as f:
            job_data: Dict[str, Any] = json.load(f)
            return job_data

    def get_storage_path(self, job_id: str) -> Path:
        """Get the storage path for a job's artifacts.

        Args:
            job_id: Job ID

        Returns:
            Path object for job's storage directory
        """
        return self.storage_dir / f"run_{job_id}"

    def _list_job_files(self) -> List[Path]:
        """List all job files sorted by priority (highest first) then creation time.

        Returns:
            List of job file paths
        """
        job_files = []
        for job_file in self.jobs_dir.glob("*.json"):
            try:
                with open(job_file, "r") as f:
                    job_data = json.load(f)
                    # Only include queued jobs
                    if job_data.get("status") == "queued":
                        job_files.append(
                            (
                                job_file,
                                job_data.get("priority", 0),
                                job_data.get("created_at", ""),
                            )
                        )
            except (json.JSONDecodeError, IOError):
                # Skip corrupted files
                continue

        # Sort by priority (descending) then created_at (ascending)
        job_files.sort(key=lambda x: (-x[1], x[2]))
        return [f[0] for f in job_files]

    def claim_next_job(self, worker_id: str) -> Optional[Dict[str, Any]]:
        """Claim the next available job atomically.

        Uses file locking to ensure only one worker can claim a job.

        Args:
            worker_id: ID of the worker claiming the job

        Returns:
            Job data dict if claimed, None if no jobs available
        """
        # Get sorted list of queued jobs
        job_files = self._list_job_files()

        for job_file in job_files:
            try:
                # Open file with exclusive lock
                with open(job_file, "r+") as f:
                    # Try to acquire exclusive lock (non-blocking)
                    fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

                    try:
                        # Read current data
                        f.seek(0)
                        job_data: Dict[str, Any] = json.load(f)

                        # Double-check status (could have changed)
                        if job_data.get("status") != "queued":
                            continue

                        # Claim the job
                        job_data["status"] = "running"
                        job_data["worker_id"] = worker_id
                        job_data["started_at"] = datetime.now(UTC).isoformat()
                        job_data["updated_at"] = datetime.now(UTC).isoformat()
                        job_data["attempts"] = job_data.get("attempts", 0) + 1

                        # Write back atomically
                        f.seek(0)
                        f.truncate()
                        json.dump(job_data, f, indent=2)
                        f.flush()

                        # Release lock happens automatically when file closes
                        return job_data

                    finally:
                        # Ensure lock is released even if error occurs
                        fcntl.flock(f.fileno(), fcntl.LOCK_UN)

            except (IOError, BlockingIOError):
                # Lock is held by another process, try next job
                continue
            except Exception:
                # Skip corrupted files
                continue

        # No jobs available
        return None

    def update_job(self, job_id: str, updates: Dict[str, Any]) -> bool:
        """Update a job atomically.

        Args:
            job_id: Job to update
            updates: Fields to update

        Returns:
            True if updated, False if job not found
        """
        job_path = self.jobs_dir / f"{job_id}.json"
        if not job_path.exists():
            return False

        try:
            with open(job_path, "r+") as f:
                # Acquire exclusive lock
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)

                try:
                    # Read current data
                    f.seek(0)
                    job_data = json.load(f)

                    # Apply updates
                    job_data.update(updates)
                    job_data["updated_at"] = datetime.now(UTC).isoformat()

                    # Write back atomically
                    f.seek(0)
                    f.truncate()
                    json.dump(job_data, f, indent=2)
                    f.flush()

                    return True

                finally:
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)

        except Exception:
            return False
