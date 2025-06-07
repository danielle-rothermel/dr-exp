"""Tests for API authentication and authorization."""

import pytest
from .conftest import create_test_job, Priority, JobStatus


def test_public_endpoints_no_auth(client, db_client):
    """Test that public endpoints work without authentication."""
    job = create_test_job(db_client)
    job_id = job["id"]

    # These endpoints should work without auth
    public_endpoints = [
        "/health",
        "/metrics", 
        "/api",
        "/jobs",
        f"/job/{job_id}",
        f"/config/{job_id}",
    ]
    
    for endpoint in public_endpoints:
        resp = client.get(endpoint)
        assert resp.status_code in [200, 404], f"Endpoint {endpoint} failed with {resp.status_code}"


def test_admin_endpoints_require_auth(client, db_client):
    """Test that admin endpoints require authentication."""
    job = create_test_job(db_client, status=JobStatus.FAILED)
    job_id = job["id"]

    admin_endpoints = [
        ("/job/kill", {"job_id": job_id}),
        ("/job/requeue", {"job_id": job_id}),
        ("/job/boost-priority", {"job_id": job_id, "boost_amount": 100}),
        ("/job/set-priority", {"job_id": job_id, "priority": 500}),
    ]
    
    for endpoint, payload in admin_endpoints:
        # Test without auth (may return 401 or 403)
        resp = client.post(endpoint, json=payload)
        assert resp.status_code in [401, 403], f"Endpoint {endpoint} should require auth"
        
        # Test with invalid auth
        resp = client.post(
            endpoint, 
            json=payload,
            headers={"Authorization": "Bearer invalid"}
        )
        assert resp.status_code in [401, 403], f"Endpoint {endpoint} should reject invalid token"


def test_admin_access_with_valid_token(client, db_client, admin_headers):
    """Test admin operations work with valid admin token."""
    job = create_test_job(db_client, status=JobStatus.FAILED, priority=Priority.NORMAL)
    job_id = job["id"]

    # Test kill job
    resp = client.post(
        "/job/kill", 
        json={"job_id": job_id}, 
        headers=admin_headers
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["job_id"] == job_id

    # Test requeue job
    resp = client.post(
        "/job/requeue",
        json={"job_id": job_id},
        headers=admin_headers
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["job_id"] == job_id

    # Test boost priority
    resp = client.post(
        "/job/boost-priority",
        json={"job_id": job_id, "boost_amount": 100},
        headers=admin_headers
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["old_priority"] == Priority.NORMAL
    assert data["new_priority"] == Priority.NORMAL + 100

    # Test set priority
    resp = client.post(
        "/job/set-priority",
        json={"job_id": job_id, "priority": Priority.URGENT, "reason": "urgent deadline"},
        headers=admin_headers
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["new_priority"] == Priority.URGENT


def test_reader_access_restrictions(client, db_client, reader_headers):
    """Test that reader token cannot access admin endpoints."""
    job = create_test_job(db_client, status=JobStatus.FAILED)
    job_id = job["id"]

    admin_endpoints = [
        ("/job/kill", {"job_id": job_id}),
        ("/job/requeue", {"job_id": job_id}),
        ("/job/boost-priority", {"job_id": job_id, "boost_amount": 100}),
        ("/job/set-priority", {"job_id": job_id, "priority": 500}),
    ]
    
    for endpoint, payload in admin_endpoints:
        resp = client.post(endpoint, json=payload, headers=reader_headers)
        assert resp.status_code == 403, f"Reader should not access {endpoint}"


def test_reader_can_access_read_endpoints(client, db_client, reader_headers):
    """Test that reader token can access read-only endpoints."""
    job = create_test_job(db_client)
    job_id = job["id"]

    read_endpoints = [
        "/health",
        "/metrics",
        "/api", 
        "/jobs",
        f"/job/{job_id}",
        f"/config/{job_id}",
    ]
    
    for endpoint in read_endpoints:
        resp = client.get(endpoint, headers=reader_headers)
        assert resp.status_code in [200, 404], f"Reader should access {endpoint}"


def test_malformed_auth_headers(client, db_client):
    """Test handling of malformed authorization headers."""
    job = create_test_job(db_client)
    job_id = job["id"]

    malformed_headers = [
        {"Authorization": "invalid"},  # Missing Bearer
        {"Authorization": "Bearer"},   # Missing token
        {"Authorization": "Basic token"},  # Wrong scheme
        {"Authorization": "Bearer "},  # Empty token
    ]
    
    for headers in malformed_headers:
        resp = client.post(
            "/job/kill", 
            json={"job_id": job_id},
            headers=headers
        )
        assert resp.status_code in [401, 403]


def test_case_sensitive_tokens(client, db_client):
    """Test that tokens are case-sensitive."""
    job = create_test_job(db_client)
    job_id = job["id"]

    # Test with wrong case
    wrong_case_headers = {"Authorization": "Bearer SECRET"}  # Should be "secret"
    
    resp = client.post(
        "/job/kill",
        json={"job_id": job_id},
        headers=wrong_case_headers
    )
    assert resp.status_code == 401


def test_empty_authorization_header(client, db_client):
    """Test behavior with empty authorization header."""
    job = create_test_job(db_client)
    job_id = job["id"]

    resp = client.post(
        "/job/kill",
        json={"job_id": job_id},
        headers={"Authorization": ""}
    )
    assert resp.status_code in [401, 403]


def test_multiple_authorization_headers(client, db_client):
    """Test behavior with multiple authorization headers."""
    job = create_test_job(db_client)
    job_id = job["id"]

    # FastAPI/Starlette should handle this gracefully
    resp = client.post(
        "/job/kill",
        json={"job_id": job_id},
        headers=[
            ("Authorization", "Bearer secret"),
            ("Authorization", "Bearer invalid")
        ]
    )
    # Behavior may vary, but should either work with first header or reject
    assert resp.status_code in [200, 401]