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
    data = resp.json()
    metrics = data["metrics"]
    assert len(metrics) == 105
    assert data["count"] == 105
    assert metrics[-1]["step"] == 104

    # Test custom limit
    resp = client.get(f"/metrics/{run_id}?limit=10")
    assert resp.status_code == 200
    data = resp.json()
    metrics = data["metrics"]
    assert len(metrics) == 10
    assert data["count"] == 10
    assert metrics[-1]["step"] == 104  # Should be last 10 metrics


def test_admin_actions(client, sb_client):
    job = sb_client.add_job({"a": 1}, "sweep1", status="failed")
    job_id = job["id"]

    headers = {"Authorization": "Bearer secret"}
    
    # Test kill endpoint
    r = client.post("/job/kill", json={"job_id": job_id}, headers=headers)
    assert r.status_code == 200
    kill_resp = r.json()
    assert kill_resp["success"] is True
    assert kill_resp["job_id"] == job_id
    assert "marked for termination" in kill_resp["message"]
    
    job_data = sb_client.get_job_details(job_id)
    assert job_data.get("kill_requested") is True

    # Test requeue endpoint
    r = client.post("/job/requeue", json={"job_id": job_id}, headers=headers)
    assert r.status_code == 200
    requeue_resp = r.json()
    assert requeue_resp["success"] is True
    assert requeue_resp["job_id"] == job_id
    assert "requeued for retry" in requeue_resp["message"]
    
    job_data = sb_client.get_job_details(job_id)
    assert job_data["status"] == "queued"
    assert job_data["retry_index"] == 1

    # Test unauthorized access
    bad = client.post(
        "/job/kill", json={"job_id": job_id}, headers={"Authorization": "Bearer bad"}
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

    headers = {"Authorization": "Bearer secret"}
    
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
        headers={"Authorization": "Bearer bad"}
    )
    assert bad_resp.status_code == 401


def test_websocket_connection(client):
    """Test WebSocket connection can be established."""
    with client.websocket_connect("/ws") as websocket:
        # Send a test message
        websocket.send_text("test message")
        # Receive the echo
        data = websocket.receive_text()
        assert "Echo: test message" in data


def test_pagination(tmp_path, monkeypatch):
    """Test job listing pagination with isolated database."""
    # Create isolated app for this test
    monkeypatch.setenv("ADMIN_API_KEY", "secret")
    monkeypatch.setenv("EXPMGR_MODE", "files_local")
    monkeypatch.setenv("DR_EXP_BASE_PATH", str(tmp_path))
    
    from dr_exp.api.main import create_app
    from fastapi.testclient import TestClient
    
    app = create_app(base_path=str(tmp_path))
    client = TestClient(app)
    sb_client = app.state.client
    
    # Verify we start with no jobs
    existing_jobs = client.get("/jobs").json()
    assert len(existing_jobs) == 0, f"Expected 0 jobs but found {len(existing_jobs)}"
    
    # Create multiple jobs for pagination testing
    jobs = []
    for i in range(25):
        job = sb_client.add_job({"index": i}, f"sweep{i}", status="queued")
        jobs.append(job)
    
    # Test non-paginated response (default)
    resp = client.get("/jobs")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) == 25
    
    # Test paginated response
    resp = client.get("/jobs?paginated=true&page=1&per_page=10")
    assert resp.status_code == 200
    data = resp.json()
    
    # Check pagination metadata
    assert data["total"] == 25
    assert data["page"] == 1
    assert data["per_page"] == 10
    assert data["pages"] == 3
    assert data["has_next"] is True
    assert data["has_prev"] is False
    assert len(data["jobs"]) == 10
    
    # Test second page
    resp = client.get("/jobs?paginated=true&page=2&per_page=10")
    assert resp.status_code == 200
    data = resp.json()
    assert data["page"] == 2
    assert data["has_next"] is True
    assert data["has_prev"] is True
    assert len(data["jobs"]) == 10
    
    # Test last page
    resp = client.get("/jobs?paginated=true&page=3&per_page=10")
    assert resp.status_code == 200
    data = resp.json()
    assert data["page"] == 3
    assert data["has_next"] is False
    assert data["has_prev"] is True
    assert len(data["jobs"]) == 5  # Remaining jobs
    
    # Test invalid page number
    resp = client.get("/jobs?paginated=true&page=0")
    assert resp.status_code == 400
    
    # Test invalid per_page
    resp = client.get("/jobs?paginated=true&per_page=101")
    assert resp.status_code == 400


