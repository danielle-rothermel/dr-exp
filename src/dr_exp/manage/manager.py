"""Manager implementation using abstract interface methods."""

import logging
import os
import signal
import time
from datetime import datetime, timedelta, UTC
from typing import List, Optional

from dr_exp.utils.jobdb_factory import get_job_db_client
from dr_exp.job_db.base_job_db import BaseJobDB
from .process_manager import ProcessManager


class Manager:
    """Manager that coordinates workers using only abstract interface methods.

    This manager eliminates database-specific code paths by delegating all
    database operations to the abstract interface. It focuses purely on
    high-level coordination logic.
    """

    def __init__(
        self,
        gpus: List[str],
        workers_per_gpu: int,
        heartbeat_timeout: int,
        idle_timeout_mins: int,
        base_dir: str,
        client: Optional[BaseJobDB] = None,
        process_manager: Optional[ProcessManager] = None,
    ) -> None:
        """Create a new Manager.

        Parameters
        ----------
        gpus : List[str]
            List of GPU IDs to use for workers.
        workers_per_gpu : int
            Number of worker processes per GPU.
        heartbeat_timeout : int
            Timeout in seconds for worker heartbeats.
        idle_timeout_mins : int
            Minutes to wait before shutting down when idle.
        base_dir : str
            Base directory for manager logs and worker directories.
        client : BaseJobDB, optional
            Job database client. If None, uses factory to create.
        process_manager : ProcessManager, optional
            Process manager for spawning workers. If None, uses default.
        """
        self.gpus = gpus
        self.workers_per_gpu = workers_per_gpu
        self.heartbeat_timeout = heartbeat_timeout
        self.idle_timeout = timedelta(minutes=idle_timeout_mins)
        self.base_dir = base_dir
        self.job_db = client or get_job_db_client()
        self.process_manager = process_manager or ProcessManager()

        self.last_activity = datetime.now(UTC)
        self.shutdown = False

        # Setup logging
        os.makedirs(self.base_dir, exist_ok=True)
        logging.basicConfig(
            filename=os.path.join(self.base_dir, "manager.log"),
            level=logging.INFO,
            format="%(asctime)s %(levelname)s %(message)s",
            force=True,
        )

    # ---------------- Worker Management ------------------

    def start_workers(self) -> None:
        """Spawn all configured worker processes."""
        for gpu in self.gpus:
            for i in range(self.workers_per_gpu):
                worker_id = f"worker_{gpu}_{i}"
                self.process_manager.launch_worker(worker_id, gpu, self.base_dir)
                logging.info("Launched worker %s on GPU %s", worker_id, gpu)

    def stop_all_workers(self) -> None:
        """Terminate all running worker processes."""
        self.process_manager.stop_all_workers()
        logging.info("Stopped all workers")

    # ---------------- Job & Heartbeat Management ------------------

    def check_stale_jobs(self) -> None:
        """Check for stale worker heartbeats and handle failed jobs.

        This method uses the streamlined interface to:
        1. Find jobs with stale heartbeats
        2. Mark them as failed
        3. Restart affected workers
        """
        # Use streamlined interface to get stale jobs
        stale_jobs = self.job_db.get_stale_jobs(self.heartbeat_timeout * 2)

        if not stale_jobs:
            return

        # Log stale jobs found
        for stale_job in stale_jobs:
            logging.warning(
                "Stale heartbeat for job %s (worker: %s, age: %ds)",
                stale_job.job_id,
                stale_job.assigned_worker,
                stale_job.age_seconds,
            )

        # Mark all stale jobs as failed in batch
        job_ids = [job.job_id for job in stale_jobs]
        results = self.job_db.mark_jobs_failed(job_ids, "worker_lost")

        # Log results
        successful_failures = [job_id for job_id, success in results.items() if success]
        failed_failures = [job_id for job_id, success in results.items() if not success]

        if successful_failures:
            logging.info(
                "Marked %d jobs as failed: %s",
                len(successful_failures),
                successful_failures,
            )
        if failed_failures:
            logging.error(
                "Failed to mark %d jobs as failed: %s",
                len(failed_failures),
                failed_failures,
            )

        # Restart affected workers - fail fast if infrastructure is compromised
        affected_workers = {job.assigned_worker for job in stale_jobs}
        managed_workers = set(self.process_manager.get_worker_status().keys())
        
        for worker_id in affected_workers:
            if worker_id not in managed_workers:
                # Worker not managed by process manager - likely external worker, log and continue
                logging.warning(f"Cannot restart worker {worker_id}: not managed by process manager")
                continue
                
            try:
                self.process_manager.restart_worker(worker_id)
                logging.info("Restarted worker %s", worker_id)
            except RuntimeError as e:
                logging.error(f"Critical: Worker restart failed for {worker_id}: {e}")
                # Re-raise to fail fast - infrastructure problems should not be masked
                raise RuntimeError(
                    f"Manager cannot continue with failing worker infrastructure: {e}"
                ) from e

    def check_idle_timeout(self) -> None:
        """Shutdown manager if idle for longer than idle_timeout.

        Uses streamlined interface to check for running jobs and queue status.
        """
        # Check if there are any running jobs
        running_jobs = self.job_db.list_running_jobs()

        if running_jobs:
            # There's activity, update last activity time
            self.last_activity = datetime.now(UTC)
            logging.debug(
                "Found %d running jobs, resetting idle timer", len(running_jobs)
            )
            return

        # No running jobs, check if there are queued jobs to log status
        if self.job_db.has_queued_jobs():
            queue_summary = self.job_db.get_queue_summary(limit=5)
            logging.info(
                "No running jobs, but %d queued jobs remain. Top priorities: %s",
                len(queue_summary),
                [
                    {
                        "id": job["id"],
                        "priority": job["priority"],
                    }  # Fail fast if required fields missing
                    for job in queue_summary
                ],
            )
        else:
            logging.debug("No running or queued jobs")

        # Check if we've been idle too long
        if datetime.now(UTC) - self.last_activity > self.idle_timeout:
            logging.info(
                "Idle timeout reached (%s minutes), shutting down",
                self.idle_timeout.total_seconds() / 60,
            )
            self.shutdown = True

    def log_status(self) -> None:
        """Log current system status for monitoring."""
        running_jobs = self.job_db.list_running_jobs()
        has_queued = self.job_db.has_queued_jobs()

        logging.info(
            "Status: %d running jobs, %s queued jobs, %d workers",
            len(running_jobs),
            "some" if has_queued else "no",
            self.process_manager.get_worker_count(),
        )

        # Log worker status
        worker_status = self.process_manager.get_worker_status()
        alive_workers = sum(1 for status in worker_status.values() if status["alive"])
        logging.info("Workers: %d alive, %d total", alive_workers, len(worker_status))

    # ---------------- Main Loop ------------------

    def _handle_signal(self, signum: int, frame: object) -> None:
        """Handle termination signals to initiate shutdown."""
        logging.info("Received signal %s", signum)
        self.shutdown = True

    def run(self) -> None:
        """Run the manager main loop.

        The main loop:
        1. Starts all workers
        2. Periodically checks for stale jobs and handles them
        3. Checks for idle timeout
        4. Logs status periodically
        5. Stops all workers on shutdown
        """
        # Setup signal handlers
        signal.signal(signal.SIGTERM, self._handle_signal)
        signal.signal(signal.SIGINT, self._handle_signal)

        logging.info(
            "Starting Manager with %d GPUs, %d workers per GPU",
            len(self.gpus),
            self.workers_per_gpu,
        )

        # Start all workers
        self.start_workers()

        # Main monitoring loop
        loop_count = 0
        status_log_interval = 10  # Log status every 10 loops

        try:
            while not self.shutdown:
                # Core monitoring tasks
                self.check_stale_jobs()
                self.check_idle_timeout()

                # Periodic status logging
                if loop_count % status_log_interval == 0:
                    self.log_status()

                loop_count += 1
                time.sleep(self.heartbeat_timeout)

        except KeyboardInterrupt:
            logging.info("Keyboard interrupt received")
            self.shutdown = True
        except Exception as e:
            logging.error("Unexpected error in main loop: %s", e)
            self.shutdown = True
        finally:
            # Always stop workers on exit
            self.stop_all_workers()
            logging.info("Manager shutdown complete")


__all__ = ["Manager"]
