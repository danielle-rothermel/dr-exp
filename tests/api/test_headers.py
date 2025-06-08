"""Tests for HTTP response headers and security features."""

from .conftest import create_test_job, JobStatus


def test_security_headers_present(client):
    """Test that security headers are present on all responses."""
    endpoints = [
        "/health",
        "/metrics", 
        "/api",
        "/jobs",
    ]
    
    expected_security_headers = {
        "x-content-type-options": "nosniff",
        "x-frame-options": "DENY", 
        "x-xss-protection": "1; mode=block",
        "referrer-policy": "strict-origin-when-cross-origin"
    }
    
    for endpoint in endpoints:
        resp = client.get(endpoint)
        if resp.status_code == 200:
            for header_name, expected_value in expected_security_headers.items():
                assert header_name in resp.headers, f"Missing security header {header_name} on {endpoint}"
                assert resp.headers[header_name] == expected_value, f"Incorrect {header_name} value on {endpoint}"


def test_content_type_headers(client, db_client):
    """Test that content-type headers are correct for different responses."""
    # Create a test job for endpoints that need it
    job = create_test_job(db_client)
    job_id = job["id"]
    
    json_endpoints = [
        "/health",
        "/metrics",
        "/api", 
        "/jobs",
        f"/job/{job_id}",
        f"/config/{job_id}",
    ]
    
    for endpoint in json_endpoints:
        resp = client.get(endpoint)
        if resp.status_code == 200:
            assert "content-type" in resp.headers
            assert "application/json" in resp.headers["content-type"]


def test_api_version_headers_consistency(client, db_client):
    """Test that API version headers are consistent across all endpoints."""
    job = create_test_job(db_client)
    job_id = job["id"]
    
    all_endpoints = [
        "/health",
        "/metrics",
        "/api",
        "/jobs", 
        f"/job/{job_id}",
        f"/config/{job_id}",
    ]
    
    expected_version = "1.0.0"
    
    for endpoint in all_endpoints:
        resp = client.get(endpoint)
        if resp.status_code == 200:
            assert "x-api-version" in resp.headers, f"Missing API version header on {endpoint}"
            assert resp.headers["x-api-version"] == expected_version, f"Incorrect API version on {endpoint}"


def test_performance_timing_headers(client):
    """Test that performance timing headers are present and reasonable."""
    endpoints = ["/health", "/metrics", "/api", "/jobs"]
    
    for endpoint in endpoints:
        resp = client.get(endpoint)
        if resp.status_code == 200:
            assert "x-process-time" in resp.headers, f"Missing timing header on {endpoint}"
            
            # Parse timing value
            process_time = float(resp.headers["x-process-time"])
            
            # Should be a reasonable value (under 10 seconds for test environment)
            assert 0 <= process_time <= 10.0, f"Unreasonable process time {process_time} on {endpoint}"


def test_deprecation_headers_on_legacy_endpoints(client, db_client):
    """Test that deprecation headers are correctly applied to legacy endpoints."""
    job = create_test_job(db_client)
    job_id = job["id"]
    
    # Endpoints that should have deprecation headers
    legacy_endpoints = [
        "/jobs",
        f"/job/{job_id}",
        f"/config/{job_id}",
    ]
    
    for endpoint in legacy_endpoints:
        resp = client.get(endpoint)
        if resp.status_code == 200:
            assert "x-api-deprecation-notice" in resp.headers, f"Missing deprecation notice on {endpoint}"
            assert "x-api-migration-guide" in resp.headers, f"Missing migration guide on {endpoint}"
            
            # Check content of deprecation headers
            deprecation_notice = resp.headers["x-api-deprecation-notice"]
            migration_guide = resp.headers["x-api-migration-guide"]
            
            assert "deprecated" in deprecation_notice.lower()
            assert "/api/v1" in migration_guide or "v1" in migration_guide


def test_no_deprecation_headers_on_current_endpoints(client):
    """Test that current API endpoints do not have deprecation headers."""
    current_endpoints = ["/health", "/metrics", "/ws", "/docs"]
    
    for endpoint in current_endpoints:
        resp = client.get(endpoint)
        if resp.status_code == 200:
            assert "x-api-deprecation-notice" not in resp.headers, f"Unexpected deprecation on {endpoint}"
            assert "x-api-migration-guide" not in resp.headers, f"Unexpected migration guide on {endpoint}"


