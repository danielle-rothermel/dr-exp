import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from dr_exp.api.main import create_app


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("ADMIN_API_KEY", "secret")
    app = create_app(base_path=str(tmp_path))
    return app


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.fixture
def sb_client(app):
    return app.state.client


def test_get_job_and_config(client, sb_client):
    cfg = {"model": {"name": "resnet"}}
    job = sb_client.add_job(cfg, "sweep1", status="queued")
    job_id = job["id"]

    resp = client.get(f"/job/{job_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == job_id
    assert data["status"] == "queued"

    cfg_resp = client.get(f"/config/{job_id}")
    assert cfg_resp.status_code == 200
    assert cfg_resp.json()["config"] == cfg


def test_metrics_endpoint(client, sb_client, tmp_path):
    job = sb_client.add_job({"a": 1}, "sweep1", status="running")
    run_id = job["id"]
    run_dir = Path(sb_client.mock_storage_path) / f"run_{run_id}"
    run_dir.mkdir(parents=True)
    metrics_path = run_dir / "metrics.jsonl"
    with open(metrics_path, "w") as f:
        for i in range(105):
            f.write(json.dumps({"step": i}) + "\n")

    resp = client.get(f"/metrics/{run_id}")
    assert resp.status_code == 200
    metrics = resp.json()["metrics"]
    assert len(metrics) == 100
    assert metrics[-1]["step"] == 104


def test_admin_actions(client, sb_client):
    job = sb_client.add_job({"a": 1}, "sweep1", status="failed")
    job_id = job["id"]

    headers = {"X-API-Key": "secret"}
    r = client.post("/job/kill", json={"job_id": job_id}, headers=headers)
    assert r.status_code == 200
    job_data = sb_client.get_job_details(job_id)
    assert job_data.get("kill_requested") is True

    r = client.post("/job/requeue", json={"job_id": job_id}, headers=headers)
    assert r.status_code == 200
    job_data = sb_client.get_job_details(job_id)
    assert job_data["status"] == "queued"
    assert job_data["retry_index"] == 1

    bad = client.post(
        "/job/kill", json={"job_id": job_id}, headers={"X-API-Key": "bad"}
    )
    assert bad.status_code == 401


def test_list_jobs_endpoint(client, sb_client):
    job1 = sb_client.add_job({"a": 1}, "sweep1", status="queued")
    job2 = sb_client.add_job({"b": 2}, "sweep2", status="running")

    resp = client.get("/jobs")
    assert resp.status_code == 200
    data = resp.json()
    ids = {j["id"] for j in data}
    assert job1["id"] in ids
    assert job2["id"] in ids
