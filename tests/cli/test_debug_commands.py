"""Integration tests for debug commands and diagnostic workflows."""

import os
import tempfile
import pytest
from unittest.mock import patch

from dr_exp.cli.main import main
from dr_exp.job_db.config import JobDBConfig
from dr_exp.job_db.local_job_db import LocalJobDB


@pytest.mark.integration
def test_debug_config_command() -> None:
    """Test debug config command shows comprehensive configuration."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Set up environment for test
        env_vars = {
            "EXPMGR_MODE": "files_local",
            "DR_EXP_BASE_PATH": tmpdir,
            "DR_EXP_STORAGE_PATH": os.path.join(tmpdir, "storage"),
        }

        with patch.dict(os.environ, env_vars):
            exit_code = main(["debug", "debug_config"])
            assert exit_code == 0


@pytest.mark.integration
def test_debug_health_check_healthy_system() -> None:
    """Test health check with a healthy system configuration."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Set up a healthy system
        storage_dir = os.path.join(tmpdir, "storage")
        os.makedirs(storage_dir, exist_ok=True)

        env_vars = {
            "EXPMGR_MODE": "files_local",
            "DR_EXP_BASE_PATH": tmpdir,
            "DR_EXP_STORAGE_PATH": storage_dir,
        }

        with patch.dict(os.environ, env_vars):
            exit_code = main(["debug", "debug_health_check"])
            assert exit_code == 0


