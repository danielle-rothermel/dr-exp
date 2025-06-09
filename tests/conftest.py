"""Global pytest configuration and fixtures."""

import os
import pytest
import tempfile
import shutil
import threading
import subprocess
from pathlib import Path
from datetime import datetime, UTC, timedelta
from contextlib import contextmanager
from unittest.mock import patch
from typing import Any, Dict, Optional, List, Generator, Callable, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    pass

from dr_exp.job_db import JobDBConfig, LocalJobDB, SupabaseJobDB
from dr_exp.utils.factory import create_system, SystemConfig
from dr_exp.training import create_success_result


def make_wrapped_config(
    config_dict: Dict[str, Any], metadata: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Create a properly wrapped config for tests that simulate the full upload workflow.

    This function creates the config structure that would normally be created
    by the config upload process.

    Args:
        config_dict: The training configuration dictionary
        metadata: Optional metadata dict, defaults to test metadata

    Returns:
        Dict with {"config": config_dict, "metadata": metadata} structure
    """
    if metadata is None:
        metadata = {
            "cluster_name": "test_cluster",
            "description": "test config",
            "interface_version": None,
            "code_version": None,
        }

    return {"config": config_dict, "metadata": metadata}


@pytest.fixture
def temp_job_db() -> Generator[LocalJobDB, None, None]:
    """Provide a temporary LocalJobDB for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config = JobDBConfig(
            mode="files_local",
            base_path=tmpdir,
            storage_path=os.path.join(tmpdir, "storage"),
        )
        config.validate()
        yield LocalJobDB(config)


@pytest.fixture(scope="session")
def supabase_test_mode() -> bool:
    """Check if we should run Supabase integration tests."""
    # Check if Supabase is available for testing
    return os.getenv("RUN_SUPABASE_TESTS") == "1"


@pytest.fixture
def reset_supabase_db() -> None:
    """Reset the local Supabase database before test."""
    if os.getenv("RUN_SUPABASE_TESTS") == "1":
        try:
            # Reset the database
            subprocess.run(
                ["supabase", "db", "reset", "--linked=false"],
                check=True,
                capture_output=True,
            )
        except (subprocess.CalledProcessError, FileNotFoundError):
            pytest.skip("Could not reset Supabase database")


@pytest.fixture
def clean_supabase_client() -> SupabaseJobDB:
    """Provide a clean SupabaseJobDB client for testing."""
    if os.getenv("EXPMGR_MODE") != "supabase_local":
        pytest.skip("Requires EXPMGR_MODE=supabase_local")

    config = JobDBConfig(
        base_path=os.getenv("DR_EXP_BASE_PATH", "./logs"),
        mode="supabase_local",
        storage_path=os.getenv("DR_EXP_STORAGE_PATH", "./storage"),
        # Supabase credentials will be read from environment in validate()
    )
    config.validate()
    return SupabaseJobDB(config)


# Pytest markers for organizing tests
def pytest_configure(config: pytest.Config) -> None:
    """Configure pytest markers."""
    config.addinivalue_line(
        "markers", "supabase: mark test as requiring local Supabase"
    )
    config.addinivalue_line("markers", "slow: mark test as slow running")
    config.addinivalue_line("markers", "fast: mark test as fast running")
    config.addinivalue_line(
        "markers", "concurrency: mark test as testing concurrent behavior"
    )
    config.addinivalue_line("markers", "integration: mark test as integration test")
    config.addinivalue_line("markers", "unit: mark test as unit test")
    config.addinivalue_line("markers", "edge_case: mark test for edge case scenarios")
    config.addinivalue_line(
        "markers", "timeout: mark test as including timeouts (very slow)"
    )


# Enhanced test infrastructure fixtures for Phase 2


@pytest.fixture
def enhanced_mock_time() -> Any:
    """Enhanced timing fixture with database operation coordination and multi-scenario support."""

    class EnhancedMockTime:
        def __init__(self) -> None:
            self._current_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
            self._time_calls: List[datetime] = []
            self._milestones: Dict[
                str, datetime
            ] = {}  # Named time milestones for test coordination
            self._events: Dict[
                str, threading.Event
            ] = {}  # Associated events for timing coordination

        def now(self, tz: Optional[Any] = None) -> datetime:
            self._time_calls.append(self._current_time)
            return self._current_time

        def advance(self, seconds: int, name: Optional[str] = None) -> None:
            """Advance mock time by specified seconds, optionally setting a named milestone."""
            self._current_time += timedelta(seconds=seconds)
            if name:
                self._milestones[name] = self._current_time
                # Signal any waiting events
                if name in self._events:
                    self._events[name].set()

        def set_milestone(self, name: str) -> None:
            """Set a named milestone at current time."""
            self._milestones[name] = self._current_time
            if name in self._events:
                self._events[name].set()

        def get_milestone(self, name: str) -> Optional[datetime]:
            """Get time at named milestone."""
            return self._milestones.get(name)

        def wait_for_milestone(self, name: str, timeout: int = 5) -> bool:
            """Wait for a named milestone to be reached."""
            if name not in self._events:
                self._events[name] = threading.Event()
            return self._events[name].wait(timeout=timeout)

        def create_stale_timestamp(self, seconds_ago: int) -> str:
            """Create a timestamp that would be stale by the given number of seconds."""
            stale_time = self._current_time - timedelta(seconds=seconds_ago)
            return stale_time.isoformat() + "Z"

        def advance_to_make_stale(
            self, heartbeat_timeout: int, buffer: int = 5
        ) -> None:
            """Advance time to make jobs with current heartbeat stale."""
            # Stale threshold is typically 2x heartbeat timeout
            stale_threshold = heartbeat_timeout * 2 + buffer
            self.advance(stale_threshold, "stale_jobs_detected")

        def get_calls(self) -> List[datetime]:
            return self._time_calls.copy()

        def reset_calls(self) -> None:
            self._time_calls.clear()

    return EnhancedMockTime()


@pytest.fixture
def isolated_job_db(tmp_path: Path) -> Any:
    """Job database with guaranteed isolation and verification utilities."""

    class IsolatedJobDB:
        def __init__(self, tmp_path: Path) -> None:
            self.config = JobDBConfig(
                base_path=str(tmp_path),
                storage_path=str(tmp_path / "storage"),
                mode="files_local",
            )
            self.config.validate()
            self.db = LocalJobDB(self.config)
            self._job_counts: Dict[str, int] = {}

        def add_test_job(
            self,
            config_override: Optional[Dict[str, Any]] = None,
            sweep_name: str = "test_sweep",
            status: str = "queued",
            priority: int = 100,
            **kwargs: Any,
        ) -> Dict[str, Any]:
            """Add a test job with sensible defaults."""
            config = {"test_param": "default_value"}
            if config_override:
                config.update(config_override)

            # Wrap config for proper worker interface
            wrapped_config = make_wrapped_config(config)
            job = self.db.add_job(
                wrapped_config, sweep_name, status=status, priority=priority, **kwargs
            )
            return job

        def create_test_jobs(
            self,
            count: int = 3,
            priority_range: Tuple[int, int] = (100, 900),
            status: str = "queued",
        ) -> List[Dict[str, Any]]:
            """Create multiple test jobs with realistic priority distribution."""
            jobs = []
            priority_step = (priority_range[1] - priority_range[0]) // max(1, count - 1)

            for i in range(count):
                priority = priority_range[0] + (i * priority_step)
                job = self.add_test_job(
                    config_override={"job_number": i, "priority_test": f"job_{i}"},
                    priority=priority,
                    status=status,
                )
                jobs.append(job)

            return jobs

        def verify_job_counts(self, expected_counts: Dict[str, int]) -> None:
            """Verify job counts by status."""
            for status, expected_count in expected_counts.items():
                actual_count = len(
                    [j for j in self.db.list_jobs() if j["status"] == status]
                )
                assert actual_count == expected_count, (
                    f"Expected {expected_count} {status} jobs, got {actual_count}"
                )

        def verify_job_statuses(self, expected_statuses: Dict[str, str]) -> None:
            """Verify specific job statuses by job ID."""
            for job_id, expected_status in expected_statuses.items():
                job_details = self.db.get_job_details(job_id)
                assert job_details is not None
                actual_status = job_details["status"]
                assert actual_status == expected_status, (
                    f"Job {job_id} has status {actual_status}, expected {expected_status}"
                )

        def get_jobs_by_status(self, status: str) -> List[Dict[str, Any]]:
            """Get all jobs with specific status."""
            return [j for j in self.db.list_jobs() if j["status"] == status]

        def reset_state(self) -> None:
            """Reset database to clean state."""
            # Clear all jobs by removing both job_data and storage directories

            # Remove job_data directory (where job records are stored)
            job_data_dir = Path(self.config.base_path) / "job_data"
            if job_data_dir.exists():
                shutil.rmtree(job_data_dir)

            # Remove storage directory (where artifacts are stored)
            storage_dir = Path(self.config.storage_path)
            if storage_dir.exists():
                shutil.rmtree(storage_dir)

            # Recreate the database instance to ensure clean state and recreate directories
            self.db = LocalJobDB(self.config)

        # Delegate other methods to underlying db
        def __getattr__(self, name: str) -> Any:
            return getattr(self.db, name)

    return IsolatedJobDB(tmp_path)


@pytest.fixture
def integration_system(tmp_path: Path) -> Any:
    """Complete integration system with enhanced configuration."""
    job_db_config = JobDBConfig(
        base_path=str(tmp_path),
        storage_path=str(tmp_path / "storage"),
        mode="files_local",
    )

    config = SystemConfig(
        job_db_config=job_db_config,
        gpus=["0", "1"],
        workers_per_gpu=2,
        heartbeat_timeout=10,
        idle_timeout_mins=1,
        max_claim_attempts=3,
        worker_heartbeat_interval=0.1,  # Fast heartbeat for testing
    )

    return create_system(config)


@contextmanager
def event_driven_training(
    completion_events: Optional[Dict[str, threading.Event]] = None,
    execution_order: Optional[List[str]] = None,
    results: Optional[Dict[str, Any]] = None,
    startup_delays: Optional[Dict[str, threading.Event]] = None,
    heartbeat_events: Optional[Dict[str, threading.Event]] = None,
) -> Generator[List[str], None, None]:
    """Enhanced event-driven training context with multiple coordination patterns."""
    completion_events = completion_events or {}
    execution_order = execution_order or []
    results = results or {}
    startup_delays = startup_delays or {}
    heartbeat_events = heartbeat_events or {}

    def enhanced_mock_train(
        config: Dict[str, Any], logger: Any, *args: Any, **kwargs: Any
    ) -> Any:
        job_key = (
            config.get("test_param")
            or config.get("priority_test")
            or config.get("job_number", "default")
        )

        # Handle startup delay if specified
        startup_event = startup_delays.get(job_key)
        if startup_event:
            startup_event.wait(timeout=5)

        execution_order.append(job_key)

        # Signal heartbeat events if monitoring heartbeats
        heartbeat_event = heartbeat_events.get(job_key)
        if heartbeat_event:
            heartbeat_event.set()

        # Signal completion if event provided
        completion_event = completion_events.get(job_key)
        if completion_event:
            completion_event.set()

        # Return configured result
        default_result = create_success_result(
            final_metrics={
                "final_val_acc": 0.95,
                "final_train_loss": 0.1,
                "final_val_loss": 0.15,
            },
            epochs=1,
            logger_meta={"metrics_path": "test_metrics.jsonl", "num_checkpoints": 0},
            artifacts_path=logger.paths.artifact_dir,
            training_time=0.1,
        )
        return results.get(job_key, default_result)

    with patch(
        "dr_exp.train_examples.dummy_trainer.train", side_effect=enhanced_mock_train
    ):
        yield execution_order


@pytest.fixture
def worker_coordination() -> Any:
    """Utilities for coordinating multiple workers in tests."""

    class WorkerCoordination:
        def __init__(self) -> None:
            self.worker_events: Dict[str, Dict[str, threading.Event]] = {}
            self.worker_results: Dict[str, Any] = {}
            self.worker_threads: Dict[str, Any] = {}

        def create_worker_event(self, worker_id: str) -> Dict[str, threading.Event]:
            """Create coordination event for a worker."""
            if worker_id not in self.worker_events:
                self.worker_events[worker_id] = {
                    "start": threading.Event(),
                    "can_complete": threading.Event(),
                    "completed": threading.Event(),
                }
            return self.worker_events[worker_id]

        def wait_for_workers_to_start(
            self, worker_ids: List[str], timeout: int = 5
        ) -> bool:
            """Wait for multiple workers to start."""
            for worker_id in worker_ids:
                events = self.worker_events.get(worker_id, {})
                start_event = events.get("start")
                if start_event:
                    if not start_event.wait(timeout):
                        return False
                else:
                    return False
            return True

        def allow_workers_to_complete(self, worker_ids: List[str]) -> None:
            """Allow multiple workers to complete."""
            for worker_id in worker_ids:
                events = self.worker_events.get(worker_id, {})
                complete_event = events.get("can_complete")
                if complete_event:
                    complete_event.set()

        def wait_for_workers_to_complete(
            self, worker_ids: List[str], timeout: int = 10
        ) -> bool:
            """Wait for multiple workers to complete."""
            for worker_id in worker_ids:
                events = self.worker_events.get(worker_id, {})
                completed_event = events.get("completed")
                if completed_event:
                    if not completed_event.wait(timeout):
                        return False
                else:
                    return False
            return True

        def create_coordinated_trainer(
            self, worker_id: str
        ) -> Callable[[Dict[str, Any], Any], Any]:
            """Create a trainer function that coordinates with events."""

            def coordinated_trainer(
                config: Dict[str, Any], logger: Any, *args: Any, **kwargs: Any
            ) -> Any:
                events = self.create_worker_event(worker_id)

                # Signal worker started
                events["start"].set()

                # Wait for permission to complete
                events["can_complete"].wait(timeout=10)

                # Do work and signal completion
                result = create_success_result(
                    final_metrics={
                        "final_val_acc": 0.95,
                        "final_train_loss": 0.1,
                        "final_val_loss": 0.15,
                    },
                    epochs=1,
                    logger_meta={
                        "metrics_path": "test_metrics.jsonl",
                        "num_checkpoints": 0,
                    },
                    artifacts_path=logger.paths.artifact_dir,
                    training_time=0.1,
                )
                events["completed"].set()

                return result

            return coordinated_trainer

    return WorkerCoordination()


# Skip Supabase tests by default unless explicitly enabled
def pytest_collection_modifyitems(
    config: pytest.Config, items: List[pytest.Item]
) -> None:
    """Modify test collection to handle Supabase tests."""
    skip_supabase = pytest.mark.skip(
        reason="Supabase tests require EXPMGR_MODE=supabase_local and RUN_SUPABASE_TESTS=1"
    )

    for item in items:
        # Skip Supabase integration tests unless explicitly enabled
        if "supabase_integration" in str(item.fspath):
            if not (
                os.getenv("EXPMGR_MODE") == "supabase_local"
                and os.getenv("RUN_SUPABASE_TESTS") == "1"
            ):
                item.add_marker(skip_supabase)
