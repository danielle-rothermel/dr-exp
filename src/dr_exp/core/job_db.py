"""Simple file-based job database for ML experiments."""

import fcntl
import importlib
import json
import logging
import random
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

MAX_PRIORITY = 1000
MIN_PRIORITY = 0


class JobDB:
    """File-based job database with priority queue."""

    def __init__(
        self, base_path: str, experiment_name: str, validate: bool = True
    ) -> None:
        """Initialize JobDB with base path and experiment name."""
        if not base_path:
            raise ValueError("base_path cannot be empty")
        if not experiment_name:
            raise ValueError("experiment_name cannot be empty")
        if "/" in experiment_name:
            raise ValueError("experiment_name cannot contain '/'")

        self.base_path = Path(base_path).resolve()
        self.experiment_name = experiment_name
        self.experiment_path = self.base_path / experiment_name

        self.jobs_dir = self.experiment_path / "jobs"
        self.storage_dir = self.experiment_path / "storage"
        self.logs_dir = self.experiment_path / "logs"
        self.control_dir = self.experiment_path / "control"

        required_dirs = [
            self.jobs_dir,
            self.storage_dir,
            self.logs_dir,
            self.control_dir,
        ]

        if validate:
            missing = [d for d in required_dirs if not d.exists()]
            if missing:
                missing_names = [d.name for d in missing]
                raise RuntimeError(
                    f"Experiment not initialized. "
                    f"Missing directories: {missing_names}\n"
                    f"Run: dr_exp --base-path {base_path} "
                    f"--experiment {experiment_name} init"
                )
        else:
            for dir_path in required_dirs:
                dir_path.mkdir(parents=True, exist_ok=True)

        logger.info(
            f"JobDB initialized for experiment '{experiment_name}' "
            f"at {self.experiment_path}"
        )

    def create_job(
        self,
        config: dict[str, Any],
        priority: int = 100,
        tags: list[str] | None = None,
    ) -> str:
        """Create a new job with given config and priority."""
        if not MIN_PRIORITY <= priority <= MAX_PRIORITY:
            raise ValueError(
                f"Priority must be {MIN_PRIORITY}-{MAX_PRIORITY}, got {priority}"
            )

        # KNOWN ISSUE (see README): _target_ validated in JobDB and CLI too
        if "_target_" not in config:
            raise ValueError("Config must include _target_ field")
        target = config["_target_"]
        module_path, _func_name = target.rsplit(".", 1)
        try:
            importlib.import_module(module_path)
        except ImportError as e:
            raise ValueError(f"Module {module_path} not found") from e

        job_id = str(uuid.uuid4())
        job_data = {
            "id": job_id,
            "experiment_name": self.experiment_name,
            "config": config,
            "priority": priority,
            "tags": tags or [],
            "status": "queued",
            "created_at": datetime.now(UTC).isoformat(),
            "updated_at": datetime.now(UTC).isoformat(),
            "attempts": 0,
            "worker_id": None,
            "error": None,
            "completed_at": None,
        }

        job_path = self.jobs_dir / f"{job_id}.json"
        with job_path.open("w") as f:
            json.dump(job_data, f, indent=2)

        logger.info(f"Created job {job_id} with priority {priority}")
        return job_id

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        """Retrieve a job by ID."""
        job_path = self.jobs_dir / f"{job_id}.json"
        if not job_path.exists():
            return None

        with job_path.open() as f:
            job_data: dict[str, Any] = json.load(f)
            return job_data

    def get_storage_path(self, job_id: str) -> Path:
        """Get the storage path for a job's artifacts."""
        return self.storage_dir / f"run_{job_id}"

    def _list_job_files(self) -> list[Path]:
        """List queued job files sorted by priority then creation time."""
        job_files = []
        for job_file in self.jobs_dir.glob("*.json"):
            try:
                with job_file.open() as f:
                    job_data = json.load(f)
                    if job_data.get("status") == "queued":
                        job_files.append(
                            (
                                job_file,
                                job_data.get("priority", 0),
                                job_data.get("created_at", ""),
                            )
                        )
            except (OSError, json.JSONDecodeError):
                continue

        job_files.sort(key=lambda x: (-x[1], x[2]))
        return [f[0] for f in job_files]

    def claim_next_job(self, worker_id: str) -> dict[str, Any] | None:
        """Claim the highest priority unclaimed job."""
        # KNOWN ISSUE (see README): 5 lock attempts max; O(N) directory scans
        lock_file = self.jobs_dir / ".claim_lock"
        lock_file.touch(exist_ok=True)

        with lock_file.open("w") as lock_fd:
            max_attempts = 5
            for attempt in range(max_attempts):
                try:
                    fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if attempt < max_attempts - 1:
                        time.sleep(0.001 * random.uniform(0.5, 1.5))  # noqa: S311
                    else:
                        return None

            try:
                best_job = None
                best_priority = -1
                best_created_at = None

                for job_file in self.jobs_dir.glob("*.json"):
                    if job_file.name == ".claim_lock":
                        continue

                    try:
                        with job_file.open() as f:
                            job_data = json.load(f)

                        if job_data["status"] == "queued":
                            priority = job_data["priority"]
                            created_at = job_data.get("created_at", "")

                            if priority > best_priority or (
                                priority == best_priority
                                and (
                                    best_created_at is None
                                    or created_at < best_created_at
                                )
                            ):
                                best_job = job_data
                                best_priority = priority
                                best_created_at = created_at

                    except (json.JSONDecodeError, KeyError):
                        continue

                if not best_job:
                    return None

                job_file = self.jobs_dir / f"{best_job['id']}.json"

                with job_file.open() as f:
                    current_job: dict[str, Any] = json.load(f)

                if current_job["status"] != "queued":
                    return None

                # KNOWN ISSUE (see README): attempts incremented but never capped
                current_job["status"] = "running"
                current_job["worker_id"] = worker_id
                current_job["started_at"] = datetime.now(UTC).isoformat()
                current_job["updated_at"] = datetime.now(UTC).isoformat()
                current_job["attempts"] = current_job.get("attempts", 0) + 1

                temp_file = job_file.with_suffix(".tmp")
                with temp_file.open("w") as f:
                    json.dump(current_job, f, indent=2)
                temp_file.replace(job_file)

                return current_job

            finally:
                fcntl.flock(lock_fd, fcntl.LOCK_UN)

    def update_job(self, job_id: str, updates: dict[str, Any]) -> bool:
        """Update a job atomically."""
        job_path = self.jobs_dir / f"{job_id}.json"
        if not job_path.exists():
            return False

        try:
            with job_path.open("r+") as f:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)

                try:
                    f.seek(0)
                    job_data = json.load(f)
                    job_data.update(updates)
                    job_data["updated_at"] = datetime.now(UTC).isoformat()
                    f.seek(0)
                    f.truncate()
                    json.dump(job_data, f, indent=2)
                    f.flush()
                    return True

                finally:
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)

        except Exception:
            return False

    def complete_job(self, job_id: str, metrics: dict[str, Any] | None = None) -> bool:
        """Mark a job as completed successfully."""
        updates: dict[str, Any] = {
            "status": "completed",
            "completed_at": datetime.now(UTC).isoformat(),
            "error": None,
        }
        if metrics:
            updates["final_metrics"] = metrics

        return self.update_job(job_id, updates)

    def fail_job(self, job_id: str, error: str) -> bool:
        """Mark a job as failed."""
        updates = {
            "status": "failed",
            "completed_at": datetime.now(UTC).isoformat(),
            "error": error,
        }
        return self.update_job(job_id, updates)

    def heartbeat(self, job_id: str) -> bool:
        """Update job heartbeat timestamp."""
        updates = {"last_heartbeat": datetime.now(UTC).isoformat()}
        return self.update_job(job_id, updates)

    def list_jobs(self, status: str | None = None) -> list[dict[str, Any]]:
        """List all jobs, optionally filtered by status."""
        jobs = []

        for job_file in self.jobs_dir.glob("*.json"):
            try:
                with job_file.open() as f:
                    job_data = json.load(f)

                    if status is None or job_data.get("status") == status:
                        jobs.append(job_data)

            except (OSError, json.JSONDecodeError):
                continue

        jobs.sort(key=lambda x: x.get("created_at", ""))
        return jobs

    def get_experiment_info(self) -> dict[str, Any]:
        """Get information about this experiment."""
        jobs = self.list_jobs()

        status_counts: dict[str, int] = {}
        for job in jobs:
            status = job.get("status", "unknown")
            status_counts[status] = status_counts.get(status, 0) + 1

        return {
            "experiment_name": self.experiment_name,
            "base_path": str(self.base_path),
            "experiment_path": str(self.experiment_path),
            "total_jobs": len(jobs),
            "status_counts": status_counts,
            "created_at": min(
                (j.get("created_at") for j in jobs if j.get("created_at")), default=None
            ),
        }

    def mark_job_failed(self, job_id: str, reason: str) -> bool:
        """Mark a running job as failed (kill it)."""
        # KNOWN ISSUE (see README): only rewrites JSON; running trainer is not signalled
        job = self.get_job(job_id)
        if job and job["status"] == "running":
            return self.update_job(
                job_id,
                {
                    "status": "failed",
                    "error": f"Killed: {reason}",
                    "completed_at": datetime.now(UTC).isoformat(),
                },
            )
        return False

    def recover_stale_jobs(self, heartbeat_timeout: int = 300) -> list[str]:
        """Reset jobs with stale heartbeats back to queued."""
        from datetime import timedelta

        cutoff = datetime.now(UTC) - timedelta(seconds=heartbeat_timeout)
        recovered = []

        for job_file in self.jobs_dir.glob("*.json"):
            with job_file.open() as f:
                job = json.load(f)

            if job["status"] == "running":
                heartbeat = job.get("last_heartbeat")
                if not heartbeat or datetime.fromisoformat(heartbeat) < cutoff:
                    self.update_job(
                        job["id"],
                        {
                            "status": "queued",
                            "worker_id": None,
                            "started_at": None,
                            "last_heartbeat": None,
                            "error": "Worker died - job reset to queue",
                        },
                    )
                    recovered.append(job["id"])

        return recovered

    def boost_priority(self, job_ids: list[str], new_priority: int) -> int:
        """Boost priority of multiple jobs."""
        if not MIN_PRIORITY <= new_priority <= MAX_PRIORITY:
            raise ValueError(
                f"Priority must be {MIN_PRIORITY}-{MAX_PRIORITY}, got {new_priority}"
            )

        updated = 0
        for job_id in job_ids:
            job = self.get_job(job_id)
            if job and job["status"] == "queued":
                self.update_job(job_id, {"priority": new_priority})
                updated += 1
                logger.info(f"Boosted job {job_id} to priority {new_priority}")

        return updated

    def reserve_job(self, job_id: str, worker_id: str) -> bool:
        """Reserve a specific job for a worker."""
        # KNOWN ISSUE (see README): read-then-write without claim lock (races)
        job = self.get_job(job_id)
        if not job:
            return False

        if job["status"] not in ["queued", "failed"]:
            return False

        return self.update_job(
            job_id,
            {
                "reserved_for": worker_id,
                "reservation_time": datetime.now(UTC).isoformat(),
            },
        )

    def claim_reserved_job(self, job_id: str, worker_id: str) -> dict[str, Any] | None:
        """Claim a previously reserved job."""
        # KNOWN ISSUE (see README): read-then-write without claim lock (races)
        job = self.get_job(job_id)
        if not job:
            return None

        if job.get("reserved_for") != worker_id:
            return None

        if job["status"] not in ["queued", "failed"]:
            return None

        success = self.update_job(
            job_id,
            {
                "status": "running",
                "worker_id": worker_id,
                "started_at": datetime.now(UTC).isoformat(),
                "last_heartbeat": datetime.now(UTC).isoformat(),
                "reserved_for": None,
                "reservation_time": None,
            },
        )

        if success:
            return self.get_job(job_id)
        return None
