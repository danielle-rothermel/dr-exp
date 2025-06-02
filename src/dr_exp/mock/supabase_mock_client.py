import json
import os
import shutil
import tempfile
import uuid
from datetime import datetime, UTC
from typing import Optional, List, Dict, Any

import portalocker


class SupabaseMockClient:
    def __init__(self, base_path: str = ".") -> None:
        """Create the directories used for the mock database.

        Parameters
        ----------
        base_path : str, optional
            Directory under which ``mock_db`` and ``mock_storage`` are located.
        """
        self.mock_db_path = os.path.join(base_path, "mock_db")
        self.mock_storage_path = os.path.join(base_path, "mock_storage")
        self.jobs_dir = os.path.join(self.mock_db_path, "jobs")
        self.metrics_dir = os.path.join(self.mock_db_path, "metrics")
        self.errors_file = os.path.join(self.mock_db_path, "errors.jsonl")

        # Ensure directories exist (idempotent)
        os.makedirs(self.jobs_dir, exist_ok=True)
        os.makedirs(self.metrics_dir, exist_ok=True)
        os.makedirs(self.mock_storage_path, exist_ok=True)
        if not os.path.exists(self.errors_file):
            with open(self.errors_file, "w"):
                pass  # Create empty file

    def _atomic_write(self, target_file_path: str, data: str) -> None:
        """Write ``data`` to ``target_file_path`` atomically."""
        target_dir = os.path.dirname(target_file_path)
        fd, temp_file_path = tempfile.mkstemp(
            dir=target_dir, prefix=os.path.basename(target_file_path) + "~"
        )
        try:
            with os.fdopen(fd, "w") as temp_file:
                temp_file.write(data)
                temp_file.flush()
                os.fsync(temp_file.fileno())
            os.rename(temp_file_path, target_file_path)
        finally:
            if os.path.exists(temp_file_path):
                os.remove(temp_file_path)

    def list_jobs(self) -> List[Dict[str, Any]]:
        """Return a list of all job records in the mock database."""
        jobs: List[Dict[str, Any]] = []
        for job_file in os.listdir(self.jobs_dir):
            if not job_file.endswith(".json"):
                continue
            path = os.path.join(self.jobs_dir, job_file)
            try:
                with open(path, "r") as f:
                    jobs.append(json.load(f))
            except Exception as e:  # pragma: no cover - unexpected read error
                print(f"Error reading job file {path}: {e}")
        return jobs

    # --- Interface methods based on docs/supabase_mock.md ---

    def claim_job(self) -> Optional[Dict[str, Any]]:
        """
        Atomically claims a job from Supabase (simulated).
        Looks for a job with status='queued', updates it to 'running'.
        Uses file-level locking if possible for atomicity.
        """
        for job_file_name in os.listdir(self.jobs_dir):
            if not job_file_name.endswith(".json"):
                continue

            job_file_path = os.path.join(self.jobs_dir, job_file_name)
            try:
                with portalocker.Lock(
                    job_file_path, mode="r+b", flags=portalocker.LOCK_EX
                ):
                    with open(job_file_path, "r") as f:
                        job_data = json.load(f)

                    if job_data.get("status") == "queued":
                        job_data["status"] = "running"
                        job_data["assigned_worker"] = (
                            f"mock_worker_{uuid.uuid4().hex[:6]}"
                        )
                        job_data["heartbeat"] = datetime.now(UTC).isoformat() + "Z"

                        self._atomic_write(
                            job_file_path, json.dumps(job_data, indent=4)
                        )
                        return job_data
            except Exception as e:
                print(
                    f"Error processing job file {job_file_path}: {e}"
                )  # Should go to a logger
                continue
        return None

    def update_job(self, job_id: str, data: Dict[str, Any]):
        """Update a job record with ``data``."""
        job_file_path = os.path.join(self.jobs_dir, f"{job_id}.json")
        if not os.path.exists(job_file_path):
            # print(f"Job file not found for update: {job_file_path}") # Debug
            # In a real scenario, you might raise an error or return a status
            # For now, let's assume it might be created if it's a new job being fully defined
            # Or simply do nothing if it strictly means "update existing"
            # For robustness, let's assume we only update existing.
            return {"success": False, "message": "Job not found"}

        try:
            with portalocker.Lock(job_file_path, mode="r+b", flags=portalocker.LOCK_EX):
                with open(job_file_path, "r") as f:
                    existing_data = json.load(f)

                existing_data.update(data)
                if existing_data.get("status") == "running" and "heartbeat" not in data:
                    existing_data["heartbeat"] = datetime.now(UTC).isoformat() + "Z"

                self._atomic_write(job_file_path, json.dumps(existing_data, indent=4))
            return {"success": True, "message": "Job updated"}
        except Exception as e:
            print(f"Error updating job {job_id}: {e}")
            return {"success": False, "message": str(e)}

    def log_metrics(self, job_id: str, metrics_list: List[Dict[str, Any]]):
        """Append metrics to the job's metrics file."""
        metric_file_path = os.path.join(self.metrics_dir, f"{job_id}.jsonl")
        try:
            with portalocker.Lock(
                metric_file_path, mode="a", flags=portalocker.LOCK_EX
            ) as f:
                for metrics in metrics_list:
                    metrics_to_log = metrics.copy()
                    if "timestamp" not in metrics_to_log:
                        metrics_to_log["timestamp"] = (
                            datetime.now(UTC).isoformat() + "Z"
                        )
                    f.write(json.dumps(metrics_to_log) + "\n")
                f.flush()
                os.fsync(f.fileno())
        except Exception as e:
            print(f"Error logging metrics for job {job_id}: {e}")

    def record_failure(
        self,
        job_id: str,
        error_type: str,
        message: str,
        stacktrace: Optional[str] = None,
    ):
        """Record a failure event in ``errors.jsonl``."""
        error_entry = {
            "job_id": job_id,
            "error_type": error_type,
            "message": message,
            "stacktrace": stacktrace,
            "timestamp": datetime.now(UTC).isoformat() + "Z",
        }
        try:
            with portalocker.Lock(
                self.errors_file, mode="a", flags=portalocker.LOCK_EX
            ) as f:
                f.write(json.dumps(error_entry) + "\n")
                f.flush()
                os.fsync(f.fileno())
        except Exception as e:
            print(f"Error recording failure for job {job_id}: {e}")

    def finalize_job(self, job_id: str, final_status: str, metadata: Dict[str, Any]):
        """Finalize a job and update its status."""
        update_data = {
            "status": final_status,
            "end_time": datetime.now(UTC).isoformat() + "Z",
        }
        update_data.update(metadata)  # e.g., upload_complete_at, finalize_success
        return self.update_job(job_id, update_data)

    def upload_artifact(self, job_id: str, local_path: str, remote_path_suffix: str):
        """
        Simulates uploading an artifact by copying it to the mock storage.
        remote_path_suffix is the path relative to the run's artifact directory.
        E.g., if remote_path_suffix = "plots/loss.png", it goes to mock_storage/run_<job_id>/artifacts/plots/loss.png
        If remote_path_suffix = "metrics.jsonl", it goes to mock_storage/run_<job_id>/metrics.jsonl
        """
        if not os.path.exists(local_path):
            print(f"Local artifact not found: {local_path}")
            return {"success": False, "message": "Local artifact not found"}

        # Determine if it's a root file (like metrics.jsonl) or an artifact subdirectory file
        if (
            "/" not in remote_path_suffix and "." in remote_path_suffix
        ):  # Simple check for root files
            destination_path = os.path.join(
                self.mock_storage_path, f"run_{job_id}", remote_path_suffix
            )
        else:
            destination_path = os.path.join(
                self.mock_storage_path, f"run_{job_id}", "artifacts", remote_path_suffix
            )

        destination_dir = os.path.dirname(destination_path)
        os.makedirs(destination_dir, exist_ok=True)

        try:
            if os.path.isdir(local_path):
                # local_path is a directory; copy entire directory tree
                shutil.copytree(local_path, destination_path, dirs_exist_ok=True)
            else:
                # local_path is a file; copy the single file
                shutil.copy2(local_path, destination_path)
            return {"success": True, "storage_path": destination_path}
        except Exception as e:
            print(f"Error uploading artifact for job {job_id}: {e}")
            return {"success": False, "message": str(e)}

    # --- Helper/Additional methods that would be needed ---
    def get_job_details(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Return the stored record for ``job_id`` if it exists."""
        job_file_path = os.path.join(self.jobs_dir, f"{job_id}.json")
        if os.path.exists(job_file_path):
            with open(job_file_path, "r") as f:
                return json.load(f)
        return None

    def get_config_for_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Return the ``config_json`` stored with ``job_id`` if present."""
        job_data = self.get_job_details(job_id)
        if job_data and "config_json" in job_data:
            return job_data["config_json"]
        # print(f"Config not found for job {job_id}") # Debug
        return None

    def add_job(
        self, job_config: Dict[str, Any], sweep_config_id: str, status: str = "queued"
    ) -> Dict[str, Any]:
        """Add a new job entry to the mock database."""
        job_id = str(uuid.uuid4())
        job_data = {
            "id": job_id,
            "config_id": sweep_config_id,  # This would be the ID of the entry in a sweep_configs table
            "status": status,
            "retry_index": 0,
            "assigned_worker": "unassigned",
            "config_json": job_config,  # Storing the full config here for mock simplicity
            "created_at": datetime.now(UTC).isoformat() + "Z",
            # ... other fields will be populated as the job runs
        }
        job_file_path = os.path.join(self.jobs_dir, f"{job_id}.json")
        with portalocker.Lock(job_file_path, mode="wb", flags=portalocker.LOCK_EX):
            self._atomic_write(job_file_path, json.dumps(job_data, indent=4))
        print(f"Added new job {job_id}")  # Debug
        print("Job Data:")
        for k, v in job_data.items():
            print(f" - {k + ':':20} {v}")
        return job_data
