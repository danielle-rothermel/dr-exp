import os

from dr_exp.mock.supabase_mock_client import SupabaseMockClient
import dr_exp.worker as run_worker


def make_config():
    return {"train": {"num_epochs": 2}, "logging": {}}


def test_worker_success(tmp_path):
    client = SupabaseMockClient(base_path=str(tmp_path))
    job = client.add_job(make_config(), "sweep1", status="queued")

    work_dir = tmp_path / "work"
    status = run_worker.run_worker(
        base_path=str(tmp_path),
        work_dir=str(work_dir),
        heartbeat_interval=0.01,
        client=client,
        worker_id="w0",
    )

    assert status == "completed"
    job_data = client.get_job_details(job["id"])
    assert job_data["status"] == "completed"
    assert job_data["assigned_worker"] == "w0"
    assert "upload_complete_at" in job_data
    assert not work_dir.exists()

    storage_run = os.path.join(client.mock_storage_path, f"run_{job['id']}")
    assert os.path.exists(os.path.join(storage_run, "metrics.jsonl"))
    bundle_dir = os.path.join(storage_run, "artifacts", "bundle")
    assert os.path.isdir(bundle_dir)


def test_worker_no_job(tmp_path):
    client = SupabaseMockClient(base_path=str(tmp_path))
    work_dir = tmp_path / "work"
    result = run_worker.run_worker(
        base_path=str(tmp_path),
        work_dir=str(work_dir),
        max_claim_attempts=2,
        heartbeat_interval=0.01,
        client=client,
        worker_id="wid",
    )
    assert result == "no_job"
    assert not work_dir.exists()


def test_worker_training_failure(tmp_path):
    client = SupabaseMockClient(base_path=str(tmp_path))
    job = client.add_job(make_config(), "sweep1", status="queued")

    def failing_train(cfg, logger):
        raise RuntimeError("boom")

    work_dir = tmp_path / "work"
    status = run_worker.run_worker(
        base_path=str(tmp_path),
        work_dir=str(work_dir),
        heartbeat_interval=0.01,
        trainer_fn=failing_train,
        client=client,
        worker_id="wfail",
    )

    assert status == "failed"
    job_data = client.get_job_details(job["id"])
    assert job_data["status"] == "failed"

    errors_file = os.path.join(client.mock_db_path, "errors.jsonl")
    with open(errors_file) as f:
        data = f.read()
    assert "RuntimeError" in data
