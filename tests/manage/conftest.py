"""Enhanced fixtures specific to manager-worker integration tests."""

import pytest
import threading
from unittest.mock import patch
from pathlib import Path
from typing import Any, Dict, List, Optional, Callable

from dr_exp.manage.manager import Manager
from dr_exp.manage.process_manager import MockProcessManager
from dr_exp.manage.worker import run_worker


@pytest.fixture
def integration_manager(integration_system: Any, enhanced_mock_time: Any) -> Manager:
    """Manager configured for integration testing with enhanced timing control."""
    manager = Manager(
        gpus=integration_system.config.gpus,
        workers_per_gpu=integration_system.config.workers_per_gpu,
        heartbeat_timeout=integration_system.config.heartbeat_timeout,
        idle_timeout_mins=integration_system.config.idle_timeout_mins,
        base_dir=str(
            Path(integration_system.config.job_db_config.base_path) / "manager"
        ),
        client=integration_system.job_db,
        process_manager=MockProcessManager(),
    )
    return manager


@pytest.fixture
def heartbeat_monitor() -> Any:
    """Utility for monitoring heartbeat updates during worker execution."""

    class HeartbeatMonitor:
        def __init__(self) -> None:
            self.heartbeat_updates = []
            self.heartbeat_events = {}
            self.original_update_method = None

        def start_monitoring(
            self, job_db: Any, job_id: Optional[str] = None, required_count: int = 2
        ) -> Any:
            """Start monitoring heartbeat updates."""
            self.original_update_method = job_db.update_job

            def track_heartbeat_updates(
                job_id_param: str, updates: Dict[str, Any]
            ) -> Any:
                if "heartbeat" in updates:
                    self.heartbeat_updates.append(
                        {
                            "job_id": job_id_param,
                            "timestamp": updates["heartbeat"],
                            "count": len(self.heartbeat_updates) + 1,
                        }
                    )

                    # Signal events based on heartbeat count
                    if len(self.heartbeat_updates) >= required_count:
                        if "sufficient_heartbeats" not in self.heartbeat_events:
                            self.heartbeat_events["sufficient_heartbeats"] = (
                                threading.Event()
                            )
                        self.heartbeat_events["sufficient_heartbeats"].set()

                return self.original_update_method(job_id_param, updates)

            return patch.object(
                job_db, "update_job", side_effect=track_heartbeat_updates
            )

        def wait_for_heartbeats(self, count: int = 2, timeout: int = 5) -> bool:
            """Wait for a specific number of heartbeats."""
            if "sufficient_heartbeats" not in self.heartbeat_events:
                self.heartbeat_events["sufficient_heartbeats"] = threading.Event()

            # Check if we already have enough
            if len(self.heartbeat_updates) >= count:
                return True

            return self.heartbeat_events["sufficient_heartbeats"].wait(timeout)

        def get_heartbeat_count(self, job_id: Optional[str] = None) -> int:
            """Get heartbeat count for specific job or total."""
            if job_id:
                return len([h for h in self.heartbeat_updates if h["job_id"] == job_id])
            return len(self.heartbeat_updates)

        def reset(self) -> None:
            """Reset monitoring state."""
            self.heartbeat_updates.clear()
            self.heartbeat_events.clear()

    return HeartbeatMonitor()


@pytest.fixture
def stale_job_detector(enhanced_mock_time: Any) -> Any:
    """Utility for testing stale job detection with deterministic timing."""

    class StaleJobDetector:
        def __init__(self, mock_time: Any) -> None:
            self.mock_time = mock_time

        def create_stale_job(
            self,
            job_db: Any,
            heartbeat_age_seconds: int,
            config: Optional[Dict[str, Any]] = None,
        ) -> Dict[str, Any]:
            """Create a job with a stale heartbeat."""
            if config is None:
                config = {"test": "stale_job"}

            # Add job
            job = job_db.add_job(config, "stale_sweep", status="queued", priority=100)

            # Claim job (simulates worker taking it)
            claimed_job = job_db.claim_job("dead_worker")
            assert claimed_job is not None

            # Set stale heartbeat
            stale_timestamp = self.mock_time.create_stale_timestamp(
                heartbeat_age_seconds
            )
            job_db.update_job(job["id"], {"heartbeat": stale_timestamp})

            return job

        def advance_time_for_stale_detection(self, heartbeat_timeout: int) -> None:
            """Advance time to trigger stale job detection."""
            self.mock_time.advance_to_make_stale(heartbeat_timeout)

        def create_mock_datetime_patch(self) -> tuple[Callable, Callable]:
            """Create a patch for datetime module in job_db for stale detection."""
            from datetime import datetime, UTC

            def create_patch() -> Any:
                return patch("dr_exp.job_db.local_job_db.datetime")

            def configure_patch(mock_datetime: Any) -> Any:
                mock_datetime.now.return_value = self.mock_time.now()
                mock_datetime.UTC = UTC
                mock_datetime.fromisoformat = datetime.fromisoformat
                return mock_datetime

            return create_patch, configure_patch

    return StaleJobDetector(enhanced_mock_time)


