"""Tests for job management endpoints."""

import pytest
from .conftest import create_test_job, create_test_metrics, Priority, JobStatus


def test_get_job_details(client, db_client):
    """Test retrieving job details."""
    config = {"model": {"name": "resnet"}, "epochs": 100}
    job = create_test_job(db_client, job_config=config, status=JobStatus.QUEUED)
    job_id = job["id"]

    resp = client.get(f"/job/{job_id}")
    assert resp.status_code == 200
    
    data = resp.json()
    assert data["id"] == job_id
    assert data["status"] == JobStatus.QUEUED
    assert data["priority"] == 100


def test_get_job_config(client, db_client):
    """Test retrieving job configuration."""
    config = {"model": {"name": "resnet"}, "lr": 0.001}
    job = create_test_job(db_client, job_config=config)
    job_id = job["id"]

    resp = client.get(f"/config/{job_id}")
    assert resp.status_code == 200
    assert resp.json()["config"] == config


def test_get_nonexistent_job(client):
    """Test retrieving non-existent job returns 404."""
    resp = client.get("/job/nonexistent-id")
    assert resp.status_code == 404


def test_get_nonexistent_config(client):
    """Test retrieving config for non-existent job returns 404.""" 
    resp = client.get("/config/nonexistent-id")
    assert resp.status_code == 404


def test_list_jobs_basic(client, db_client):
    """Test basic job listing."""
    job1 = create_test_job(db_client, sweep_config_id="sweep1", status=JobStatus.QUEUED)
    job2 = create_test_job(db_client, sweep_config_id="sweep2", status=JobStatus.RUNNING)

    resp = client.get("/jobs")
    assert resp.status_code == 200
    
    data = resp.json()
    assert isinstance(data, list)
    job_ids = {job["id"] for job in data}
    assert job1["id"] in job_ids
    assert job2["id"] in job_ids


def test_list_jobs_empty(client):
    """Test listing jobs when no jobs exist."""
    resp = client.get("/jobs")
    assert resp.status_code == 200
    assert resp.json() == []


def test_job_status_filtering(client, db_client):
    """Test filtering jobs by status."""
    queued_job = create_test_job(db_client, status=JobStatus.QUEUED)
    running_job = create_test_job(db_client, status=JobStatus.RUNNING)
    completed_job = create_test_job(db_client, status=JobStatus.COMPLETED)

    # Test filtering by queued status
    resp = client.get("/jobs?job_status=queued")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["id"] == queued_job["id"]
    assert data[0]["status"] == JobStatus.QUEUED

    # Test filtering by running status
    resp = client.get("/jobs?job_status=running")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["id"] == running_job["id"]
    assert data[0]["status"] == JobStatus.RUNNING


def test_priority_filtering(client, db_client):
    """Test filtering jobs by priority range."""
    low_job = create_test_job(db_client, priority=Priority.LOW)
    normal_job = create_test_job(db_client, priority=Priority.NORMAL)
    high_job = create_test_job(db_client, priority=Priority.HIGH)

    # Test minimum priority filter
    resp = client.get(f"/jobs?priority_min={Priority.NORMAL}")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    priorities = [job["priority"] for job in data]
    assert all(p >= Priority.NORMAL for p in priorities)
    assert {Priority.NORMAL, Priority.HIGH} == set(priorities)

    # Test maximum priority filter
    resp = client.get(f"/jobs?priority_max={Priority.NORMAL}")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    priorities = [job["priority"] for job in data]
    assert all(p <= Priority.NORMAL for p in priorities)
    assert {Priority.LOW, Priority.NORMAL} == set(priorities)

    # Test priority range filter
    resp = client.get(f"/jobs?priority_min={Priority.LOW}&priority_max={Priority.NORMAL}")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    priorities = [job["priority"] for job in data]
    assert all(Priority.LOW <= p <= Priority.NORMAL for p in priorities)


def test_job_sorting(client, db_client):
    """Test sorting jobs by different fields."""
    # Create jobs with different priorities and times
    job1 = create_test_job(db_client, priority=Priority.HIGH, sweep_config_id="job1") 
    job2 = create_test_job(db_client, priority=Priority.LOW, sweep_config_id="job2")
    job3 = create_test_job(db_client, priority=Priority.NORMAL, sweep_config_id="job3")

    # Test sorting by priority (ascending)
    resp = client.get("/jobs?sort_by=priority&sort_order=asc")
    assert resp.status_code == 200
    data = resp.json()
    priorities = [job["priority"] for job in data]
    assert priorities == sorted(priorities)
    assert priorities == [Priority.LOW, Priority.NORMAL, Priority.HIGH]

    # Test sorting by priority (descending)
    resp = client.get("/jobs?sort_by=priority&sort_order=desc")
    assert resp.status_code == 200
    data = resp.json()
    priorities = [job["priority"] for job in data]
    assert priorities == sorted(priorities, reverse=True)
    assert priorities == [Priority.HIGH, Priority.NORMAL, Priority.LOW]


def test_invalid_filters(client):
    """Test validation of invalid filter parameters."""
    # Invalid status (only validated when paginated=true)
    resp = client.get("/jobs?paginated=true&job_status=invalid_status")
    assert resp.status_code == 400

    # Invalid priority range
    resp = client.get("/jobs?paginated=true&priority_min=1001")
    assert resp.status_code == 400

    resp = client.get("/jobs?paginated=true&priority_min=500&priority_max=200")
    assert resp.status_code == 400

    # Invalid sort field
    resp = client.get("/jobs?paginated=true&sort_by=invalid_field")
    assert resp.status_code == 400

    # Invalid sort order
    resp = client.get("/jobs?paginated=true&sort_order=invalid_order")
    assert resp.status_code == 400


def test_metrics_endpoint(client, db_client):
    """Test retrieving job metrics."""
    job = create_test_job(db_client, status=JobStatus.RUNNING)
    job_id = job["id"]
    
    # Create test metrics
    create_test_metrics(db_client, job_id, num_metrics=105)

    # Test default limit (should return all 105 metrics)
    resp = client.get(f"/metrics/{job_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["metrics"]) == 105
    assert data["count"] == 105

    # Test custom limit
    resp = client.get(f"/metrics/{job_id}?limit=10")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["metrics"]) == 10
    assert data["count"] == 10
    
    # Verify metrics are ordered (latest last)
    metrics = data["metrics"]
    steps = [m["step"] for m in metrics]
    assert steps[-1] == 104  # Should be last 10 metrics


def test_metrics_nonexistent_job(client):
    """Test retrieving metrics for non-existent job."""
    resp = client.get("/metrics/nonexistent-id")
    assert resp.status_code == 404


def test_metrics_no_metrics_file(client, db_client):
    """Test retrieving metrics when no metrics file exists."""
    job = create_test_job(db_client)
    job_id = job["id"]
    
    resp = client.get(f"/metrics/{job_id}")
    assert resp.status_code == 404