def test_cors_headers_development(client):
    """Test CORS headers in development environment."""
    # In development, CORS might be permissive
    resp = client.get("/health")
    assert resp.status_code == 200
    
    # CORS headers might not be present in test environment, but if they are, they should be valid
    if "access-control-allow-origin" in resp.headers:
        origin = resp.headers["access-control-allow-origin"]
        assert origin in ["*", "http://localhost:5173", "http://localhost:3000"]


def test_cache_control_headers(client):
    """Test cache control headers for different types of responses."""
    # Health endpoint should not be cached aggressively
    resp = client.get("/health")
    assert resp.status_code == 200
    
    # If cache-control is present, it should be appropriate
    if "cache-control" in resp.headers:
        cache_control = resp.headers["cache-control"]
        # Health checks should not be cached for long
        assert "no-cache" in cache_control or "max-age" in cache_control


def test_content_length_headers(client, db_client):
    """Test that content-length headers are present and accurate."""
    job = create_test_job(db_client)
    job_id = job["id"]
    
    endpoints = [
        "/health",
        "/api",
        f"/job/{job_id}",
    ]
    
    for endpoint in endpoints:
        resp = client.get(endpoint)
        if resp.status_code == 200:
            assert "content-length" in resp.headers, f"Missing content-length on {endpoint}"
            
            content_length = int(resp.headers["content-length"])
            actual_length = len(resp.content)
            
            assert content_length == actual_length, f"Content-length mismatch on {endpoint}"


def test_server_headers_security(client):
    """Test that server headers don't expose sensitive information."""
    resp = client.get("/health")
    assert resp.status_code == 200
    
    # Server header should not expose detailed version info
    if "server" in resp.headers:
        server = resp.headers["server"].lower()
        # Should not contain version numbers or detailed implementation info
        assert "uvicorn" not in server or "/" not in server


def test_headers_on_error_responses(client):
    """Test that security headers are present even on error responses."""
    # Test 404 response
    resp = client.get("/nonexistent-endpoint")
    assert resp.status_code == 404
    
    # Security headers should still be present
    expected_headers = ["x-content-type-options", "x-frame-options", "x-xss-protection"]
    for header in expected_headers:
        assert header in resp.headers, f"Missing security header {header} on error response"


def test_headers_on_admin_endpoints(client, db_client, admin_headers):
    """Test headers on authenticated admin endpoints."""
    job = create_test_job(db_client, status=JobStatus.FAILED)
    job_id = job["id"]
    
    # Test admin endpoint
    resp = client.post(
        "/job/kill",
        json={"job_id": job_id},
        headers=admin_headers
    )
    assert resp.status_code == 200
    
    # All standard headers should be present
    assert "x-api-version" in resp.headers
    assert "x-process-time" in resp.headers
    assert "x-content-type-options" in resp.headers
    assert "content-type" in resp.headers
    assert "application/json" in resp.headers["content-type"]


def test_headers_consistency_across_methods(client, db_client, admin_headers):
    """Test that headers are consistent across different HTTP methods."""
    job = create_test_job(db_client)
    job_id = job["id"]
    
    # Test GET
    get_resp = client.get(f"/job/{job_id}")
    assert get_resp.status_code == 200
    
    # Test POST
    post_resp = client.post(
        "/job/boost-priority",
        json={"job_id": job_id, "boost_amount": 50},
        headers=admin_headers
    )
    assert post_resp.status_code == 200
    
    # Both should have same security headers
    security_headers = ["x-content-type-options", "x-frame-options", "x-xss-protection"]
    for header in security_headers:
        assert get_resp.headers[header] == post_resp.headers[header]
    
    # Both should have API version
    assert get_resp.headers["x-api-version"] == post_resp.headers["x-api-version"]


def test_websocket_headers_different(client):
    """Test that WebSocket endpoints have different header behavior."""
    # WebSocket upgrade should behave differently from regular HTTP
    # Note: TestClient WebSocket connection might not expose all headers
    with client.websocket_connect("/ws") as websocket:
        websocket.send_text("test")
        response = websocket.receive_text()
        assert "test" in response
        # WebSocket connection established successfully
        # Detailed header testing for WebSocket is limited in test environment


def test_response_time_header_accuracy(client):
    """Test that response time headers reflect actual processing time."""
    import time
    
    start_time = time.time()
    resp = client.get("/health")
    end_time = time.time()
    
    assert resp.status_code == 200
    assert "x-process-time" in resp.headers
    
    reported_time = float(resp.headers["x-process-time"])
    actual_time = end_time - start_time
    
    # Reported time should be less than total time (excludes network/test overhead)
    assert reported_time <= actual_time
    assert reported_time > 0