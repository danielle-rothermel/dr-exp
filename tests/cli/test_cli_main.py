"""Tests for CLI main functionality."""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from dr_exp.cli.main import main, build_parser
from dr_exp.utils.cli_validation import ValidationError


def test_build_parser() -> None:
    """Test that the parser builds correctly."""
    parser = build_parser()
    assert parser is not None

    # Test help doesn't crash
    with pytest.raises(SystemExit):
        parser.parse_args(["--help"])


def test_main_with_help() -> None:
    """Test main function with help argument."""
    with pytest.raises(SystemExit) as exc_info:
        main(["--help"])
    assert exc_info.value.code == 0


def test_main_with_invalid_group() -> None:
    """Test main function with invalid group."""
    # ArgumentParser exits with code 2 for invalid arguments
    with pytest.raises(SystemExit) as exc_info:
        main(["invalid_group"])
    assert exc_info.value.code == 2


def test_system_status_command(tmp_path: Path) -> None:
    """Test system status command."""
    # Mock the system creation to avoid actual system setup
    with patch(
        "dr_exp.cli.commands.status.StatusCommand.create_system_from_args"
    ) as mock_create:
        mock_system = MagicMock()
        mock_system.get_system_status.return_value = {
            "configuration": {
                "mode": "test",
                "gpus": ["0"],
                "workers_per_gpu": 1,
                "total_worker_capacity": 1,
                "heartbeat_timeout": 60,
                "manager_base_dir": "/test",
            },
            "environment": {
                "scheduler": "local",
                "job_id": None,
                "node_name": "test",
                "cuda_visible_devices": None,
                "process_id": 12345,
            },
            "job_status": {
                "running_jobs": 0,
                "has_queued_jobs": False,
                "stale_jobs": 0,
            },
            "queue_preview": [],
            "stale_jobs_preview": [],
        }
        mock_create.return_value = mock_system

        exit_code = main(
            ["system", "status", "--base-path", str(tmp_path), "--mode", "files_local"]
        )
        assert exit_code == 0
        mock_system.get_system_status.assert_called_once()


def test_system_discover_gpus_command(tmp_path: Path) -> None:
    """Test system discover-gpus command."""
    with patch("dr_exp.cli.commands.discover_gpus.discover_gpus") as mock_discover:
        mock_discover.return_value = ["0", "1"]

        exit_code = main(
            [
                "system",
                "discover_gpus",
                "--base-path",
                str(tmp_path),
                "--mode",
                "files_local",
            ]
        )
        assert exit_code == 0
        mock_discover.assert_called_once()


def test_validation_error_handling(tmp_path: Path) -> None:
    """Test that validation errors are handled properly."""
    with patch(
        "dr_exp.cli.commands.discover_gpus.validate_positive_int"
    ) as mock_validate:
        mock_validate.side_effect = ValidationError("Test validation error")

        exit_code = main(
            [
                "system",
                "discover_gpus",
                "--base-path",
                str(tmp_path),
                "--mode",
                "files_local",
                "--gpus-per-node",
                "0",
            ]
        )
        assert exit_code == 1


def test_keyboard_interrupt_handling(tmp_path: Path) -> None:
    """Test keyboard interrupt handling."""
    with patch(
        "dr_exp.cli.commands.status.StatusCommand.create_system_from_args"
    ) as mock_create:
        mock_create.side_effect = KeyboardInterrupt()

        exit_code = main(
            ["system", "status", "--base-path", str(tmp_path), "--mode", "files_local"]
        )
        assert exit_code == 1


def test_unexpected_error_handling(tmp_path: Path) -> None:
    """Test unexpected error handling."""
    with patch(
        "dr_exp.cli.commands.status.StatusCommand.create_system_from_args"
    ) as mock_create:
        mock_create.side_effect = RuntimeError("Unexpected error")

        exit_code = main(
            ["system", "status", "--base-path", str(tmp_path), "--mode", "files_local"]
        )
        assert exit_code == 1
