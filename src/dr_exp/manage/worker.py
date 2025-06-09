"""Worker implementation with improved error handling and separation of concerns."""

from __future__ import annotations

import os
import shutil
import tempfile
import threading
import time
import traceback
import logging
from datetime import datetime, UTC
from typing import Any, Callable, Optional, Iterator, Dict
from contextlib import contextmanager

from dr_exp.logging.base_logger import BaseLogger
from dr_exp.logging.structured_logger import StructuredLogger
from dr_exp.job_db.base_job_db import BaseJobDB
from dr_exp.training.dummy_trainer import train as default_train
from dr_exp.training import TrainingResult


class UploadError(Exception):
    """Exception raised when artifact upload operations fail."""

    pass


class HeartbeatManager:
    """Manages heartbeat thread for a job."""

    def __init__(
        self, client: BaseJobDB, job_id: str, interval: float, max_failures: int = 3
    ):
        self.client = client
        self.job_id = job_id
        self.interval = interval
        self.max_failures = max_failures
        self.failure_count = 0
        self.stop_event = threading.Event()
        self.failure_event = threading.Event()  # Signal catastrophic failure
        self.thread: Optional[threading.Thread] = None

    def start(self) -> None:
        """Start the heartbeat thread."""
        if self.thread is None:
            self.thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
            self.thread.start()

    def stop(self) -> None:
        """Stop the heartbeat thread and wait for it to finish."""
        if self.thread is not None:
            self.stop_event.set()
            self.thread.join(timeout=5)  # Give it time to finish gracefully

    def has_failed(self) -> bool:
        """Check if heartbeat system has failed catastrophically."""
        return self.failure_event.is_set()

    def _heartbeat_loop(self) -> None:
        """Send heartbeats at a fixed interval until stop_event is set."""
        while not self.stop_event.is_set():
            try:
                self.client.update_job(
                    self.job_id, {"heartbeat": datetime.now(UTC).isoformat() + "Z"}
                )
                # Reset failure count on successful heartbeat
                self.failure_count = 0
            except Exception as e:
                self.failure_count += 1
                logging.error(
                    f"Heartbeat failed for job {self.job_id} (attempt {self.failure_count}/{self.max_failures}): {e}"
                )

                if self.failure_count >= self.max_failures:
                    logging.error(
                        f"Critical: Heartbeat system failed after {self.max_failures} attempts for job {self.job_id}"
                    )
                    self.failure_event.set()  # Signal catastrophic failure
                    break  # Stop trying

            # Use wait instead of sleep for more responsive shutdown
            if self.stop_event.wait(timeout=self.interval):
                break


@contextmanager
def managed_work_directory(work_dir: Optional[str], job_id: str) -> Iterator[str]:
    """Context manager for work directory creation and cleanup."""
    if work_dir is None:
        work_dir = tempfile.mkdtemp(prefix=f"worker_{job_id}_")
        created_temp = True
    else:
        created_temp = False

    os.makedirs(work_dir, exist_ok=True)

    try:
        yield work_dir
    finally:
        # Only clean up if we created a temporary directory
        if created_temp:
            shutil.rmtree(work_dir, ignore_errors=True)