def test_filtering_and_sorting(tmp_path, monkeypatch):
    """Test job filtering and sorting functionality."""
    # Create isolated app for this test
    monkeypatch.setenv("ADMIN_API_KEY", "secret")
    monkeypatch.setenv("EXPMGR_MODE", "files_local")
    monkeypatch.setenv("DR_EXP_BASE_PATH", str(tmp_path))
    
    from dr_exp.api.main import create_app
    from fastapi.testclient import TestClient
    
    app = create_app(base_path=str(tmp_path))
    client = TestClient(app)
    sb_client = app.state.client
    
    # Create jobs with different statuses and priorities
    job1 = sb_client.add_job({"name": "job1"}, "sweep1", status="queued", priority=100)
    job2 = sb_client.add_job({"name": "job2"}, "sweep2", status="running", priority=200)
    job3 = sb_client.add_job({"name": "job3"}, "sweep3", status="completed", priority=300)
    job4 = sb_client.add_job({"name": "job4"}, "sweep4", status="failed", priority=150)
    
    # Test status filtering
    resp = client.get("/jobs?job_status=queued")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["id"] == job1["id"]
    
    resp = client.get("/jobs?job_status=running")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["id"] == job2["id"]
    
    # Test priority filtering
    resp = client.get("/jobs?priority_min=200")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2  # job2 (200) and job3 (300)
    priorities = [job["priority"] for job in data]
    assert all(p >= 200 for p in priorities)
    
    resp = client.get("/jobs?priority_max=150")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2  # job1 (100) and job4 (150)
    priorities = [job["priority"] for job in data]
    assert all(p <= 150 for p in priorities)
    
    resp = client.get("/jobs?priority_min=150&priority_max=250")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2  # job2 (200) and job4 (150)
    priorities = [job["priority"] for job in data]
    assert all(150 <= p <= 250 for p in priorities)
    
    # Test sorting by priority (ascending)
    resp = client.get("/jobs?sort_by=priority&sort_order=asc")
    assert resp.status_code == 200
    data = resp.json()
    priorities = [job["priority"] for job in data]
    assert priorities == sorted(priorities)  # Should be [100, 150, 200, 300]
    
    # Test sorting by priority (descending)
    resp = client.get("/jobs?sort_by=priority&sort_order=desc")
    assert resp.status_code == 200
    data = resp.json()
    priorities = [job["priority"] for job in data]
    assert priorities == sorted(priorities, reverse=True)  # Should be [300, 200, 150, 100]
    
    # Test sorting by status
    resp = client.get("/jobs?sort_by=status&sort_order=asc")
    assert resp.status_code == 200
    data = resp.json()
    statuses = [job["status"] for job in data]
    assert statuses == sorted(statuses)
    
    # Test combined filtering and sorting with pagination
    resp = client.get("/jobs?paginated=true&job_status=queued&sort_by=priority&sort_order=desc&page=1&per_page=10")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert len(data["jobs"]) == 1
    assert data["jobs"][0]["status"] == "queued"
    
    # Test invalid status
    resp = client.get("/jobs?paginated=true&job_status=invalid")
    assert resp.status_code == 400
    
    # Test invalid priority range
    resp = client.get("/jobs?paginated=true&priority_min=1001")
    assert resp.status_code == 400
    
    resp = client.get("/jobs?paginated=true&priority_min=200&priority_max=100")
    assert resp.status_code == 400
    
    # Test invalid sort field
    resp = client.get("/jobs?paginated=true&sort_by=invalid")
    assert resp.status_code == 400
    
    # Test invalid sort order
    resp = client.get("/jobs?paginated=true&sort_order=invalid")
    assert resp.status_code == 400
