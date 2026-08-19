"""Base worker implementation for job execution."""

import os
import sys
import threading
import time
import traceback
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import hydra
from omegaconf import OmegaConf

from dr_exp.core.job_db import JobDB


class Worker:
    """Base worker that executes jobs from JobDB."""

    def __init__(
        self,
        job_db: JobDB,
        worker_id: str,
        working_dir: str | None = None,
        experiment_path: str | None = None,
        heartbeat_interval: int = 60,
    ) -> None:
        """Initialize worker."""
        self.job_db = job_db
        self.worker_id = worker_id
        self.working_dir = Path(working_dir) if working_dir else Path.cwd()
        self.heartbeat_interval = heartbeat_interval

        self.current_job_id: str | None = None
        self.should_stop = threading.Event()

        self.working_dir.mkdir(parents=True, exist_ok=True)

        # KNOWN ISSUE (see README): experiment_path unused at CLI call sites
        self.log_file = None
        self._original_stdout = None
        self._original_stderr = None
        if experiment_path:
            log_dir = Path(experiment_path) / "logs"
            log_dir.mkdir(exist_ok=True)
            log_path = log_dir / f"worker_{worker_id}.log"
            self.log_file = log_path.open("a", buffering=1)

            self._original_stdout = sys.stdout
            self._original_stderr = sys.stderr
            sys.stdout = self.log_file
            sys.stderr = self.log_file

            print(
                f"=== Worker {worker_id} started at {datetime.now(UTC).isoformat()} ==="
            )
            print(f"Experiment: {Path(experiment_path).name}")
            print("=" * 60)

        self.heartbeat_thread: threading.Thread | None = None

    def _heartbeat_worker(self) -> None:
        """Background thread that sends heartbeats for current job."""
        # KNOWN ISSUE (see README): daemon thread can be starved by GIL-holding trainer
        print(f"[{self.worker_id}] Heartbeat thread started")

        while not self.should_stop.wait(self.heartbeat_interval):
            try:
                if self.current_job_id:
                    success = self.job_db.heartbeat(self.current_job_id)
                    if not success:
                        print(
                            f"[{self.worker_id}] Failed to heartbeat job "
                            f"{self.current_job_id}"
                        )

            except Exception as e:
                print(f"[{self.worker_id}] Heartbeat error: {e}")

        print(f"[{self.worker_id}] Heartbeat thread stopped")

    def start_background_threads(self) -> None:
        """Start background heartbeat thread."""
        if not self.heartbeat_thread:
            self.heartbeat_thread = threading.Thread(
                target=self._heartbeat_worker, name=f"{self.worker_id}_heartbeat"
            )
            self.heartbeat_thread.daemon = True
            self.heartbeat_thread.start()

    def stop_background_threads(self) -> None:
        """Stop background threads gracefully."""
        self.should_stop.set()

        if self.heartbeat_thread and self.heartbeat_thread.is_alive():
            self.heartbeat_thread.join(timeout=5)

    def execute_job(self, job: dict[str, Any]) -> dict[str, Any]:
        """Execute a single job using Hydra."""
        job_id = job["id"]
        config = job["config"]

        job_dir = self.working_dir / f"job_{job_id}"
        job_dir.mkdir(parents=True, exist_ok=True)

        original_cwd = Path.cwd()
        os.chdir(job_dir)

        storage_path = self.job_db.get_storage_path(job_id)
        storage_path.mkdir(parents=True, exist_ok=True)

        try:
            if isinstance(config, dict):
                config = OmegaConf.create(config)

            config.job_id = job_id
            config.worker_id = self.worker_id
            config.storage_path = str(storage_path)

            print(
                f"[{self.worker_id}] Executing job {job_id} with "
                f"_target_={config._target_}"
            )
            result = hydra.utils.call(config)

            return {
                "status": "success",
                "result": result,
                "completed_at": datetime.now(UTC).isoformat(),
            }

        except Exception as e:
            error_msg = f"{type(e).__name__}: {e!s}"
            tb = traceback.format_exc()

            print(f"[{self.worker_id}] Job {job_id} failed: {error_msg}")
            print(f"Traceback:\n{tb}")

            error_file = storage_path / "error.txt"
            error_file.write_text(f"{error_msg}\n\n{tb}")

            return {
                "status": "failed",
                "error": error_msg,
                "traceback": tb,
                "completed_at": datetime.now(UTC).isoformat(),
            }

        finally:
            os.chdir(original_cwd)

    def run_one_job(self) -> str:
        """Claim and execute one job."""
        job = self.job_db.claim_next_job(self.worker_id)

        if not job:
            print(f"[{self.worker_id}] No jobs available")
            return "no_job"

        self.current_job_id = job["id"]
        print(
            f"[{self.worker_id}] Claimed job {job['id']} (priority={job['priority']})"
        )

        self.job_db.heartbeat(job["id"])

        result = self.execute_job(job)

        if result["status"] == "success":
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

    def run(self, max_jobs: int | None = None) -> dict[str, int]:
        """Run worker until no more jobs or max_jobs reached."""
        stats = {"completed": 0, "failed": 0, "total": 0}

        print(f"[{self.worker_id}] Worker started")

        self.start_background_threads()

        try:
            while max_jobs is None or stats["total"] < max_jobs:
                status = self.run_one_job()

                if status == "no_job":
                    time.sleep(10)
                    continue
                if status == "completed":
                    stats["completed"] += 1
                    stats["total"] += 1
                elif status == "failed":
                    stats["failed"] += 1
                    stats["total"] += 1
        finally:
            self.stop_background_threads()

            if self.log_file and not self.log_file.closed:
                sys.stdout = getattr(self, "_original_stdout", sys.__stdout__)
                sys.stderr = getattr(self, "_original_stderr", sys.__stderr__)
                self.log_file.close()

        print(f"[{self.worker_id}] Worker finished: {stats}")
        return stats

    def shutdown(self, reason: str = "signal") -> None:
        """Shutdown worker gracefully."""
        # KNOWN ISSUE (see README): never called; no SIGTERM handler registers this
        print(f"\n=== Worker {self.worker_id} shutting down: {reason} ===")

        if self.log_file:
            if self._original_stdout:
                sys.stdout = self._original_stdout
            if self._original_stderr:
                sys.stderr = self._original_stderr
            self.log_file.close()
            self.log_file = None
