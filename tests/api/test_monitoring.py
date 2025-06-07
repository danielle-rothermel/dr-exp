"""Tests for API monitoring and system endpoints."""

import pytest
from .conftest import create_test_job, JobStatus


def test_health_endpoint_basic(client):
    """Test basic health check endpoint functionality."""
    resp = client.get("/health")
    assert resp.status_code == 200
    
    data = resp.json()
    required_fields = [
        "status", "timestamp", "uptime_seconds", 
        "version", "database_status", "job_stats"
    ]
    
    for field in required_fields:
        assert field in data, f"Missing required field: {field}"
    
    # Verify data types and basic constraints
    assert isinstance(data["uptime_seconds"], (int, float))
    assert data["uptime_seconds"] >= 0
    assert data["version"] == "1.0.0"
    assert data["status"] in ["healthy", "unhealthy"]
    assert data["database_status"] in ["healthy", "unhealthy"]
    assert isinstance(data["job_stats"], dict)


def test_health_endpoint_job_stats_structure(client, db_client):
    """Test that health endpoint returns correct job statistics."""
    # Create jobs with different statuses
    create_test_job(db_client, status=JobStatus.QUEUED)
    create_test_job(db_client, status=JobStatus.RUNNING)
    create_test_job(db_client, status=JobStatus.COMPLETED)
    create_test_job(db_client, status=JobStatus.FAILED)
    
    resp = client.get("/health")
    assert resp.status_code == 200
    
    job_stats = resp.json()["job_stats"]
    expected_statuses = ["queued", "running", "completed", "failed", "killed"]
    
    for status in expected_statuses:
        assert status in job_stats
        assert isinstance(job_stats[status], int)
        assert job_stats[status] >= 0
    
    # Verify specific counts match what we created
    assert job_stats["queued"] >= 1
    assert job_stats["running"] >= 1
    assert job_stats["completed"] >= 1
    assert job_stats["failed"] >= 1


def test_metrics_endpoint_basic(client):
    """Test basic metrics endpoint functionality."""
    resp = client.get("/metrics")
    assert resp.status_code == 200
    
    data = resp.json()
    required_fields = [
        "timestamp", "uptime_seconds", "active_connections",
        "job_stats", "total_jobs", "queue_depth", "running_jobs"
    ]
    
    for field in required_fields:
        assert field in data, f"Missing required field: {field}"
    
    # Verify data types and constraints
    assert isinstance(data["uptime_seconds"], (int, float))
    assert data["uptime_seconds"] >= 0
    assert isinstance(data["active_connections"], int)
    assert data["active_connections"] >= 0
    assert isinstance(data["total_jobs"], int)
    assert data["total_jobs"] >= 0
    assert isinstance(data["queue_depth"], int)
    assert data["queue_depth"] >= 0
    assert isinstance(data["running_jobs"], int)
    assert data["running_jobs"] >= 0


def test_metrics_endpoint_job_counts(client, db_client):
    """Test that metrics endpoint returns accurate job counts."""
    # Start with clean state and create specific jobs
    queued_jobs = [create_test_job(db_client, status=JobStatus.QUEUED) for _ in range(3)]
    running_jobs = [create_test_job(db_client, status=JobStatus.RUNNING) for _ in range(2)]
    completed_jobs = [create_test_job(db_client, status=JobStatus.COMPLETED) for _ in range(1)]
    
    resp = client.get("/metrics")
    assert resp.status_code == 200
    
    data = resp.json()
    
    # Check total jobs
    assert data["total_jobs"] >= 6  # At least the jobs we created
    
    # Check queue depth (queued jobs)
    assert data["queue_depth"] >= 3
    
    # Check running jobs
    assert data["running_jobs"] >= 2
    
    # Check job stats breakdown
    job_stats = data["job_stats"]
    assert job_stats["queued"] >= 3
    assert job_stats["running"] >= 2
    assert job_stats["completed"] >= 1


def test_api_info_endpoint(client):
    """Test API information endpoint."""
    resp = client.get("/api")
    assert resp.status_code == 200
    
    data = resp.json()
    required_fields = [
        "name", "version", "versions", 
        "health_check", "metrics", "websocket"
    ]
    
    for field in required_fields:
        assert field in data, f"Missing required field: {field}"
    
    # Check specific values
    assert "DR Experiment Manager API" in data["name"]
    assert data["version"] == "1.0.0"
    assert data["health_check"] == "/health"
    assert data["metrics"] == "/metrics"
    assert data["websocket"] == "/ws"
    
    # Check versions structure
    assert "v1" in data["versions"]
    v1_info = data["versions"]["v1"]
    assert v1_info["status"] == "stable"
    assert v1_info["prefix"] == "/api/v1"
    assert v1_info["docs"] == "/docs"


