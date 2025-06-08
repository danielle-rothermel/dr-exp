import os
from unittest.mock import patch
from scripts.reset_local_jobdb import reset_job_db
from dr_exp.job_db import JobDBConfig


def create_mock_environment(base_path: str) -> None:
    # Create the new directory structure
    job_data_dir = os.path.join(base_path, "job_data")
    storage_dir = os.path.join(base_path, "storage")

    os.makedirs(job_data_dir, exist_ok=True)
    os.makedirs(os.path.join(job_data_dir, "metrics"), exist_ok=True)
    os.makedirs(storage_dir, exist_ok=True)

    # create sample files
    with open(os.path.join(job_data_dir, "job1.json"), "w") as f:
        f.write("{}")
    with open(os.path.join(job_data_dir, "metrics", "job1.jsonl"), "w") as f:
        f.write("{}\n")
    with open(os.path.join(job_data_dir, "errors.jsonl"), "w") as f:
        f.write("error\n")
    with open(os.path.join(storage_dir, "artifact.txt"), "w") as f:
        f.write("data")


def test_reset_mock_db(tmp_path, monkeypatch):
    base = str(tmp_path)
    storage_path = str(tmp_path / "storage")

    # Mock the config to use our test paths
    mock_config = JobDBConfig(
        base_path=base, storage_path=storage_path, mode="files_local"
    )

    with patch("scripts.reset_local_jobdb.JobDBConfig.from_env") as mock_from_env:
        mock_from_env.return_value = mock_config

        create_mock_environment(base)

        # ensure files exist before reset
        job_data_dir = os.path.join(base, "job_data")
        storage_dir = storage_path

        assert os.listdir(job_data_dir)
        assert os.listdir(os.path.join(job_data_dir, "metrics"))
        assert os.path.exists(os.path.join(job_data_dir, "errors.jsonl"))
        assert os.listdir(storage_dir)

        reset_job_db()

        # directories should be recreated and mostly empty
        assert os.path.isdir(job_data_dir)
        assert os.path.isdir(os.path.join(job_data_dir, "metrics"))
        assert os.path.isdir(storage_dir)
        assert os.path.isfile(os.path.join(job_data_dir, "errors.jsonl"))

        # The reset should have cleared these
        assert os.listdir(job_data_dir) == [
            "metrics",
            "errors.jsonl",
        ]  # Only structure remains
        assert os.listdir(os.path.join(job_data_dir, "metrics")) == []

        # Storage should be empty after reset
        assert os.listdir(storage_dir) == []