class JobExecutor:
    """Handles the execution of a single job."""

    def __init__(
        self,
        job: dict,
        client: BaseJobDB,
        trainer_fn: Callable[[Any, BaseLogger], TrainingResult],
        logger_cls: type[BaseLogger],
        heartbeat_interval: float,
    ):
        self.job = job
        self.job_id = job["id"]
        self.client = client
        self.trainer_fn = trainer_fn
        self.logger_cls = logger_cls
        self.heartbeat_interval = heartbeat_interval

    def execute(self, work_dir: str) -> str:
        """Execute the job and return final status."""
        # Get job configuration
        cfg = self.client.get_config_for_job(self.job_id)
        if cfg is None:
            self.client.record_failure(
                self.job_id, "config_missing", "Config not found"
            )
            self.client.finalize_job(self.job_id, "failed", {"finalize_success": False})
            return "failed"

        # Setup logging
        worker_log_path = os.path.join(work_dir, "worker.log")
        debug_mode = os.getenv("DEBUG", "False").lower() in ("true", "1", "yes")
        logger = self.logger_cls(work_dir, run_id=cfg.get("run_id"), debug=debug_mode)  # type: ignore[call-arg]

        # Start heartbeat manager
        heartbeat_manager = HeartbeatManager(
            self.client, self.job_id, self.heartbeat_interval
        )
        heartbeat_manager.start()

        try:
            # Execute training
            result = self._execute_training(cfg, logger, worker_log_path)

            # Check for heartbeat failures after training completes
            if heartbeat_manager.has_failed():
                logging.error(
                    f"Job {self.job_id} failed due to heartbeat system failure"
                )
                self.client.record_failure(
                    self.job_id,
                    "heartbeat_failure",
                    "Heartbeat system failed - worker lost connectivity",
                )
                self.client.finalize_job(
                    self.job_id, "failed", {"finalize_success": False}
                )
                return "failed"

            # Determine train_status based on result status and error
            if result.status == "success":
                train_status = "success"
            elif result.error and (
                # Check for exception class names (actual crashes)
                any(
                    exc in result.error
                    for exc in [
                        "Exception",
                        "Error",
                        "RuntimeError",
                        "ValueError",
                        "MemoryError",
                        "OSError",
                        "IOError",
                    ]
                )
                or
                # Check for crash-like error patterns
                any(
                    pattern in result.error.lower()
                    for pattern in [
                        "out of memory",
                        "memory error",
                        "no space left",
                        "disk space",
                        "interrupted",
                        "corrupt",
                        "corrupted data",
                    ]
                )
            ):
                train_status = "crash"  # Training function crashed with exception or crash-like error
            else:
                train_status = "failed"  # Training function returned failure status

            # Finalize logger and upload artifacts
            self._finalize_and_upload(
                logger, work_dir, worker_log_path, result, train_status
            )

            final_status = "completed" if train_status == "success" else "failed"
            return final_status

        finally:
            heartbeat_manager.stop()

    def _execute_training(
        self, cfg: dict, logger: BaseLogger, worker_log_path: str
    ) -> TrainingResult:
        """Execute the training function with proper error handling."""
        with open(worker_log_path, "w") as wlog:
            wlog.write(f"Worker started for job {self.job_id}\n")
            wlog.flush()

            try:
                # Unwrap training config from dr_exp metadata structure
                # cfg has structure: {"config": {...}, "metadata": {...}}
                # Training functions should only receive the training config
                training_config = cfg["config"]

                result = self.trainer_fn(training_config, logger)

                # Enforce TrainingResult type - fail immediately if wrong type
                assert isinstance(result, TrainingResult), (
                    f"Training function must return TrainingResult, got {type(result).__name__}"
                )

                wlog.write("Training completed successfully\n")
                return result

            except Exception as e:
                # Log the error
                stack = traceback.format_exc()
                wlog.write(f"Training failed with error: {e}\n")
                wlog.write(stack)

                # Return failure result as TrainingResult
                # finalize_job() will handle all failure recording as single source of truth
                from dr_exp.training import create_failure_result

                return create_failure_result(
                    error=f"{type(e).__name__}: {str(e)}", epochs=0
                )

    def _finalize_and_upload(
        self,
        logger: BaseLogger,
        work_dir: str,
        worker_log_path: str,
        result: TrainingResult,
        train_status: str,
    ) -> Dict[str, Any]:
        """Finalize logger and upload all artifacts."""
        try:
            # Finalize logger first
            logger_meta = logger.finalize()

            # Upload artifacts with fail-fast pattern
            metrics_upload = self._upload_metrics_with_retry(logger_meta)
            bundle_upload = self._upload_bundle_with_retry(
                logger, work_dir, worker_log_path
            )

            # Success path - create final metadata
            return self._create_success_metadata(
                result, train_status, metrics_upload, bundle_upload, logger_meta
            )

        except UploadError as e:
            # Single error handling path for all upload failures
            return self._handle_upload_failure(e)

    def _upload_metrics_with_retry(self, logger_meta: dict) -> dict:
        """Upload metrics with proper error handling."""
        try:
            metrics_upload = self.client.upload_artifact(
                self.job_id, logger_meta["metrics_path"], "metrics.jsonl"
            )
            assert metrics_upload["success"], (
                f"Metrics upload failed: {metrics_upload.get('error', 'Unknown error')}"
            )
            return metrics_upload
        except Exception as e:
            raise UploadError(f"Failed to upload training metrics: {e}")

    def _upload_bundle_with_retry(
        self, logger: BaseLogger, work_dir: str, worker_log_path: str
    ) -> dict:
        """Upload bundle with proper error handling."""
        try:
            bundle_upload = self._create_and_upload_bundle(
                logger, work_dir, worker_log_path
            )
            assert bundle_upload["success"], (
                f"Bundle upload failed: {bundle_upload.get('error', 'Unknown error')}"
            )
            return bundle_upload
        except Exception as e:
            raise UploadError(f"Failed to upload training bundle: {e}")

    def _create_success_metadata(
        self,
        result: TrainingResult,
        train_status: str,
        metrics_upload: dict,
        bundle_upload: dict,
        logger_meta: dict,
    ) -> Dict[str, Any]:
        """Create final metadata for successful job completion."""
        final_status = "completed" if train_status == "success" else "failed"
        metadata = {
            "final_val_acc": result.final_val_acc,  # Direct access - no .get() silent failures
            "final_train_loss": result.final_train_loss,
            "num_epochs": result.num_epochs,
            "train_status": train_status,
            "metrics_storage_path": metrics_upload[
                "storage_path"
            ],  # Guaranteed to exist due to fail-fast
            "bundle_storage_path": bundle_upload[
                "storage_path"
            ],  # Guaranteed to exist due to fail-fast
            "upload_complete_at": datetime.now(UTC).isoformat() + "Z",
            "finalize_success": logger_meta["finalize_success"],
        }

        # Add error details for failed jobs - single source of truth for failure recording
        if final_status == "failed" and result.error:
            metadata["error_message"] = result.error

        self.client.finalize_job(self.job_id, final_status, metadata)
        return {"finalize_success": True, "metadata": metadata}

    def _handle_upload_failure(self, error: UploadError) -> Dict[str, Any]:
        """Single source of truth for upload failure handling."""
        logging.error(f"Critical: Upload failed for job {self.job_id}: {error}")
        self.client.record_failure(self.job_id, "upload_failure", str(error))
        self.client.finalize_job(self.job_id, "failed", {"finalize_success": False})
        return {"finalize_success": False, "error": str(error)}

    def _create_and_upload_bundle(
        self, logger: BaseLogger, work_dir: str, worker_log_path: str
    ) -> dict:
        """Create a bundle of all artifacts and upload it."""
        bundle_dir = os.path.join(work_dir, "bundle")
        os.makedirs(bundle_dir, exist_ok=True)

        # Copy artifacts to bundle
        try:
            shutil.copytree(
                logger.paths.checkpoint_dir,
                os.path.join(bundle_dir, "checkpoints"),
            )
        except (FileNotFoundError, OSError):
            # Create empty checkpoint dir if none exists
            os.makedirs(os.path.join(bundle_dir, "checkpoints"), exist_ok=True)

        try:
            shutil.copytree(
                logger.paths.artifact_dir,
                os.path.join(bundle_dir, "artifacts"),
            )
        except (FileNotFoundError, OSError):
            # Create empty artifacts dir if none exists
            os.makedirs(os.path.join(bundle_dir, "artifacts"), exist_ok=True)

        # Copy worker log
        if os.path.exists(worker_log_path):
            shutil.copy2(worker_log_path, os.path.join(bundle_dir, "worker.log"))

        # Create zip bundle
        bundle_zip = shutil.make_archive(
            os.path.join(work_dir, "bundle"), "zip", bundle_dir
        )

        # Upload bundle - exceptions will be caught by caller for fail-fast behavior
        return self.client.upload_artifact(self.job_id, bundle_zip, "bundle.zip")


