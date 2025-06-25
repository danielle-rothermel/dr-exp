"""Tests for Hydra configuration fixes."""

import yaml
from pathlib import Path
from click.testing import CliRunner
from dr_exp.cli.main import cli


def test_hydra_config_composition(tmp_path: Path) -> None:
    # Create config structure
    config_dir = tmp_path / "configs"
    config_dir.mkdir()

    # Create base config with composition
    base_config = {
        "defaults": ["model"],
        "_target_": "dr_exp.trainers.test_trainer.train",
        "epochs": 10,
    }
    (config_dir / "train.yaml").write_text(yaml.dump(base_config))

    # Create model config
    model_config = {"layers": 3, "hidden_size": 128}
    (config_dir / "model.yaml").write_text(yaml.dump(model_config))

    # Create experiment
    exp_path = tmp_path / "experiment"
    runner = CliRunner()
    result = runner.invoke(
        cli, ["--base-path", str(tmp_path), "--experiment", "experiment", "init"]
    )
    assert result.exit_code == 0

    # Submit with composition
    result = runner.invoke(
        cli,
        [
            "--base-path",
            str(tmp_path),
            "--experiment",
            "experiment",
            "submit",
            "--config-path",
            str(config_dir),
            "--config-name",
            "train",
        ],
    )
    assert result.exit_code == 0
    assert "Created job:" in result.output

    # Verify composed config
    job_files = list((exp_path / "jobs").glob("*.json"))
    assert len(job_files) == 1

    import json

    job_data = json.loads(job_files[0].read_text())
    assert job_data["config"]["layers"] == 3  # From composed model.yaml
    assert job_data["config"]["epochs"] == 10  # From train.yaml


def test_overrides(tmp_path: Path) -> None:
    # Create simple config
    config_dir = tmp_path / "configs"
    config_dir.mkdir()

    config = {
        "_target_": "dr_exp.trainers.test_trainer.train",
        "epochs": 10,
        "lr": 0.01,
    }
    (config_dir / "train.yaml").write_text(yaml.dump(config))

    # Create experiment
    runner = CliRunner()
    runner.invoke(
        cli, ["--base-path", str(tmp_path), "--experiment", "experiment", "init"]
    )

    # Submit with overrides
    result = runner.invoke(
        cli,
        [
            "--base-path",
            str(tmp_path),
            "--experiment",
            "experiment",
            "submit",
            "--config-path",
            str(config_dir),
            "--config-name",
            "train",
            "--overrides",
            "epochs=20,lr=0.001",
        ],
    )
    assert result.exit_code == 0

    # Verify overrides applied
    exp_path = tmp_path / "experiment"
    job_files = list((exp_path / "jobs").glob("*.json"))

    import json

    job_data = json.loads(job_files[0].read_text())
    assert job_data["config"]["epochs"] == 20
    assert job_data["config"]["lr"] == 0.001
