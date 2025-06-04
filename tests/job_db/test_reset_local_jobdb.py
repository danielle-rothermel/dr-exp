import os
from scripts.reset_mock_db import reset_mock_db


def create_mock_environment(base_path: str) -> None:
    os.makedirs(os.path.join(base_path, "mock_db", "jobs"), exist_ok=True)
    os.makedirs(os.path.join(base_path, "mock_db", "metrics"), exist_ok=True)
    os.makedirs(os.path.join(base_path, "mock_storage"), exist_ok=True)
    # create sample files
    with open(os.path.join(base_path, "mock_db", "jobs", "job1.json"), "w") as f:
        f.write("{}")
    with open(os.path.join(base_path, "mock_db", "metrics", "job1.jsonl"), "w") as f:
        f.write("{}\n")
    with open(os.path.join(base_path, "mock_db", "errors.jsonl"), "w") as f:
        f.write("error\n")
    with open(os.path.join(base_path, "mock_storage", "artifact.txt"), "w") as f:
        f.write("data")


def test_reset_mock_db(tmp_path):
    base = str(tmp_path)
    create_mock_environment(base)

    # ensure files exist before reset
    assert os.listdir(os.path.join(base, "mock_db", "jobs"))
    assert os.listdir(os.path.join(base, "mock_db", "metrics"))
    assert os.path.exists(os.path.join(base, "mock_db", "errors.jsonl"))
    assert os.listdir(os.path.join(base, "mock_storage"))

    reset_mock_db(base)

    # directories recreated and empty
    jobs_dir = os.path.join(base, "mock_db", "jobs")
    metrics_dir = os.path.join(base, "mock_db", "metrics")
    storage_dir = os.path.join(base, "mock_storage")
    errors_file = os.path.join(base, "mock_db", "errors.jsonl")

    assert os.path.isdir(jobs_dir)
    assert os.path.isdir(metrics_dir)
    assert os.path.isdir(storage_dir)
    assert os.path.isfile(errors_file)
    assert os.listdir(jobs_dir) == []
    assert os.listdir(metrics_dir) == []
    assert os.listdir(storage_dir) == []
    with open(errors_file, "r") as f:
        assert f.read() == ""
