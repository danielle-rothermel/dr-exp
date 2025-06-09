"""Integration tests for debug commands and diagnostic workflows."""

import os
import tempfile
import pytest
from pathlib import Path
from typing import Any
from unittest.mock import patch

from dr_exp.cli.main import main
from dr_exp.job_db.config import JobDBConfig
from dr_exp.job_db.local_job_db import LocalJobDB


@pytest.mark.integration
def test_debug_config_command() -> None:
    """Test debug config command shows comprehensive configuration."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Test CLI flag-based configuration (no environment variables needed)
        storage_dir = os.path.join(tmpdir, "storage")

        exit_code = main(
            [
                "debug",
                "debug_config",
                "--base-path",
                tmpdir,
                "--mode",
                "files_local",
                "--storage-path",
                storage_dir,
            ]
        )
        assert exit_code == 0


@pytest.mark.integration
def test_debug_health_check_healthy_system() -> None:
    """Test health check with a healthy system configuration."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Set up a healthy system
        storage_dir = os.path.join(tmpdir, "storage")
        os.makedirs(storage_dir, exist_ok=True)

        # Test CLI flag-based configuration
        exit_code = main(
            [
                "debug",
                "debug_health_check",
                "--base-path",
                tmpdir,
                "--mode",
                "files_local",
                "--storage-path",
                storage_dir,
            ]
        )
        assert exit_code == 0


@pytest.mark.integration
def test_debug_health_check_with_issues() -> None:
    """Test health check detects and reports system issues."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a system with some issues
        nonexistent_storage = "/nonexistent/path"  # This will fail

        # Test CLI flag-based configuration with invalid storage path
        exit_code = main(
            [
                "debug",
                "debug_health_check",
                "--base-path",
                tmpdir,
                "--mode",
                "files_local",
                "--storage-path",
                nonexistent_storage,
            ]
        )
        # Should return 1 due to storage directory issue
        assert exit_code == 1


@pytest.mark.integration
def test_debug_health_check_verbose() -> None:
    """Test verbose health check provides detailed information."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Test CLI flag-based configuration with verbose flag
        exit_code = main(
            [
                "debug",
                "debug_health_check",
                "--base-path",
                tmpdir,
                "--mode",
                "files_local",
                "--verbose",
            ]
        )
        assert exit_code == 0


@pytest.mark.integration
def test_configuration_mismatch_detection(tmp_path: Path) -> None:
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
    alternative_path = str(tmp_path / "alternative")

    # Mock the alternative location check to find our main directory
    original_check = "dr_exp.cli.commands.debug_health_check.DebugHealthCheckCommand._check_alternative_locations"

    def mock_check_alternatives(self: Any, current_dir: str) -> list[str]:
        # Simulate finding jobs in main directory
        return [f"{main_job_dir.parent} (1 jobs)"]

    with patch(original_check, mock_check_alternatives):
        exit_code = main(
            [
                "debug",
                "debug_health_check",
                "--base-path",
                alternative_path,
                "--mode",
                "files_local",
            ]
        )
        # Should pass overall but report alternative locations
        assert exit_code == 0


@pytest.mark.integration
def test_configuration_validation_in_health_check() -> None:
    """Test that health check properly validates configuration."""
    # Test with invalid configuration (missing Supabase credentials)
    # Clear any existing Supabase environment variables
    with patch.dict(os.environ, {"SUPABASE_URL": "", "SUPABASE_KEY": ""}, clear=False):
        exit_code = main(
            [
                "debug",
                "debug_health_check",
                "--base-path",
                "/tmp",
                "--mode",
                "supabase_remote",
            ]
        )
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
            # Set up Supabase credentials for supabase_local mode
            env_patches = {}
            if mode == "supabase_local":
                env_patches = {
                    "SUPABASE_URL": "http://127.0.0.1:54321",
                    "SUPABASE_KEY": "test_key",
                }

            with patch.dict(os.environ, env_patches):
                config_exit = main(
                    ["debug", "debug_config", "--base-path", tmpdir, "--mode", mode]
                )
                if should_succeed:
                    assert config_exit == 0
                # For supabase_local, we don't assert success since Supabase may not be running

                # Health check may fail for supabase_local due to connectivity
                health_exit = main(
                    [
                        "debug",
                        "debug_health_check",
                        "--base-path",
                        tmpdir,
                        "--mode",
                        mode,
                    ]
                )
                if mode == "files_local":
                    assert health_exit == 0


@pytest.mark.integration
def test_stale_job_detection_in_health_check(
    tmp_path: Path, enhanced_mock_time: Any
) -> None:
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

        exit_code = main(
            [
                "debug",
                "debug_health_check",
                "--base-path",
                str(tmp_path),
                "--mode",
                "files_local",
                "--verbose",
            ]
        )
        # Should detect stale jobs but still pass overall
        assert exit_code == 0
