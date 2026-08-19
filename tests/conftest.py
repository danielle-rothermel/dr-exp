"""Base test fixtures for dr_exp test suite."""

import pytest
import tempfile
from pathlib import Path
from collections.abc import Generator
from dr_exp.core.job_db import JobDB


@pytest.fixture
def temp_experiment_dir() -> Generator[Path, None, None]:
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def temp_job_db(temp_experiment_dir: Path) -> JobDB:
    return JobDB(
        base_path=str(temp_experiment_dir), experiment_name="test_exp", validate=False
    )


@pytest.fixture
def mock_config() -> dict[str, str | int | float]:
    return {
        "_target_": "dr_exp.training.dummy_trainer.train",
        "epochs": 10,
        "lr": 0.001,
    }
