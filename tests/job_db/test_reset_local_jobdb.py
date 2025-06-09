import os
from pathlib import Path
import pytest
from scripts.reset_local_jobdb import reset_job_db


def create_mock_environment(base_path: str) -> None:
    # Create the new directory structure
    job_data_dir = os.path.join(base_path, "job_data")
    storage_dir = os.path.join(base_path, "storage")

    os.makedirs(job_data_dir, exist_ok=True)
    os.makedirs(storage_dir, exist_ok=True)

    # create sample files
    with open(os.path.join(job_data_dir, "job1.json"), "w") as f:
        f.write("{}")
    with open(os.path.join(job_data_dir, "job_database_errors.jsonl"), "w") as f:
        f.write("error\n")
    with open(os.path.join(storage_dir, "artifact.txt"), "w") as f:
        f.write("data")


def test_reset_mock_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    base = str(tmp_path)
    storage_path = str(tmp_path / "storage")

    create_mock_environment(base)

    # ensure files exist before reset
    job_data_dir = os.path.join(base, "job_data")
    storage_dir = storage_path

    assert os.listdir(job_data_dir)
    assert os.path.exists(os.path.join(job_data_dir, "job_database_errors.jsonl"))
    assert os.listdir(storage_dir)

    # Call reset_job_db with explicit parameters
    reset_job_db(base_path=base, mode="files_local", storage_path=storage_path)

    # directories should be recreated and mostly empty
    assert os.path.isdir(job_data_dir)
    assert os.path.isdir(storage_dir)
    assert os.path.isfile(os.path.join(job_data_dir, "job_database_errors.jsonl"))

    # The reset should have cleared these
    assert os.listdir(job_data_dir) == [
        "job_database_errors.jsonl",
    ]  # Only structure remains

    # Storage should be empty after reset
    assert os.listdir(storage_dir) == []
