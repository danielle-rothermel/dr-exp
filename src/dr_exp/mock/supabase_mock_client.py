import json
import os
import shutil
import uuid
from datetime import datetime, UTC
from typing import Optional, List, Dict, Any
# For file locking - fcntl is Unix-specific. Consider a cross-platform alternative
# or simplify if concurrency isn't a major concern for initial mock usage.
# For now, we'll note its importance from the spec.
# import fcntl


class SupabaseMockClient:
    def __init__(self, base_path="."):
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

            # Simplified locking: In a real concurrent scenario, proper file locking (fcntl or a lock file)
            # would be needed around reading and writing this file.
            # For this mock, we'll assume single-threaded access for simplicity in V1,
            # but acknowledge the spec's requirement for fcntl for true atomicity.
            try:
                with open(job_file_path, "r+") as f:
                    # print(f"Attempting to claim job from {job_file_path}") # Debug
                    job_data = json.load(f)
                    if job_data.get("status") == "queued":
                        job_data["status"] = "running"
                        job_data["assigned_worker"] = (
                            f"mock_worker_{uuid.uuid4().hex[:6]}"
                        )
                        job_data["heartbeat"] = datetime.now(UTC).isoformat() + "Z"

                        f.seek(0)
                        json.dump(job_data, f, indent=4)
                        f.truncate()
                        # print(f"Claimed job: {job_data['id']}") # Debug
                        return job_data
            except Exception as e:
                print(
                    f"Error processing job file {job_file_path}: {e}"
                )  # Should go to a logger
                continue
        # print("No queued jobs found to claim.") # Debug
        return None

    def update_job(self, job_id: str, data: Dict[str, Any]):
        """Updates a job record with new data."""
        job_file_path = os.path.join(self.jobs_dir, f"{job_id}.json")
        if not os.path.exists(job_file_path):
            # print(f"Job file not found for update: {job_file_path}") # Debug
            # In a real scenario, you might raise an error or return a status
            # For now, let's assume it might be created if it's a new job being fully defined
            # Or simply do nothing if it strictly means "update existing"
            # For robustness, let's assume we only update existing.
            return {"success": False, "message": "Job not found"}

        try:
            with open(job_file_path, "r+") as f:
                existing_data = json.load(f)
                existing_data.update(data)
                # Ensure heartbeat is updated if status is running
                if existing_data.get("status") == "running" and "heartbeat" not in data:
                    existing_data["heartbeat"] = datetime.now(UTC).isoformat() + "Z"

                f.seek(0)
                json.dump(existing_data, f, indent=4)
                f.truncate()
            # print(f"Updated job: {job_id} with data {data}") # Debug
            return {"success": True, "message": "Job updated"}
        except Exception as e:
            print(f"Error updating job {job_id}: {e}")
            return {"success": False, "message": str(e)}

    def log_metrics(self, job_id: str, metrics_list: List[Dict[str, Any]]):
        """Appends a list of metric dictionaries to the job's .jsonl metrics file."""
        metric_file_path = os.path.join(self.metrics_dir, f"{job_id}.jsonl")
        try:
            with open(metric_file_path, "a") as f:
                for metrics in metrics_list:
                    metrics_to_log = metrics.copy()
                    if (
                        "timestamp" not in metrics_to_log
                    ):  # Add timestamp if not present
                        metrics_to_log["timestamp"] = (
                            datetime.now(UTC).isoformat() + "Z"
                        )
                    f.write(json.dumps(metrics_to_log) + "\n")
            # print(f"Logged {len(metrics_list)} metrics for job: {job_id}") # Debug
        except Exception as e:
            print(f"Error logging metrics for job {job_id}: {e}")

    def record_failure(
        self,
        job_id: str,
        error_type: str,
        message: str,
        stacktrace: Optional[str] = None,
    ):
        """Records a failure event to a global errors.jsonl file."""
        error_entry = {
            "job_id": job_id,
            "error_type": error_type,
            "message": message,
            "stacktrace": stacktrace,
            "timestamp": datetime.now(UTC).isoformat() + "Z",
        }
        try:
            with open(self.errors_file, "a") as f:
                f.write(json.dumps(error_entry) + "\n")
            # print(f"Recorded failure for job {job_id}: {error_type}") # Debug
        except Exception as e:
            print(f"Error recording failure for job {job_id}: {e}")

    def finalize_job(self, job_id: str, final_status: str, metadata: Dict[str, Any]):
        """Finalizes a job, typically setting its status and end_time, and other metadata."""
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
        job_file_path = os.path.join(self.jobs_dir, f"{job_id}.json")
        if os.path.exists(job_file_path):
            with open(job_file_path, "r") as f:
                return json.load(f)
        return None

    def get_config_for_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieves the configuration for a given job.
        In this mock, we'll assume the config is stored within the job's JSON file itself
        under a 'config_json' key, or it could point to another file.
        For simplicity, let's assume it's part of the job_data.
        """
        job_data = self.get_job_details(job_id)
        if job_data and "config_json" in job_data:
            return job_data["config_json"]
        # print(f"Config not found for job {job_id}") # Debug
        return None

    def add_job(
        self, job_config: Dict[str, Any], sweep_config_id: str, status: str = "queued"
    ) -> Dict[str, Any]:
        """
        Adds a new job to the mock database. Used by Config Generator mock interaction.
        The job_config here is the Hydra resolved config.
        """
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
        with open(job_file_path, "w") as f:
            json.dump(job_data, f, indent=4)
        print(f"Added new job {job_id}")  # Debug
        print("Job Data:")
        for k, v in job_data.items():
            print(f" - {k + ':':20} {v}")
        return job_data
