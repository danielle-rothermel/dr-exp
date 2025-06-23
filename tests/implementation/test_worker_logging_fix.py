from src.dr_exp.worker.base import Worker
from dr_exp.core.job_db import JobDB


def test_worker_creates_log_file(tmp_path):
    # Create experiment
    job_db = JobDB(base_path=str(tmp_path), experiment_name="test_exp", validate=False)

    # Create a job
    job_db.create_job(
        config={"_target_": "src.dr_exp.trainers.test_trainer.train", "epochs": 1},
        priority=100,
    )

    # Run worker
    worker = Worker(
        worker_id="test_worker",
        job_db=job_db,
        working_dir=str(tmp_path / "work"),
        experiment_path=str(tmp_path / "test_exp"),
        sync_enabled=False,
    )

    stats = worker.run(max_jobs=1)

    # Check log file exists
    log_file = tmp_path / "test_exp" / "logs" / "worker_test_worker.log"
    assert log_file.exists()

    # Check log content
    log_content = log_file.read_text()
    assert "Worker test_worker started at" in log_content
    assert "Experiment: test_exp" in log_content
    assert "Test trainer started" in log_content  # From test trainer output
    assert "completed successfully" in log_content
    assert stats["completed"] == 1


def test_worker_log_append_mode(tmp_path):
    # Create experiment
    job_db = JobDB(base_path=str(tmp_path), experiment_name="test_exp", validate=False)

    log_dir = tmp_path / "test_exp" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "worker_test_worker.log"

    # Write initial content
    log_file.write_text("Previous run content\n")

    # Create and run worker (no jobs, just initialization)
    worker = Worker(
        worker_id="test_worker",
        job_db=job_db,
        working_dir=str(tmp_path / "work"),
        experiment_path=str(tmp_path / "test_exp"),
        sync_enabled=False,
    )

    # Just initialize to test logging setup
    worker.shutdown("test")

    # Check previous content preserved
    log_content = log_file.read_text()
    assert "Previous run content" in log_content
    assert "Worker test_worker started at" in log_content


def test_worker_log_on_error(tmp_path):
    # Create experiment
    job_db = JobDB(base_path=str(tmp_path), experiment_name="test_exp", validate=False)

    # Create failing job
    job_db.create_job(
        config={
            "_target_": "src.dr_exp.trainers.test_trainer.train",
            "epochs": 1,
            "fail_rate": 1.0,
        },
        priority=100,
    )

    # Run worker
    worker = Worker(
        worker_id="error_worker",
        job_db=job_db,
        working_dir=str(tmp_path / "work"),
        experiment_path=str(tmp_path / "test_exp"),
        sync_enabled=False,
    )

    stats = worker.run(max_jobs=1)

    # Check error logged
    log_file = tmp_path / "test_exp" / "logs" / "worker_error_worker.log"
    log_content = log_file.read_text()
    assert "failed" in log_content
    assert "RuntimeError" in log_content
    assert stats["failed"] == 1
