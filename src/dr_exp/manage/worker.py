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
from typing import Any, Callable, Optional
from contextlib import contextmanager

from dr_exp.logging.base_logger import BaseLogger
from dr_exp.logging.structured_logger import StructuredLogger
from dr_exp.utils.jobdb_factory import get_job_db_client
from dr_exp.job_db.base_job_db import BaseJobDB
from dr_exp.train_examples.dummy_trainer import train as default_train
from dr_exp.training.result import TrainingResult


class HeartbeatManager:
    """Manages heartbeat thread for a job."""

    def __init__(self, client: BaseJobDB, job_id: str, interval: float):
        self.client = client
        self.job_id = job_id
        self.interval = interval
        self.stop_event = threading.Event()
        self.thread: Optional[threading.Thread] = None

    def start(self):
        """Start the heartbeat thread."""
        if self.thread is None:
            self.thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
            self.thread.start()

    def stop(self):
        """Stop the heartbeat thread and wait for it to finish."""
        if self.thread is not None:
            self.stop_event.set()
            self.thread.join(timeout=5)  # Give it time to finish gracefully

    def _heartbeat_loop(self):
        """Send heartbeats at a fixed interval until stop_event is set."""
        while not self.stop_event.is_set():
            try:
                self.client.update_job(
                    self.job_id, {"heartbeat": datetime.now(UTC).isoformat() + "Z"}
                )
            except Exception as e:
                # Don't let heartbeat failures crash the worker
                logging.warning(f"Heartbeat failed for job {self.job_id}: {e}")

            # Use wait instead of sleep for more responsive shutdown
            if self.stop_event.wait(timeout=self.interval):
                break


@contextmanager
def managed_work_directory(work_dir: Optional[str], job_id: str):
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
        logger = self.logger_cls(work_dir, run_id=cfg.get("run_id"))

        # Start heartbeat manager
        heartbeat_manager = HeartbeatManager(
            self.client, self.job_id, self.heartbeat_interval
        )
        heartbeat_manager.start()

        try:
            # Execute training
            result = self._execute_training(cfg, logger, worker_log_path)
            train_status = result.status  # Direct access - guaranteed to exist

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
                if not isinstance(result, TrainingResult):
                    raise TypeError(
                        f"Training function must return TrainingResult, got {type(result).__name__}"
                    )

                wlog.write("Training completed successfully\n")
                return result

            except Exception as e:
                # Log the error
                stack = traceback.format_exc()
                wlog.write(f"Training failed with error: {e}\n")
                wlog.write(stack)

                # Record failure in database
                self.client.record_failure(self.job_id, type(e).__name__, str(e), stack)

                # Return failure result as TrainingResult
                from dr_exp.training.result import create_failure_result

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
    ):
        """Finalize logger and upload all artifacts."""
        # Finalize logger
        logger_meta = logger.finalize()

        # Upload metrics
        metrics_upload = self.client.upload_artifact(
            self.job_id, logger_meta["metrics_path"], "metrics.jsonl"
        )

        # Create and upload bundle
        bundle_upload = self._create_and_upload_bundle(
            logger, work_dir, worker_log_path
        )

        # Finalize job with metadata
        final_status = "completed" if train_status == "success" else "failed"
        metadata = {
            "final_val_acc": result.final_val_acc,  # Direct access - no .get() silent failures
            "final_train_loss": result.final_train_loss,
            "num_epochs": result.num_epochs,
            "train_status": train_status,
            "metrics_storage_path": metrics_upload.get("storage_path"),
            "bundle_storage_path": bundle_upload.get("storage_path"),
            "upload_complete_at": datetime.now(UTC).isoformat() + "Z",
            "finalize_success": logger_meta.get("finalize_success", False),
        }

        self.client.finalize_job(self.job_id, final_status, metadata)

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

        # Upload bundle
        return self.client.upload_artifact(self.job_id, bundle_zip, "bundle.zip")


def run_worker(
    base_path: str = "./job_data",
    work_dir: Optional[str] = None,
    max_claim_attempts: int = 5,
    heartbeat_interval: float = 5.0,
    trainer_fn: Callable[[Any, BaseLogger], TrainingResult] = default_train,
    logger_cls: type[BaseLogger] = StructuredLogger,
    client: Optional[BaseJobDB] = None,
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
    client = client or get_job_db_client()

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
) -> dict | str:
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
            return client.get_job_details(target_job_id)
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

    return "no_job"


__all__ = ["run_worker", "HeartbeatManager", "JobExecutor", "managed_work_directory"]