def run_worker(
    client: BaseJobDB,
    base_path: str = "./job_data",
    work_dir: Optional[str] = None,
    max_claim_attempts: int = 5,
    heartbeat_interval: float = 5.0,
    trainer_fn: Callable[[Any, BaseLogger], TrainingResult] = default_train,
    logger_cls: type[BaseLogger] = StructuredLogger,
    worker_id: str = "unassigned_worker",
    target_job_id: Optional[str] = None,
    respect_reservations: bool = True,
) -> str:
    """Run a streamlined worker iteration with improved error handling.

    This is an improved version of run_worker that:
    - Uses better separation of concerns with dedicated classes
    - Has more robust error handling and cleanup
    - Provides clearer logging and status reporting
    - Uses context managers for resource management

    Parameters
    ----------
    base_path : str, optional
        Base path for mock database files.
    work_dir : str, optional
        Directory used for temporary work files. If None, creates a temp directory.
    max_claim_attempts : int, optional
        How many times to poll for a job before giving up.
    heartbeat_interval : float, optional
        Seconds between heartbeat updates.
    trainer_fn : Callable[[Any, BaseLogger], TrainingResult], optional
        Function implementing the training loop.
    logger_cls : type[BaseLogger], optional
        Logger class to instantiate.
    client : BaseJobDB, optional
        Client to use for job operations.
    worker_id : str, optional
        Identifier used when claiming jobs.
    target_job_id : str, optional
        If specified, worker will only attempt to claim this specific job.
    respect_reservations : bool, optional
        Whether to respect job reservations when claiming jobs.

    Returns
    -------
    str
        Final status string: "completed", "failed", "no_job", "job_not_found", etc.
    """

    # Claim a job
    job = _claim_job(
        client, worker_id, target_job_id, max_claim_attempts, respect_reservations
    )
    if isinstance(job, str):  # Error status
        return job

    # Execute the job with managed work directory
    with managed_work_directory(work_dir, job["id"]) as managed_dir:
        executor = JobExecutor(
            job=job,
            client=client,
            trainer_fn=trainer_fn,
            logger_cls=logger_cls,
            heartbeat_interval=heartbeat_interval,
        )
        return executor.execute(managed_dir)