@pytest.fixture
def worker_execution_helper(integration_system: Any) -> Any:
    """Helper for executing workers with consistent patterns."""

    class WorkerExecutionHelper:
        def __init__(self, system: Any) -> None:
            self.system = system
            self.execution_results = []

        def run_worker_with_trainer(
            self, trainer_fn: Callable, worker_id: Optional[str] = None, **kwargs: Any
        ) -> Any:
            """Run worker with specified trainer function."""
            if worker_id is None:
                worker_id = f"test_worker_{len(self.execution_results)}"

            # Merge with default parameters
            run_params = {
                "base_path": self.system.config.job_db_config.base_path,
                "max_claim_attempts": self.system.config.max_claim_attempts,
                "heartbeat_interval": self.system.config.worker_heartbeat_interval,
                "trainer_fn": trainer_fn,
                "client": self.system.job_db,
                "worker_id": worker_id,
            }
            run_params.update(kwargs)

            status = run_worker(**run_params)

            result = {"worker_id": worker_id, "status": status, "params": run_params}
            self.execution_results.append(result)

            return status

        def run_coordinated_worker(
            self,
            coordination: Any,
            worker_id: str,
            trainer_fn: Optional[Callable] = None,
        ) -> threading.Thread:
            """Run worker with coordination events."""
            if trainer_fn is None:
                trainer_fn = coordination.create_coordinated_trainer(worker_id)

            def worker_thread() -> None:
                status = self.run_worker_with_trainer(trainer_fn, worker_id)
                self.execution_results[-1]["thread_status"] = status

            thread = threading.Thread(target=worker_thread)
            thread.start()
            return thread

        def get_last_result(self) -> Optional[Dict[str, Any]]:
            """Get the most recent execution result."""
            return self.execution_results[-1] if self.execution_results else None

        def get_results_by_status(self, status: str) -> List[Dict[str, Any]]:
            """Get all results with specific status."""
            return [r for r in self.execution_results if r["status"] == status]

    return WorkerExecutionHelper(integration_system)


@pytest.fixture
def priority_job_factory(isolated_job_db: Any) -> Any:
    """Factory for creating jobs with specific priority patterns."""

    class PriorityJobFactory:
        def __init__(self, job_db: Any) -> None:
            self.job_db = job_db

        def create_priority_sequence(
            self, priorities: List[int], base_config: Optional[Dict[str, Any]] = None
        ) -> List[Dict[str, Any]]:
            """Create jobs with specified priorities for testing execution order."""
            if base_config is None:
                base_config = {}

            jobs = []
            for i, priority in enumerate(priorities):
                config = base_config.copy()
                config["priority_test"] = f"priority_{priority}"
                config["job_index"] = i

                job = self.job_db.add_test_job(
                    config_override=config,
                    priority=priority,
                    sweep_name="priority_test_sweep",
                )
                jobs.append(job)

            return jobs

        def create_mixed_priority_jobs(self, count: int = 5) -> List[Dict[str, Any]]:
            """Create jobs with mixed priorities for realistic testing."""
            import random

            priorities = random.sample(range(100, 1000, 50), count)
            return self.create_priority_sequence(priorities)

        def create_high_medium_low_jobs(self) -> List[Dict[str, Any]]:
            """Create the classic high/medium/low priority test set."""
            return self.create_priority_sequence(
                [900, 500, 100], {"test_type": "priority_ordering"}
            )

    return PriorityJobFactory(isolated_job_db)
