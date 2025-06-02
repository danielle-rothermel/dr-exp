# ruff: noqa: E402
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(ROOT / "src"))  # noqa: E402
sys.path.append(str(ROOT))  # noqa: E402

import json
import time
from multiprocessing import Process

import pytest
from fastapi.testclient import TestClient

import dr_exp.manager as manager
from dr_exp.backend.main import create_app
from dr_exp.mock.supabase_mock_client import SupabaseMockClient
from dr_exp import config_upload

CONFIG_DIR = Path(__file__).resolve().parents[2] / "configs"


def create_jobs(client: SupabaseMockClient, sweep: str) -> list[dict]:
    return config_upload.upload_configs(
        base_config_path=str(CONFIG_DIR),
        config_name="config.yaml",
        sweep=sweep,
        client=client,
        cluster_name="local",
        description="test",
        interface_version="v1",
        code_version="1",
    )


def wait_for_workers(mgr: manager.Manager) -> None:
    for info in mgr.workers.values():
        proc: Process = info["process"]  # type: ignore[assignment]
        proc.join()


@pytest.fixture
def api_client(tmp_path, monkeypatch):
    monkeypatch.setenv("ADMIN_API_KEY", "secret")
    app = create_app(base_path=str(tmp_path))
    return TestClient(app)


@pytest.fixture
def sb_client(api_client):
    return api_client.app.state.client


def test_full_sweep_lifecycle(tmp_path, api_client, sb_client):
    jobs = create_jobs(sb_client, "model=resnet,vit")
    mgr_dir = tmp_path / "mgr"
    mgr = manager.Manager(
        gpus=["0"],
        workers_per_gpu=2,
        heartbeat_interval=0.1,
        idle_timeout_mins=1,
        base_dir=str(mgr_dir),
        client=sb_client,
    )
    mgr.start_workers()
    wait_for_workers(mgr)

    for job in jobs:
        resp = api_client.get(f"/job/{job['id']}")
        assert resp.status_code == 200
        assert resp.json()["status"] == "completed"
        m = api_client.get(f"/metrics/{job['id']}")
        assert m.status_code == 200
        assert len(m.json()["metrics"]) > 0


def test_job_failure(tmp_path, api_client, sb_client, monkeypatch):
    jobs = create_jobs(sb_client, "model=resnet,vit")
    fail_job = jobs[0]
    path = Path(sb_client.jobs_dir) / f"{fail_job['id']}.json"
    data = json.loads(path.read_text())
    data["config_json"]["fail"] = True
    path.write_text(json.dumps(data))

    import dr_exp.worker as rw

    orig_run_worker = rw.run_worker
    orig_train = rw.default_train

    def maybe_fail(cfg, logger):
        if cfg.get("fail"):
            raise RuntimeError("boom")
        return orig_train(cfg, logger)

    def run_worker_wrapper(
        base_path: str = ".", work_dir: str | None = None, worker_id: str = "id"
    ):
        orig_run_worker(
            base_path=base_path,
            work_dir=work_dir,
            trainer_fn=maybe_fail,
            worker_id=worker_id,
        )

    monkeypatch.setattr(manager._run_worker, "run_worker", run_worker_wrapper)

    mgr_dir = tmp_path / "mgr"
    mgr = manager.Manager(
        gpus=["0"],
        workers_per_gpu=2,
        heartbeat_interval=0.1,
        idle_timeout_mins=1,
        base_dir=str(mgr_dir),
        client=sb_client,
    )
    mgr.start_workers()
    wait_for_workers(mgr)

    resp = api_client.get(f"/job/{fail_job['id']}")
    assert resp.json()["status"] == "failed"
    ok = api_client.get(f"/job/{jobs[1]['id']}")
    assert ok.json()["status"] == "completed"

    errors_file = Path(sb_client.mock_db_path) / "errors.jsonl"
    data = errors_file.read_text()
    assert "RuntimeError" in data


def test_job_control_api(tmp_path, api_client, sb_client, monkeypatch):
    [job] = create_jobs(sb_client, "model=resnet")

    import dr_exp.worker as rw

    def slow_train(cfg, logger):
        for _ in range(5):
            time.sleep(0.05)
            logger.log({"step": 1})
        return {
            "status": "success",
            "final_val_acc": 0,
            "final_train_loss": 0,
            "num_epochs": 5,
        }

    orig_run_worker = rw.run_worker

    def run_worker_wrapper(
        base_path: str = ".", work_dir: str | None = None, worker_id: str = "id"
    ):
        orig_run_worker(
            base_path=base_path,
            work_dir=work_dir,
            trainer_fn=slow_train,
            worker_id=worker_id,
        )

    monkeypatch.setattr(manager._run_worker, "run_worker", run_worker_wrapper)

    mgr_dir = tmp_path / "mgr"
    mgr = manager.Manager(
        gpus=["0"],
        workers_per_gpu=1,
        heartbeat_interval=0.1,
        idle_timeout_mins=1,
        base_dir=str(mgr_dir),
        client=sb_client,
    )
    mgr.start_workers()

    time.sleep(0.1)
    api_client.post(
        "/job/kill", json={"job_id": job["id"]}, headers={"X-API-Key": "secret"}
    )

    wait_for_workers(mgr)

    job_data = sb_client.get_job_details(job["id"])
    assert job_data.get("kill_requested") is True

    api_client.post(
        "/job/requeue", json={"job_id": job["id"]}, headers={"X-API-Key": "secret"}
    )
    job_data = sb_client.get_job_details(job["id"])
    assert job_data["status"] == "queued"
    assert job_data["retry_index"] == 1


def test_jobs_list_endpoint(tmp_path, api_client, sb_client):
    jobs = create_jobs(sb_client, "model=resnet,vit")

    mgr_dir = tmp_path / "mgr"
    mgr = manager.Manager(
        gpus=["0"],
        workers_per_gpu=2,
        heartbeat_interval=0.1,
        idle_timeout_mins=1,
        base_dir=str(mgr_dir),
        client=sb_client,
    )
    mgr.start_workers()
    wait_for_workers(mgr)

    resp = api_client.get("/jobs")
    assert resp.status_code == 200
    data = {j["id"]: j for j in resp.json()}
    for job in jobs:
        assert data[job["id"]]["status"] == "completed"
