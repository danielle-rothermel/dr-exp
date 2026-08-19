"""Validation tests for worker logging functionality."""

from pathlib import Path

from dr_exp.core.job_db import JobDB
from dr_exp.worker.base import Worker


def test_worker_creates_log_file(tmp_path: Path) -> None:
    job_db = JobDB(base_path=str(tmp_path), experiment_name="test_exp", validate=False)

    job_db.create_job(
        config={"_target_": "dr_exp.training.dummy_trainer.train", "epochs": 1},
        priority=100,
    )

    worker = Worker(
        worker_id="test_worker",
        job_db=job_db,
        working_dir=str(tmp_path / "work"),
        experiment_path=str(tmp_path / "test_exp"),
    )

    stats = worker.run(max_jobs=1)

    log_file = tmp_path / "test_exp" / "logs" / "worker_test_worker.log"
    assert log_file.exists()

    log_content = log_file.read_text()
    assert "Worker test_worker started at" in log_content
    assert "Experiment: test_exp" in log_content
    assert "Dummy trainer started" in log_content
    assert "completed successfully" in log_content
    assert stats["completed"] == 1


def test_worker_log_append_mode(tmp_path: Path) -> None:
    job_db = JobDB(base_path=str(tmp_path), experiment_name="test_exp", validate=False)

    log_dir = tmp_path / "test_exp" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "worker_test_worker.log"
    log_file.write_text("Previous run content\n")

    worker = Worker(
        worker_id="test_worker",
        job_db=job_db,
        working_dir=str(tmp_path / "work"),
        experiment_path=str(tmp_path / "test_exp"),
    )

    worker.shutdown("test")

    log_content = log_file.read_text()
    assert "Previous run content" in log_content
    assert "Worker test_worker started at" in log_content


def test_worker_log_on_error(tmp_path: Path) -> None:
    job_db = JobDB(base_path=str(tmp_path), experiment_name="test_exp", validate=False)

    job_db.create_job(
        config={
            "_target_": "dr_exp.training.dummy_trainer.train",
            "epochs": 1,
            "fail_rate": 1.0,
        },
        priority=100,
    )

    worker = Worker(
        worker_id="error_worker",
        job_db=job_db,
        working_dir=str(tmp_path / "work"),
        experiment_path=str(tmp_path / "test_exp"),
    )

    stats = worker.run(max_jobs=1)

    log_file = tmp_path / "test_exp" / "logs" / "worker_error_worker.log"
    log_content = log_file.read_text()
    assert "failed" in log_content
    assert "RuntimeError" in log_content
    assert stats["failed"] == 1
