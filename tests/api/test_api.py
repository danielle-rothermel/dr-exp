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
    run_dir = Path(sb_client.storage_dir) / f"run_{run_id}"
    run_dir.mkdir(parents=True)
    metrics_path = run_dir / "metrics.jsonl"
    with open(metrics_path, "w") as f:
        for i in range(105):
            f.write(json.dumps({"step": i}) + "\n")

    # Test default limit (500) - should return all 105 metrics
    resp = client.get(f"/metrics/{run_id}")
    assert resp.status_code == 200
    metrics = resp.json()["metrics"]
    assert len(metrics) == 105
    assert metrics[-1]["step"] == 104

    # Test custom limit
    resp = client.get(f"/metrics/{run_id}?limit=10")
    assert resp.status_code == 200
    metrics = resp.json()["metrics"]
    assert len(metrics) == 10
    assert metrics[-1]["step"] == 104  # Should be last 10 metrics


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


def test_priority_endpoints(client, sb_client):
    job = sb_client.add_job({"a": 1}, "sweep1", status="queued", priority=100)
    job_id = job["id"]

    headers = {"X-API-Key": "secret"}
    
    # Test boost priority
    boost_resp = client.post(
        "/job/boost-priority", 
        json={"job_id": job_id, "boost_amount": 50}, 
        headers=headers
    )
    assert boost_resp.status_code == 200
    boost_data = boost_resp.json()
    assert boost_data["job_id"] == job_id
    assert boost_data["old_priority"] == 100
    assert boost_data["new_priority"] == 150
    assert boost_data["success"] is True

    # Test set priority
    set_resp = client.post(
        "/job/set-priority",
        json={"job_id": job_id, "priority": 300, "reason": "urgent experiment"},
        headers=headers
    )
    assert set_resp.status_code == 200
    set_data = set_resp.json()
    assert set_data["job_id"] == job_id
    assert set_data["old_priority"] == 150  # From previous boost
    assert set_data["new_priority"] == 300
    assert set_data["success"] is True

    # Test unauthorized access
    bad_resp = client.post(
        "/job/boost-priority", 
        json={"job_id": job_id, "boost_amount": 50},
        headers={"X-API-Key": "bad"}
    )
    assert bad_resp.status_code == 401