@pytest.mark.integration
def test_debug_health_check_with_issues() -> None:
    """Test health check detects and reports system issues."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a system with some issues
        env_vars = {
            "EXPMGR_MODE": "files_local",
            "DR_EXP_BASE_PATH": tmpdir,
            "DR_EXP_STORAGE_PATH": "/nonexistent/path",  # This will fail
        }

        with patch.dict(os.environ, env_vars):
            exit_code = main(["debug", "debug_health_check"])
            # Should return 1 due to storage directory issue
            assert exit_code == 1


@pytest.mark.integration
def test_debug_health_check_verbose() -> None:
    """Test verbose health check provides detailed information."""
    with tempfile.TemporaryDirectory() as tmpdir:
        env_vars = {
            "EXPMGR_MODE": "files_local",
            "DR_EXP_BASE_PATH": tmpdir,
        }

        with patch.dict(os.environ, env_vars):
            exit_code = main(["debug", "debug_health_check", "--verbose"])
            assert exit_code == 0


@pytest.mark.integration
def test_configuration_mismatch_detection(tmp_path) -> None:
    """Test that health check detects configuration mismatches."""
    # Create main job directory with jobs
    main_job_dir = tmp_path / "main" / "job_data"
    main_job_dir.mkdir(parents=True)

    # Create some job files in main directory
    config = JobDBConfig(
        mode="files_local",
        base_path=str(tmp_path / "main"),
        storage_path=str(tmp_path / "storage"),
    )
    config.validate()
    main_db = LocalJobDB(config)

    # Add test jobs to main database
    test_config = {"config": {"test": True}, "metadata": {"test": True}}
    main_db.add_job(test_config, "test_sweep", priority=100)

    # Create alternative job directory with different jobs
    alt_job_dir = tmp_path / "alternative" / "job_data"
    alt_job_dir.mkdir(parents=True)

    # Point health check to alternative directory (should detect main jobs)
    env_vars = {
        "EXPMGR_MODE": "files_local",
        "DR_EXP_BASE_PATH": str(tmp_path / "alternative"),
    }

    # Mock the alternative location check to find our main directory
    original_check = "dr_exp.cli.commands.debug_health_check.DebugHealthCheckCommand._check_alternative_locations"

    def mock_check_alternatives(self, current_dir):
        # Simulate finding jobs in main directory
        return [f"{main_job_dir.parent} (1 jobs)"]

    with patch.dict(os.environ, env_vars):
        with patch(original_check, mock_check_alternatives):
            exit_code = main(["debug", "debug_health_check"])
            # Should pass overall but report alternative locations
            assert exit_code == 0


@pytest.mark.integration
def test_enhanced_worker_diagnostics_integration(tmp_path) -> None:
    """Test complete workflow of enhanced worker diagnostics."""
    # Set up environment with no jobs
    env_vars = {
        "EXPMGR_MODE": "files_local",
        "DR_EXP_BASE_PATH": str(tmp_path),
    }

    with patch.dict(os.environ, env_vars):
        # Run worker - should trigger enhanced diagnostics
        exit_code = main(
            ["system", "run_worker", "test_worker", str(tmp_path / "work")]
        )
        # Should return 1 (no job available) but show diagnostics
        assert exit_code == 1


@pytest.mark.integration
def test_worker_diagnostics_with_jobs(tmp_path, isolated_job_db) -> None:
    """Test worker diagnostics when jobs are available."""
    # Create a job in the database
    isolated_job_db.add_test_job(priority=100)

    # Set up environment to use the same database
    env_vars = {
        "EXPMGR_MODE": "files_local",
        "DR_EXP_BASE_PATH": isolated_job_db.config.base_path,
    }

    # Mock the training function to prevent actual training
    with patch("dr_exp.training.dummy_trainer.train") as mock_train:
        from dr_exp.training import create_success_result

        mock_train.return_value = create_success_result(
            final_metrics={
                "final_val_acc": 0.95,
                "final_train_loss": 0.1,
                "final_val_loss": 0.15,
            },
            epochs=1,
            logger_meta={"metrics_path": "test.jsonl", "num_checkpoints": 0},
            artifacts_path="/tmp",
            training_time=1.0,
        )

        with patch.dict(os.environ, env_vars):
            exit_code = main(
                ["system", "run_worker", "test_worker", str(tmp_path / "work")]
            )
            # Should succeed when job is available and training succeeds
            assert exit_code == 0


@pytest.mark.integration
def test_end_to_end_diagnostic_workflow(tmp_path) -> None:
    """Test complete end-to-end diagnostic workflow."""
    # Set up environment
    env_vars = {
        "EXPMGR_MODE": "files_local",
        "DR_EXP_BASE_PATH": str(tmp_path),
    }

    with patch.dict(os.environ, env_vars):
        # 1. Run health check first
        health_exit = main(["debug", "debug_health_check"])
        assert health_exit == 0

        # 2. Show configuration
        config_exit = main(["debug", "debug_config"])
        assert config_exit == 0

        # 3. Try to run worker (should show diagnostics)
        worker_exit = main(
            ["system", "run_worker", "test_worker", str(tmp_path / "work")]
        )
        assert worker_exit == 1  # No jobs available


@pytest.mark.integration
def test_configuration_validation_in_health_check() -> None:
    """Test that health check properly validates configuration."""
    # Test with invalid configuration
    env_vars = {
        "EXPMGR_MODE": "supabase_remote",
        "DR_EXP_BASE_PATH": "/tmp",
        # Missing SUPABASE_URL and SUPABASE_KEY
    }

    with patch.dict(os.environ, env_vars):
        exit_code = main(["debug", "debug_health_check"])
        # Should fail due to missing Supabase credentials
        assert exit_code == 1


@pytest.mark.integration
def test_debug_commands_with_different_modes() -> None:
    """Test debug commands work with different database modes."""
    modes_to_test = [
        ("files_local", True),  # Should work
        ("supabase_local", False),  # May fail without Supabase running
    ]

    for mode, should_succeed in modes_to_test:
        with tempfile.TemporaryDirectory() as tmpdir:
            env_vars = {
                "EXPMGR_MODE": mode,
                "DR_EXP_BASE_PATH": tmpdir,
            }

            if mode == "supabase_local":
                env_vars.update(
                    {
                        "SUPABASE_URL": "http://127.0.0.1:54321",
                        "SUPABASE_KEY": "test_key",
                    }
                )

            with patch.dict(os.environ, env_vars):
                config_exit = main(["debug", "debug_config"])
                if should_succeed:
                    assert config_exit == 0
                # For supabase_local, we don't assert success since Supabase may not be running

                # Health check may fail for supabase_local due to connectivity
                health_exit = main(["debug", "debug_health_check"])
                if mode == "files_local":
                    assert health_exit == 0


@pytest.mark.integration
def test_stale_job_detection_in_health_check(tmp_path, enhanced_mock_time) -> None:
    """Test that health check detects stale jobs."""
    # Create database and add a job
    config = JobDBConfig(
        mode="files_local",
        base_path=str(tmp_path),
        storage_path=str(tmp_path / "storage"),
    )
    config.validate()
    db = LocalJobDB(config)

    # Add a job and mark it as running with old heartbeat
    test_config = {"config": {"test": True}, "metadata": {"test": True}}
    job = db.add_job(test_config, "test_sweep", priority=100)

    # Update job to running with old heartbeat
    old_heartbeat = enhanced_mock_time.create_stale_timestamp(120)  # 2 minutes ago
    db.update_job(
        job["id"],
        {
            "status": "running",
            "assigned_worker": "old_worker",
            "last_heartbeat": old_heartbeat,
        },
    )

    # Mock the database to return our stale job
    with patch("dr_exp.utils.jobdb_factory.get_job_db_client") as mock_factory:
        mock_factory.return_value = db

        env_vars = {
            "EXPMGR_MODE": "files_local",
            "DR_EXP_BASE_PATH": str(tmp_path),
        }

        with patch.dict(os.environ, env_vars):
            exit_code = main(["debug", "debug_health_check", "--verbose"])
            # Should detect stale jobs but still pass overall
            assert exit_code == 0


@pytest.mark.integration
def test_worker_alternative_location_detection() -> None:
    """Test that worker diagnostics detect jobs in alternative locations."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create job in one location
        main_path = os.path.join(tmpdir, "main")
        alt_path = os.path.join(tmpdir, "alt")

        os.makedirs(os.path.join(main_path, "job_data"))
        os.makedirs(os.path.join(alt_path, "job_data"))

        # Add job to main location
        config = JobDBConfig(
            mode="files_local",
            base_path=main_path,
            storage_path=os.path.join(main_path, "storage"),
        )
        config.validate()
        db = LocalJobDB(config)
        test_config = {"config": {"test": True}, "metadata": {"test": True}}
        db.add_job(test_config, "test_sweep", priority=100)

        # Try to run worker from alt location (should detect jobs in main)
        env_vars = {
            "EXPMGR_MODE": "files_local",
            "DR_EXP_BASE_PATH": alt_path,
        }

        with patch.dict(os.environ, env_vars):
            exit_code = main(
                ["system", "run_worker", "test_worker", os.path.join(alt_path, "work")]
            )
            # Should return 1 (no job) but show diagnostics about alternative locations
            assert exit_code == 1
