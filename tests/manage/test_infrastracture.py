"""Test demonstration of Phase 2 enhanced test infrastructure.

This module showcases the new testing patterns and fixtures developed for Phase 2.
These tests serve as both validation of the infrastructure and examples for future development.
"""

import threading

from dr_exp.manage.worker import run_worker
from dr_exp.training import create_success_result
from tests.conftest import make_wrapped_config


class TestEnhancedTimeFixtures:
    """Demonstrate enhanced time-controlled testing patterns."""

    def test_milestone_based_timing(self, enhanced_mock_time, isolated_job_db):
        """Test using named milestones for time coordination."""
        # Create a job that will be checked for staleness
        job = isolated_job_db.add_test_job({"test": "milestone_timing"})

        # Set initial heartbeat at current time
        enhanced_mock_time.set_milestone("job_started")
        heartbeat_time = enhanced_mock_time.now()
        isolated_job_db.update_job(
            job["id"], {"heartbeat": heartbeat_time.isoformat() + "Z"}
        )

        # Advance to make job stale with named milestone
        enhanced_mock_time.advance_to_make_stale(heartbeat_timeout=10)
        assert enhanced_mock_time.get_milestone("stale_jobs_detected") is not None

        # Verify the time progression
        start_time = enhanced_mock_time.get_milestone("job_started")
        stale_time = enhanced_mock_time.get_milestone("stale_jobs_detected")
        time_diff = (stale_time - start_time).total_seconds()
        assert time_diff >= 25  # Should be at least 2*10 + 5 buffer

    def test_event_coordination_with_timing(self, enhanced_mock_time):
        """Test event coordination with milestone timing."""
        # Start waiting for a milestone in a thread
        milestone_reached = threading.Event()

        def wait_for_milestone():
            if enhanced_mock_time.wait_for_milestone("test_event", timeout=2):
                milestone_reached.set()

        thread = threading.Thread(target=wait_for_milestone)
        thread.start()

        # Advance time and set milestone
        enhanced_mock_time.advance(10, "test_event")

        # Verify event coordination worked
        thread.join(timeout=3)
        assert milestone_reached.is_set()


class TestDatabaseStateManagement:
    """Demonstrate enhanced database state management utilities."""

    def test_job_creation_patterns(self, isolated_job_db):
        """Test standardized job creation patterns."""
        # Create jobs with realistic priority distribution
        jobs = isolated_job_db.create_test_jobs(count=5, priority_range=(200, 800))

        assert len(jobs) == 5
        # Verify priority distribution
        priorities = [job["priority"] for job in jobs]
        assert min(priorities) >= 200
        assert max(priorities) <= 800
        assert len(set(priorities)) == 5  # All different priorities

    def test_state_verification_utilities(self, isolated_job_db):
        """Test database state verification helpers."""
        # Create jobs in different states
        isolated_job_db.add_test_job({"state": "queued"}, status="queued")
        isolated_job_db.add_test_job({"state": "running"}, status="running")
        isolated_job_db.add_test_job({"state": "completed"}, status="completed")

        # Verify counts
        isolated_job_db.verify_job_counts({"queued": 1, "running": 1, "completed": 1})

        # Verify specific statuses
        all_jobs = isolated_job_db.list_jobs()
        job_statuses = {job["id"]: job["status"] for job in all_jobs}
        isolated_job_db.verify_job_statuses(job_statuses)

    def test_database_isolation(self, isolated_job_db):
        """Test that database isolation works correctly."""
        # Add some jobs
        _job1 = isolated_job_db.add_test_job({"test": "isolation_1"})
        _job2 = isolated_job_db.add_test_job({"test": "isolation_2"})

        # Verify jobs exist
        assert len(isolated_job_db.list_jobs()) == 2

        # Reset state
        isolated_job_db.reset_state()

        # Verify clean slate
        assert len(isolated_job_db.list_jobs()) == 0


