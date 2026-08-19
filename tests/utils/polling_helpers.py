"""Helper functions for testing worker infinite polling behavior."""

import time
import threading
from collections.abc import Callable
from dr_exp.core.job_db import JobDB
from dr_exp.worker.base import Worker


class PollingTestResult:
    """Result container for polling tests."""

    def __init__(self) -> None:
        """Initialize polling test result container."""
        self.worker_started = False
        self.worker_finished = False
        self.stats: dict[str, int] | None = None
        self.exception: Exception | None = None
        self.polling_confirmed = False
        self.no_job_count = 0


def run_infinite_polling_test(
    worker: Worker, timeout_seconds: float = 2.0, no_job_threshold: int = 3
) -> PollingTestResult:
    """Test that worker polls indefinitely when no max_jobs is specified.

    Args:
        worker: Worker instance to test
        timeout_seconds: How long to let worker run before stopping
        no_job_threshold: Number of "no_job" messages to confirm polling

    Returns:
        PollingTestResult with test outcomes
    """
    result = PollingTestResult()

    # Track worker output to detect polling behavior
    original_run_one_job = worker.run_one_job

    def tracking_run_one_job() -> str:
        status = original_run_one_job()
        if status == "no_job":
            result.no_job_count += 1
            if result.no_job_count >= no_job_threshold:
                result.polling_confirmed = True
        return status

    worker.run_one_job = tracking_run_one_job

    # Run worker in background thread with timeout
    def worker_thread() -> None:
        try:
            result.worker_started = True
            result.stats = worker.run()  # This should run indefinitely
            result.worker_finished = True
        except Exception as e:
            result.exception = e

    thread = threading.Thread(target=worker_thread, daemon=True)
    thread.start()

    # Wait for worker to start and begin polling
    time.sleep(timeout_seconds)

    # Stop the worker gracefully
    worker.should_stop.set()

    # Wait a bit for graceful shutdown
    thread.join(timeout=1.0)

    return result


def run_max_jobs_termination_test(
    worker: Worker, max_jobs: int, timeout_seconds: float = 5.0
) -> PollingTestResult:
    """Test that worker terminates after processing max_jobs.

    Args:
        worker: Worker instance to test
        max_jobs: Number of jobs to process before terminating
        timeout_seconds: Maximum time to wait for completion

    Returns:
        PollingTestResult with test outcomes
    """
    result = PollingTestResult()

    # Run worker in background thread with timeout
    def worker_thread() -> None:
        try:
            result.worker_started = True
            result.stats = worker.run(max_jobs=max_jobs)
            result.worker_finished = True
        except Exception as e:
            result.exception = e

    thread = threading.Thread(target=worker_thread, daemon=True)
    thread.start()

    # Wait for completion or timeout
    thread.join(timeout=timeout_seconds)

    return result


def create_background_job_adder(
    job_db: JobDB, delay_seconds: float = 1.0, job_count: int = 2
) -> Callable[[], None]:
    """Create a function that adds jobs to the database after a delay.

    Useful for testing worker behavior when jobs arrive while it's polling.

    Args:
        job_db: JobDB instance to add jobs to
        delay_seconds: Delay before adding jobs
        job_count: Number of jobs to add

    Returns:
        Function that adds jobs when called
    """

    def add_jobs() -> None:
        time.sleep(delay_seconds)
        for i in range(job_count):
            config = {
                "_target_": "dr_exp.training.dummy_trainer.train",
                "epochs": 1,
                "index": i,
            }
            job_db.create_job(config, priority=100 + i)

    return add_jobs


def run_polling_with_delayed_jobs_test(
    worker: Worker, job_adder: Callable[[], None], timeout_seconds: float = 5.0
) -> PollingTestResult:
    """Test worker polling behavior when jobs are added while polling.

    Args:
        worker: Worker instance to test
        job_adder: Function that adds jobs to the database
        timeout_seconds: Maximum time to wait for completion

    Returns:
        PollingTestResult with test outcomes
    """
    result = PollingTestResult()

    # Start job adder in background
    job_thread = threading.Thread(target=job_adder, daemon=True)
    job_thread.start()

    # Track polling behavior
    original_run_one_job = worker.run_one_job

    def tracking_run_one_job() -> str:
        status = original_run_one_job()
        if status == "no_job":
            result.no_job_count += 1
        return status

    worker.run_one_job = tracking_run_one_job

    # Run worker in background thread
    def worker_thread() -> None:
        try:
            result.worker_started = True
            # Run until jobs are processed (should terminate naturally)
            result.stats = worker.run(max_jobs=2)
            result.worker_finished = True
        except Exception as e:
            result.exception = e

    thread = threading.Thread(target=worker_thread, daemon=True)
    thread.start()

    # Wait for completion or timeout
    thread.join(timeout=timeout_seconds)

    return result