def _claim_job(
    client: BaseJobDB,
    worker_id: str,
    target_job_id: Optional[str],
    max_claim_attempts: int,
    respect_reservations: bool,
) -> Dict[str, Any] | str:
    """Claim a job, returning the job dict or an error status string."""

    # Handle target job ID for "run one" functionality
    if target_job_id:
        job = client.get_job_details(target_job_id)
        if job is None:
            return "job_not_found"
        if job.get("status") != "queued":
            return "job_not_available"

        # Directly claim the specific job by updating its status
        try:
            client.update_job(
                target_job_id,
                {
                    "status": "running",
                    "assigned_worker": worker_id,
                    "claimed_at": datetime.now(UTC).isoformat() + "Z",
                },
            )
            # Return the updated job details
            job_details = client.get_job_details(target_job_id)
            if job_details is None:
                return "job_claim_failed"
            return job_details
        except Exception:
            return "target_job_claim_failed"

    # Normal job claiming with exponential backoff
    attempt = 0
    backoff = 1.0

    while attempt < max_claim_attempts:
        job = client.claim_job(worker_id, respect_reservations=respect_reservations)
        if job:
            return job

        time.sleep(backoff)
        backoff = min(backoff * 2, 30)  # Cap backoff at 30 seconds
        attempt += 1

    # No job was claimed - provide detailed diagnostics
    return _diagnose_no_jobs(client)