class TestEventDrivenUtilities:
    """Demonstrate event-driven test coordination utilities."""

    def test_worker_coordination_basic(self, worker_coordination, integration_system):
        """Test basic worker coordination patterns."""
        worker_id = "coordinated_worker_1"

        # Create worker events first
        worker_coordination.create_worker_event(worker_id)

        # Create coordinated trainer
        trainer_fn = worker_coordination.create_coordinated_trainer(worker_id)

        # Add a job for the worker
        _job = integration_system.job_db.add_job(
            make_wrapped_config({"test": "coordination"}),
            "coord_sweep",
            status="queued",
            priority=100,
        )

        # Run worker in thread
        result = []
        exception_caught = []

        def run_coordinated_worker():
            try:
                status = run_worker(
                    base_path=integration_system.config.job_db_config.base_path,
                    max_claim_attempts=integration_system.config.max_claim_attempts,
                    heartbeat_interval=integration_system.config.worker_heartbeat_interval,
                    trainer_fn=trainer_fn,
                    client=integration_system.job_db,
                    worker_id=worker_id,
                )
                result.append(status)
            except Exception as e:
                exception_caught.append(str(e))

        thread = threading.Thread(target=run_coordinated_worker)
        thread.start()

        # Wait for worker to start
        worker_started = worker_coordination.wait_for_workers_to_start(
            [worker_id], timeout=10
        )
        assert worker_started, (
            f"Worker {worker_id} did not start. Exceptions: {exception_caught}"
        )

        # Allow worker to complete
        worker_coordination.allow_workers_to_complete([worker_id])

        # Wait for completion
        worker_completed = worker_coordination.wait_for_workers_to_complete(
            [worker_id], timeout=10
        )
        thread.join(timeout=10)

        # Check for exceptions
        if exception_caught:
            assert False, (
                f"Worker execution failed with exception: {exception_caught[0]}"
            )

        # Verify result
        assert len(result) == 1, (
            f"Expected 1 result, got {len(result)}. Completed: {worker_completed}"
        )
        assert result[0] == "completed"

    def test_multiple_worker_coordination(
        self, worker_coordination, integration_system
    ):
        """Test coordination of multiple workers."""
        worker_ids = ["worker_1", "worker_2", "worker_3"]

        # Create events for all workers first
        for worker_id in worker_ids:
            worker_coordination.create_worker_event(worker_id)

        # Add jobs for workers
        for i, worker_id in enumerate(worker_ids):
            integration_system.job_db.add_job(
                make_wrapped_config({"worker": worker_id, "job_num": i}),
                "multi_coord_sweep",
                status="queued",
                priority=100 + i,
            )

        # Start all workers
        threads = []
        results = []

        for worker_id in worker_ids:
            trainer_fn = worker_coordination.create_coordinated_trainer(worker_id)

            def create_worker_runner(wid, tfn):
                def run():
                    status = run_worker(
                        base_path=integration_system.config.job_db_config.base_path,
                        max_claim_attempts=integration_system.config.max_claim_attempts,
                        heartbeat_interval=integration_system.config.worker_heartbeat_interval,
                        trainer_fn=tfn,
                        client=integration_system.job_db,
                        worker_id=wid,
                    )
                    results.append({"worker_id": wid, "status": status})

                return run

            thread = threading.Thread(
                target=create_worker_runner(worker_id, trainer_fn)
            )
            thread.start()
            threads.append(thread)

        # Wait for all workers to start
        worker_coordination.wait_for_workers_to_start(worker_ids)

        # Allow all workers to complete
        worker_coordination.allow_workers_to_complete(worker_ids)

        # Wait for all workers to complete
        worker_coordination.wait_for_workers_to_complete(worker_ids)

        # Wait for threads
        for thread in threads:
            thread.join(timeout=5)

        # Since only 3 jobs exist and workers claim jobs individually,
        # we should have exactly 3 completed workers (one per job)
        completed_workers = [r for r in results if r["status"] == "completed"]
        _no_work_workers = [r for r in results if r["status"] == "no_work"]

        assert len(completed_workers) == 3, (
            f"Expected 3 completed workers, got {len(completed_workers)}"
        )
        assert len(results) == 3, f"Expected 3 total results, got {len(results)}"