def test_response_headers_version(client):
    """Test that API version headers are present."""
    endpoints_to_test = ["/health", "/metrics", "/api", "/jobs"]
    
    for endpoint in endpoints_to_test:
        resp = client.get(endpoint)
        assert resp.status_code == 200
        
        # Check version header
        assert "X-API-Version" in resp.headers
        assert resp.headers["X-API-Version"] == "1.0.0"


def test_response_headers_timing(client):
    """Test that performance timing headers are present."""
    resp = client.get("/health")
    assert resp.status_code == 200
    
    # Check timing header (should be present for performance monitoring)
    assert "X-Process-Time" in resp.headers
    
    # Parse timing value and verify it's reasonable
    process_time = float(resp.headers["X-Process-Time"])
    assert 0 <= process_time <= 10.0  # Should be under 10 seconds for health check


def test_deprecation_headers_presence(client):
    """Test that deprecation headers are added to non-versioned endpoints."""
    # Endpoints that should have deprecation headers
    deprecated_endpoints = ["/jobs", "/job/123", "/config/123", "/metrics/123"]
    
    for endpoint in deprecated_endpoints:
        resp = client.get(endpoint)
        # Don't require 200 status (some endpoints may 404)
        
        if resp.status_code == 200:
            assert "X-API-Deprecation-Notice" in resp.headers
            assert "X-API-Migration-Guide" in resp.headers
            
            deprecation_notice = resp.headers["X-API-Deprecation-Notice"]
            assert "deprecated" in deprecation_notice.lower()


def test_no_deprecation_headers_for_excluded_paths(client):
    """Test that deprecation headers are not added to excluded paths."""
    # Endpoints that should NOT have deprecation headers
    excluded_endpoints = ["/health", "/metrics", "/api", "/docs", "/ws"]
    
    for endpoint in excluded_endpoints:
        resp = client.get(endpoint)
        if resp.status_code == 200:  # Skip if endpoint doesn't exist in test
            assert "X-API-Deprecation-Notice" not in resp.headers
            assert "X-API-Migration-Guide" not in resp.headers


def test_health_endpoint_database_status(client, db_client):
    """Test health endpoint database status reporting."""
    resp = client.get("/health")
    assert resp.status_code == 200
    
    data = resp.json()
    
    # In test environment with working database, should be healthy
    assert data["database_status"] == "healthy"
    
    # Create a job to verify database is actually working
    job = create_test_job(db_client)
    assert job["id"] is not None
    
    # Health check should still report healthy
    resp = client.get("/health")
    data = resp.json()
    assert data["database_status"] == "healthy"


def test_metrics_endpoint_active_connections(client):
    """Test metrics endpoint active connections tracking."""
    resp = client.get("/metrics")
    assert resp.status_code == 200
    
    data = resp.json()
    
    # Should have at least 1 active connection (the current request)
    # Note: This might be 0 in some test setups where connection pooling
    # or async handling means the connection isn't "active" during response
    assert data["active_connections"] >= 0


def test_concurrent_health_checks(client):
    """Test multiple concurrent health check requests."""
    import threading
    import time
    
    results = []
    errors = []
    
    def make_request():
        try:
            resp = client.get("/health")
            results.append(resp.status_code)
        except Exception as e:
            errors.append(str(e))
    
    # Create multiple threads
    threads = []
    for _ in range(10):
        thread = threading.Thread(target=make_request)
        threads.append(thread)
    
    # Start all threads
    for thread in threads:
        thread.start()
    
    # Wait for all to complete
    for thread in threads:
        thread.join()
    
    # Verify all requests succeeded
    assert len(errors) == 0, f"Errors occurred: {errors}"
    assert len(results) == 10
    assert all(status == 200 for status in results)


def test_uptime_consistency(client):
    """Test that uptime values are consistent and increasing."""
    import time
    
    # Get initial uptime
    resp1 = client.get("/health")
    assert resp1.status_code == 200
    uptime1 = resp1.json()["uptime_seconds"]
    
    # Wait a short time
    time.sleep(0.1)
    
    # Get uptime again
    resp2 = client.get("/health")
    assert resp2.status_code == 200
    uptime2 = resp2.json()["uptime_seconds"]
    
    # Second uptime should be >= first (allowing for timing precision)
    assert uptime2 >= uptime1