def _diagnose_no_jobs(client: BaseJobDB) -> str:
    """Diagnose why no jobs were found and provide detailed status information."""
    logger = logging.getLogger(__name__)

    # Get basic job statistics
    try:
        has_queued = client.has_queued_jobs()
        queue_summary = client.get_queue_summary(limit=5) if has_queued else []
        running_jobs = client.list_running_jobs()
    except Exception as e:
        logger.error(f"Failed to query job database: {e}")
        return "no_job_db_error"

    # Configuration information from client
    jobs_dir = client.jobs_dir  # BaseJobDB already constructs this path

    # File system diagnostics for files_local mode
    fs_diagnostics = ""
    # Note: We can't easily determine mode from BaseJobDB, so check if we have LocalJobDB
    from dr_exp.job_db.local_job_db import LocalJobDB

    if isinstance(client, LocalJobDB):
        try:
            if os.path.exists(jobs_dir):
                job_files = [f for f in os.listdir(jobs_dir) if f.endswith(".json")]
                fs_diagnostics = f"Jobs directory: {jobs_dir} (exists: True, job files: {len(job_files)})"

                # Check for jobs in alternative locations
                alternatives = _check_alternative_job_locations(jobs_dir)
                if alternatives:
                    fs_diagnostics += (
                        f"\nAlternative locations with jobs: {alternatives}"
                    )
            else:
                fs_diagnostics = f"Jobs directory: {jobs_dir} (exists: False)"
                # Look for job_data directories elsewhere
                alternatives = _find_job_data_directories()
                if alternatives:
                    fs_diagnostics += (
                        f"\nFound job_data directories elsewhere: {alternatives}"
                    )
        except Exception as e:
            fs_diagnostics = f"Error checking file system: {e}"

    # Log detailed diagnostics
    logger.info("=== Worker Job Claiming Diagnostics ===")
    logger.info(
        f"Configuration: Jobs directory={jobs_dir}, Base path={client.base_path}"
    )
    logger.info(f"Queued jobs in database: {len(queue_summary)}")
    logger.info(f"Running jobs: {len(running_jobs)}")
    if fs_diagnostics:
        logger.info(f"File system: {fs_diagnostics}")

    if queue_summary:
        logger.info("Top queued jobs:")
        for job in queue_summary[:3]:
            logger.info(
                f"  - Job {job['id'][:8]}... Priority: {job['priority']} Status: {job['status']}"
            )

        # Suggest configuration fix if jobs exist but can't be claimed
        if isinstance(client, LocalJobDB) and alternatives:
            logger.warning("CONFIGURATION MISMATCH DETECTED:")
            logger.warning(
                "Jobs exist in database but file system shows jobs in different location."
            )
            logger.warning(
                "Ensure --base-path and --mode arguments are consistent between upload and worker commands."
            )
            return "no_job_config_mismatch"

    logger.info("=== End Diagnostics ===")
    return "no_job"


def _check_alternative_job_locations(current_jobs_dir: str) -> list[str]:
    """Check for job files in common alternative locations."""
    alternatives = []
    common_paths = ["./job_data", "./logs/job_data", "../job_data", "job_data"]

    for alt_path in common_paths:
        if alt_path != current_jobs_dir and os.path.exists(alt_path):
            try:
                job_files = [f for f in os.listdir(alt_path) if f.endswith(".json")]
                if job_files:
                    alternatives.append(f"{alt_path} ({len(job_files)} jobs)")
            except (OSError, PermissionError):
                continue

    return alternatives


def _find_job_data_directories() -> list[str]:
    """Find job_data directories in current working directory and common locations."""
    found_dirs = []
    search_paths = [".", "./logs", "../", "logs"]

    for search_path in search_paths:
        if os.path.exists(search_path):
            try:
                for item in os.listdir(search_path):
                    full_path = os.path.join(search_path, item)
                    if os.path.isdir(full_path) and item == "job_data":
                        job_files = [
                            f for f in os.listdir(full_path) if f.endswith(".json")
                        ]
                        if job_files:
                            found_dirs.append(f"{full_path} ({len(job_files)} jobs)")
            except (OSError, PermissionError):
                continue

    return found_dirs


__all__ = ["run_worker", "HeartbeatManager", "JobExecutor", "managed_work_directory"]
