"""Test config sweep functionality."""

import tempfile
from pathlib import Path
from click.testing import CliRunner

import pytest

from dr_exp.core.job_db import JobDB
from dr_exp.cli.sweep_utils import (
    parse_sweep_params,
    generate_sweep_configs,
    validate_sweep_config,
)
from dr_exp.cli.main import cli


def test_parse_sweep_params() -> None:
    """Test parsing sweep parameter strings."""
    # Basic parsing
    params = parse_sweep_params("model=resnet18,resnet50 lr=0.001,0.01")
    assert params == {"model": ["resnet18", "resnet50"], "lr": ["0.001", "0.01"]}

    # Nested parameters
    params = parse_sweep_params("optim.lr=0.1,0.01 model.layers=12,24")
    assert params == {"optim.lr": ["0.1", "0.01"], "model.layers": ["12", "24"]}

    # Single values
    params = parse_sweep_params("epochs=100")
    assert params == {"epochs": ["100"]}

    # Empty string
    params = parse_sweep_params("")
    assert params == {}

    # Invalid format (no equals)
    params = parse_sweep_params("invalid_param another_invalid")
    assert params == {}


def test_generate_configs() -> None:
    """Test config generation from sweeps."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create test config
        config_dir = Path(tmpdir) / "configs"
        config_dir.mkdir()

        config_file = config_dir / "test.yaml"
        config_file.write_text("""
_target_: dr_exp.training.dummy_trainer.train_dummy
model: resnet18
lr: 0.001
epochs: 10
""")

        # Generate configs
        sweep_params = {"model": ["resnet18", "resnet50"], "lr": ["0.001", "0.01"]}
        configs = generate_sweep_configs(str(config_file), sweep_params)

        # Should have 2x2=4 configs
        assert len(configs) == 4

        # Check all combinations exist
        combinations = []
        for cfg in configs:
            combinations.append((cfg["model"], cfg["lr"]))

        assert ("resnet18", 0.001) in combinations
        assert ("resnet18", 0.01) in combinations
        assert ("resnet50", 0.001) in combinations
        assert ("resnet50", 0.01) in combinations

        # All should have the target
        for cfg in configs:
            assert cfg["_target_"] == "dr_exp.training.dummy_trainer.train_dummy"


def test_validate_config() -> None:
    """Test config validation."""
    # Valid config
    config = {"_target_": "dr_exp.training.dummy_trainer.train_dummy", "epochs": 10}
    validate_sweep_config(config)  # Should not raise

    # Missing target
    with pytest.raises(AssertionError, match="_target_"):
        validate_sweep_config({"epochs": 10})

    # Invalid target
    with pytest.raises(AssertionError, match="Cannot import"):
        validate_sweep_config({"_target_": "nonexistent.module.func"})


def test_sweep_cli_dry_run() -> None:
    """Test sweep CLI command in dry-run mode."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Setup
        job_db = JobDB(base_path=tmpdir, experiment_name="test_exp", validate=False)

        # Create test config
        config_file = Path(tmpdir) / "test.yaml"
        config_file.write_text("""
_target_: dr_exp.training.dummy_trainer.train_dummy
model: resnet18
lr: 0.001
epochs: 10
""")

        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "--base-path",
                tmpdir,
                "--experiment",
                "test_exp",
                "job",
                "sweep",
                "--config",
                str(config_file),
                "--params",
                "model=resnet18,resnet50 lr=0.001,0.01",
                "--dry-run",
            ],
        )

        assert result.exit_code == 0
        assert "Generating 4 configurations" in result.output
        assert "Config 1/4" in result.output
        assert "Config 4/4" in result.output
        assert "resnet18" in result.output
        assert "resnet50" in result.output

        # No jobs should be created
        jobs = job_db.list_jobs()
        assert len(jobs) == 0


def test_sweep_cli_create_jobs() -> None:
    """Test sweep CLI command creating actual jobs."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Setup
        job_db = JobDB(base_path=tmpdir, experiment_name="test_exp", validate=False)

        # Create test config
        config_file = Path(tmpdir) / "test.yaml"
        config_file.write_text("""
_target_: dr_exp.training.dummy_trainer.train_dummy
epochs: 10
batch_size: 32
""")

        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "--base-path",
                tmpdir,
                "--experiment",
                "test_exp",
                "job",
                "sweep",
                "--config",
                str(config_file),
                "--params",
                "epochs=10,20,30",
                "--priority",
                "500",
            ],
        )

        assert result.exit_code == 0
        assert "Created: 3 jobs" in result.output

        # Check jobs were created
        jobs = job_db.list_jobs()
        assert len(jobs) == 3

        # Check each job has correct config
        epochs_values = [job["config"]["epochs"] for job in jobs]
        assert sorted(epochs_values) == [10, 20, 30]

        # All should have priority 500
        for job in jobs:
            assert job["priority"] == 500


def test_sweep_with_target_override() -> None:
    """Test sweep with target override."""
    with tempfile.TemporaryDirectory() as tmpdir:
        job_db = JobDB(base_path=tmpdir, experiment_name="test_exp", validate=False)

        # Config without _target_
        config_file = Path(tmpdir) / "base.yaml"
        config_file.write_text("""
model: resnet18
lr: 0.001
""")

        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "--base-path",
                tmpdir,
                "--experiment",
                "test_exp",
                "job",
                "sweep",
                "--config",
                str(config_file),
                "--params",
                "lr=0.1,0.01",
                "--target",
                "dr_exp.training.dummy_trainer.train_dummy",
                "--priority",
                "300",
            ],
        )

        assert result.exit_code == 0
        assert "Created: 2 jobs" in result.output

        # Check jobs have the target
        jobs = job_db.list_jobs()
        assert len(jobs) == 2
        for job in jobs:
            assert (
                job["config"]["_target_"] == "dr_exp.training.dummy_trainer.train_dummy"
            )


def test_large_sweep_progress() -> None:
    """Test progress reporting for large sweeps."""
    with tempfile.TemporaryDirectory() as tmpdir:
        JobDB(base_path=tmpdir, experiment_name="test_exp", validate=False)

        config_file = Path(tmpdir) / "test.yaml"
        config_file.write_text("""
_target_: dr_exp.training.dummy_trainer.train_dummy
model: resnet18
lr: 0.001
batch_size: 32
epochs: 10
""")

        # Create a large sweep (3x3x3 = 27 jobs)
        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "--base-path",
                tmpdir,
                "--experiment",
                "test_exp",
                "job",
                "sweep",
                "--config",
                str(config_file),
                "--params",
                "lr=0.1,0.01,0.001 batch_size=16,32,64 epochs=10,20,30",
            ],
        )

        if result.exit_code != 0:
            print(f"Command failed with output: {result.output}")
        assert result.exit_code == 0
        assert "Generating 27 configurations" in result.output
        assert "Progress:" in result.output  # Should show progress
        assert "Created: 27 jobs" in result.output