class TestManageSpecificFixtures:
    """Demonstrate manage-specific enhanced fixtures."""

    def test_heartbeat_monitoring(self, heartbeat_monitor, integration_system):
        """Test heartbeat monitoring utilities."""
        # Add a job
        _job = integration_system.job_db.add_job(
            make_wrapped_config({"test": "heartbeat_monitoring"}),
            "hb_sweep",
            status="queued",
            priority=100,
        )

        # Start monitoring
        with heartbeat_monitor.start_monitoring(
            integration_system.job_db, required_count=2
        ):
            # Create a trainer that simulates longer execution
            execution_started = threading.Event()
            can_complete = threading.Event()

            def mock_train_with_heartbeat(config, logger, *args, **kwargs):
                execution_started.set()
                can_complete.wait(timeout=5)
                return create_success_result(
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

            # Run worker in thread
            result = []

            def run_worker_thread():
                status = run_worker(
                    base_path=integration_system.config.job_db_config.base_path,
                    max_claim_attempts=integration_system.config.max_claim_attempts,
                    heartbeat_interval=integration_system.config.worker_heartbeat_interval,
                    trainer_fn=mock_train_with_heartbeat,
                    client=integration_system.job_db,
                    worker_id="heartbeat_test_worker",
                )
                result.append(status)

            worker_thread = threading.Thread(target=run_worker_thread)
            worker_thread.start()

            # Wait for execution to start
            assert execution_started.wait(timeout=5)

            # Wait for sufficient heartbeats
            assert heartbeat_monitor.wait_for_heartbeats(count=2, timeout=5)

            # Allow completion
            can_complete.set()

            # Wait for worker to complete
            worker_thread.join(timeout=10)
            assert len(result) == 1
            assert result[0] == "completed"

        # Verify heartbeat count
        assert heartbeat_monitor.get_heartbeat_count() >= 2

    def test_stale_job_detection_helper(self, stale_job_detector, integration_manager):
        """Test stale job detection helper utilities."""
        # Create a stale job
        stale_job = stale_job_detector.create_stale_job(
            integration_manager.job_db,
            heartbeat_age_seconds=30,
            config={"test": "stale_detection_helper"},
        )

        # Advance time for stale detection
        stale_job_detector.advance_time_for_stale_detection(
            heartbeat_timeout=integration_manager.heartbeat_timeout
        )

        # Create datetime patch
        create_patch, configure_patch = stale_job_detector.create_mock_datetime_patch()

        with create_patch() as mock_datetime:
            configure_patch(mock_datetime)

            # Check for stale jobs
            integration_manager.check_stale_jobs()

        # Verify job was marked as failed
        job_details = integration_manager.job_db.get_job_details(stale_job["id"])
        assert job_details["status"] == "failed"
        assert "worker_lost" in job_details.get("status_reason", "")

    def test_priority_job_factory(self, priority_job_factory, worker_execution_helper):
        """Test priority job factory and execution helper."""
        # Create high/medium/low priority jobs
        jobs = priority_job_factory.create_high_medium_low_jobs()
        assert len(jobs) == 3

        # Verify priority ordering
        priorities = [job["priority"] for job in jobs]
        assert priorities == [900, 500, 100]

        # Track execution order
        execution_order = []

        def priority_tracking_trainer(config, logger, *args, **kwargs):
            priority_level = config.get("priority_test")
            execution_order.append(priority_level)
            return create_success_result(
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

        # Execute all jobs
        for _ in range(3):
            status = worker_execution_helper.run_worker_with_trainer(
                priority_tracking_trainer
            )
            assert status == "completed"

        # Verify execution order (high to low priority)
        assert execution_order == ["priority_900", "priority_500", "priority_100"]


class TestInfrastructureIntegration:
    """Test integration of all Phase 2 infrastructure components."""

    def test_complete_enhanced_workflow(
        self,
        enhanced_mock_time,
        isolated_job_db,
        worker_coordination,
        heartbeat_monitor,
        integration_system,
    ):
        """Test a complete workflow using all enhanced infrastructure."""
        # Phase 1: Setup with timing milestones
        enhanced_mock_time.set_milestone("test_start")

        # Phase 2: Create test jobs
        _jobs = isolated_job_db.create_test_jobs(count=2, priority_range=(100, 200))
        isolated_job_db.verify_job_counts({"queued": 2})

        # Phase 3: Setup worker coordination
        worker_ids = ["enhanced_worker_1", "enhanced_worker_2"]
        execution_order = []

        # Phase 4: Setup heartbeat monitoring
        with heartbeat_monitor.start_monitoring(isolated_job_db):
            # Phase 5: Execute workers with coordination
            threads = []
            results = []

            for worker_id in worker_ids:

                def create_enhanced_trainer(wid):
                    def enhanced_trainer(config, logger, *args, **kwargs):
                        # Track execution
                        job_key = config.get("job_number", "unknown")
                        execution_order.append(f"{wid}_job_{job_key}")

                        # Coordinate with events
                        events = worker_coordination.create_worker_event(wid)
                        events["start"].set()
                        events["can_complete"].wait(timeout=10)

                        return create_success_result(
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

                    return enhanced_trainer

                trainer_fn = create_enhanced_trainer(worker_id)

                def create_worker_runner(wid, tfn):
                    def run():
                        status = run_worker(
                            base_path=integration_system.config.job_db_config.base_path,
                            max_claim_attempts=integration_system.config.max_claim_attempts,
                            heartbeat_interval=integration_system.config.worker_heartbeat_interval,
                            trainer_fn=tfn,
                            client=isolated_job_db,
                            worker_id=wid,
                        )
                        results.append({"worker_id": wid, "status": status})

                    return run

                thread = threading.Thread(
                    target=create_worker_runner(worker_id, trainer_fn)
                )
                thread.start()
                threads.append(thread)

            # Phase 6: Coordinate execution
            worker_coordination.wait_for_workers_to_start(worker_ids)
            enhanced_mock_time.advance(5, "workers_started")

            # Wait for some heartbeats
            heartbeat_monitor.wait_for_heartbeats(count=2, timeout=5)
            enhanced_mock_time.advance(2, "heartbeats_received")

            # Allow completion
            worker_coordination.allow_workers_to_complete(worker_ids)
            worker_coordination.wait_for_workers_to_complete(worker_ids)

            # Wait for threads
            for thread in threads:
                thread.join(timeout=10)

        # Phase 7: Verify results with enhanced infrastructure
        enhanced_mock_time.set_milestone("test_complete")

        # Verify worker execution
        assert len(results) == 2
        assert all(r["status"] == "completed" for r in results)

        # Verify job completion
        isolated_job_db.verify_job_counts({"completed": 2})

        # Verify timing progression
        start_time = enhanced_mock_time.get_milestone("test_start")
        complete_time = enhanced_mock_time.get_milestone("test_complete")
        assert complete_time > start_time

        # Verify heartbeat monitoring
        assert heartbeat_monitor.get_heartbeat_count() >= 2

        # Verify execution tracking
        assert len(execution_order) == 2
        assert all("enhanced_worker_" in entry for entry in execution_order)
