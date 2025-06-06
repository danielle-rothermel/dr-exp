from multiprocessing import Process
import zipfile
from pathlib import Path

from dr_exp.job_db import LocalJobDB, JobDBConfig, JobDBConfig
import dr_exp.manage.manager_logic as manager


def make_config():
    return {"train": {"num_epochs": 1}, "logging": {}}


def test_manager_worker_flow(tmp_path, monkeypatch):
    base_path = tmp_path
    client = LocalJobDB(JobDBConfig(base_path=str(base_path, storage_path=str(base_path + "/storage", mode="files_local")), storage_path=str(base_path / "storage")
    )
    job = client.add_job(make_config(), "sweep1", status="queued")

    mgr_dir = tmp_path / "mgr"
    monkeypatch.setenv("DR_EXP_BASE_PATH", str(tmp_path))
    mgr = manager.Manager(
        gpus=["0"],
        workers_per_gpu=1,
        heartbeat_interval=0.1,
        idle_timeout_mins=1,
        base_dir=str(mgr_dir),
        client=client,
    )
    monkeypatch.chdir(tmp_path)
    mgr.start_workers()
    for info in mgr.workers.values():
        proc: Process = info["process"]  # type: ignore[assignment]
        proc.join()

    data = client.get_job_details(job["id"])
    assert data["status"] == "completed"

    storage_run = Path(client.storage_dir) / f"run_{job['id']}"
    assert (storage_run / "metrics.jsonl").exists()
    bundle_zip = storage_run / "bundle.zip"
    assert bundle_zip.exists()
    with zipfile.ZipFile(bundle_zip) as zf:
        names = zf.namelist()
        assert "worker.log" in names
        assert any(n.startswith("checkpoints/") for n in names)
    assert (mgr_dir / "manager.log").exists()
