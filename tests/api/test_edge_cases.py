"""Tests for API error boundaries and edge cases."""

from typing import Dict, Any

from .conftest import create_test_job, create_test_metrics, JobStatus


def test_malformed_json_requests(
    client: Any, db_client: Any, admin_headers: Dict[str, str]
) -> None:
    """Test handling of malformed JSON in request bodies."""
    job = create_test_job(db_client)
    job_id = job["id"]

    malformed_payloads = [
        '{"incomplete": json',  # Invalid JSON syntax
        '{"missing_quote: "value"}',  # Missing quote
        '{job_id: "' + job_id + '"}',  # Unquoted key
        '{"extra_comma": "value",}',  # Trailing comma
        "",  # Empty body
        "not json at all",  # Plain text
        '{"nested": {"incomplete": }',  # Incomplete nesting
    ]

    for payload in malformed_payloads:
        resp = client.post(
            "/job/kill",
            content=payload,  # Use content instead of data to send raw string
            headers={**admin_headers, "Content-Type": "application/json"},
        )
        # Should return 422 (Unprocessable Entity) for malformed JSON
        assert resp.status_code in [400, 422], (
            f"Unexpected response for payload: {payload}"
        )


def test_missing_required_fields(client: Any, admin_headers: Dict[str, str]) -> None:
    """Test handling of requests with missing required fields."""
    missing_field_requests = [
        ("/job/kill", {}),  # Missing job_id
        ("/job/requeue", {}),  # Missing job_id
        ("/job/boost-priority", {"job_id": "test"}),  # Missing boost_amount
        ("/job/boost-priority", {"boost_amount": 100}),  # Missing job_id
        ("/job/set-priority", {"job_id": "test"}),  # Missing priority
        ("/job/set-priority", {"priority": 500}),  # Missing job_id
    ]

    for endpoint, payload in missing_field_requests:
        resp = client.post(endpoint, json=payload, headers=admin_headers)
        # Should reject with validation error (400/422) or job not found (404)
        assert resp.status_code in [400, 404, 422], (
            f"Should reject missing fields for {endpoint}: {payload}"
        )


def test_invalid_field_types(
    client: Any, db_client: Any, admin_headers: Dict[str, str]
) -> None:
    """Test handling of requests with invalid field types."""
    job = create_test_job(db_client)
    job_id = job["id"]

    invalid_type_requests = [
        ("/job/boost-priority", {"job_id": job_id, "boost_amount": "not_a_number"}),
        ("/job/boost-priority", {"job_id": job_id, "boost_amount": []}),
        ("/job/boost-priority", {"job_id": job_id, "boost_amount": {}}),
        ("/job/set-priority", {"job_id": job_id, "priority": "high"}),
        ("/job/set-priority", {"job_id": job_id, "priority": [500]}),
        ("/job/kill", {"job_id": 123}),  # job_id should be string
        ("/job/requeue", {"job_id": None}),
    ]

    for endpoint, payload in invalid_type_requests:
        resp = client.post(endpoint, json=payload, headers=admin_headers)
        assert resp.status_code in [400, 422], (
            f"Should reject invalid types for {endpoint}: {payload}"
        )


def test_out_of_range_values(
    client: Any, db_client: Any, admin_headers: Dict[str, str]
) -> None:
    """Test handling of values outside valid ranges."""
    job = create_test_job(db_client)
    job_id = job["id"]

    out_of_range_requests = [
        (
            "/job/boost-priority",
            {"job_id": job_id, "boost_amount": -100},
        ),  # Negative boost
        (
            "/job/boost-priority",
            {"job_id": job_id, "boost_amount": 10000},
        ),  # Too large boost
        ("/job/set-priority", {"job_id": job_id, "priority": -1}),  # Below minimum
        ("/job/set-priority", {"job_id": job_id, "priority": 1001}),  # Above maximum
        (
            "/job/set-priority",
            {"job_id": job_id, "priority": 1.5},
        ),  # Float instead of int
    ]

    for endpoint, payload in out_of_range_requests:
        resp = client.post(endpoint, json=payload, headers=admin_headers)
        assert resp.status_code in [400, 422], (
            f"Should reject out-of-range values for {endpoint}: {payload}"
        )


def test_nonexistent_job_operations(client: Any, admin_headers: Dict[str, str]) -> None:
    """Test operations on jobs that don't exist."""
    fake_job_id = "00000000-0000-0000-0000-000000000000"

    operations = [
        ("/job/kill", {"job_id": fake_job_id}),
        ("/job/requeue", {"job_id": fake_job_id}),
        ("/job/boost-priority", {"job_id": fake_job_id, "boost_amount": 100}),
        ("/job/set-priority", {"job_id": fake_job_id, "priority": 500}),
    ]

    for endpoint, payload in operations:
        resp = client.post(endpoint, json=payload, headers=admin_headers)
        assert resp.status_code in [404, 400], (
            f"Should handle nonexistent job for {endpoint}"
        )


def test_extremely_long_strings(client: Any, admin_headers: Dict[str, str]) -> None:
    """Test handling of extremely long string inputs."""
    very_long_string = "x" * 10000  # 10KB string
    extremely_long_string = "y" * 100000  # 100KB string

    long_string_requests = [
        ("/job/kill", {"job_id": very_long_string}),
        (
            "/job/set-priority",
            {"job_id": "valid-id", "priority": 500, "reason": extremely_long_string},
        ),
    ]

    for endpoint, payload in long_string_requests:
        resp = client.post(endpoint, json=payload, headers=admin_headers)
        # Should either accept it or reject with 400/422, but not crash
        assert resp.status_code in [200, 400, 404, 422], (
            f"Should handle long strings gracefully for {endpoint}"
        )


def test_unicode_and_special_characters(
    client: Any, db_client: Any, admin_headers: Dict[str, str]
) -> None:
    """Test handling of unicode and special characters."""
    job = create_test_job(db_client)
    job_id = job["id"]

    special_strings = [
        "🚀 Rocket job",  # Emoji
        "тест",  # Cyrillic
        "测试",  # Chinese
        "job\x00with\x00nulls",  # Null bytes
        "job\nwith\nnewlines",  # Newlines
        "job\twith\ttabs",  # Tabs
        "job with 'quotes' and \"quotes\"",  # Mixed quotes
        "job with <tags> & entities",  # HTML-like content
        "job\\with\\backslashes",  # Backslashes
    ]

    for special_string in special_strings:
        resp = client.post(
            "/job/set-priority",
            json={"job_id": job_id, "priority": 600, "reason": special_string},
            headers=admin_headers,
        )
        # Should handle unicode gracefully
        assert resp.status_code in [200, 400], (
            f"Should handle special characters: {special_string}"
        )


def test_concurrent_operations_on_same_job(
    client: Any, db_client: Any, admin_headers: Dict[str, str]
) -> None:
    """Test concurrent operations on the same job."""
    import threading

    job = create_test_job(db_client, status=JobStatus.FAILED)
    job_id = job["id"]

    results = []
    errors = []

    def make_request(operation_id: int) -> None:
        try:
            resp = client.post(
                "/job/boost-priority",
                json={"job_id": job_id, "boost_amount": 10},
                headers=admin_headers,
            )
            results.append((operation_id, resp.status_code, resp.json()))
        except Exception as e:
            errors.append((operation_id, str(e)))

    # Launch multiple concurrent requests
    threads = []
    for i in range(5):
        thread = threading.Thread(target=make_request, args=(i,))
        threads.append(thread)

    # Start all threads
    for thread in threads:
        thread.start()

    # Wait for all to complete
    for thread in threads:
        thread.join(timeout=10)

    # Should handle concurrent requests gracefully
    assert len(errors) == 0, f"Errors occurred: {errors}"
    assert len(results) == 5

    # All requests should get valid responses
    for operation_id, status_code, response in results:
        assert status_code in [200, 404, 400], (
            f"Unexpected status for operation {operation_id}"
        )


def test_pagination_edge_cases(client: Any, db_client: Any) -> None:
    """Test edge cases in pagination parameters."""
    # Create a few jobs for testing
    for i in range(3):
        create_test_job(db_client, sweep_config_id=f"edge_case_{i}")

    edge_case_params = [
        "?paginated=true&page=999999&per_page=1",  # Very high page number
        "?paginated=true&page=1&per_page=1000",  # Very high per_page (should be clamped)
        "?paginated=true&page=0&per_page=10",  # Invalid page (0)
        "?paginated=true&page=-1&per_page=10",  # Negative page
        "?paginated=true&page=1&per_page=0",  # Zero per_page
        "?paginated=true&page=1&per_page=-5",  # Negative per_page
        "?paginated=true&page=abc&per_page=10",  # Non-numeric page
        "?paginated=true&page=1&per_page=xyz",  # Non-numeric per_page
        "?priority_min=999&priority_max=1",  # Min > Max
        "?priority_min=abc&priority_max=def",  # Non-numeric priorities
    ]

    for params in edge_case_params:
        resp = client.get(f"/jobs{params}")
        # Should either work or return appropriate error, but not crash
        assert resp.status_code in [200, 400, 422], (
            f"Should handle edge case params: {params}"
        )


def test_metrics_edge_cases(client: Any, db_client: Any) -> None:
    """Test edge cases for metrics endpoints."""
    job = create_test_job(db_client)
    job_id = job["id"]

    # Test with no metrics file
    resp = client.get(f"/metrics/{job_id}")
    assert resp.status_code == 404

    # Create metrics file and test edge cases
    create_test_metrics(db_client, job_id, num_metrics=0)  # Empty metrics
    resp = client.get(f"/metrics/{job_id}")
    assert resp.status_code in [200, 404]  # Might be empty but valid

    # Test with very large limit
    resp = client.get(f"/metrics/{job_id}?limit=999999")
    assert resp.status_code in [200, 400, 404]

    # Test with negative limit
    resp = client.get(f"/metrics/{job_id}?limit=-1")
    assert resp.status_code in [200, 400]

    # Test with non-numeric limit
    resp = client.get(f"/metrics/{job_id}?limit=abc")
    assert resp.status_code in [200, 400, 422]


def test_database_unavailable_simulation(tmp_path: Any, monkeypatch: Any) -> None:
    """Test behavior when database operations fail."""
    # This is harder to test without actually breaking the database
    # But we can test with an invalid path
    monkeypatch.setenv("ADMIN_API_KEY", "secret")
    monkeypatch.setenv("EXPMGR_MODE", "files_local")
    monkeypatch.setenv("DR_EXP_BASE_PATH", "/nonexistent/path/that/should/fail")

    from dr_exp.api.main import create_app
    from fastapi.testclient import TestClient

    try:
        app = create_app(base_path="/nonexistent/path")
        client = TestClient(app)

        # Health check might still work but report unhealthy database
        resp = client.get("/health")
        # Should not crash, but might report database issues
        assert resp.status_code in [200, 500]

    except Exception:
        # If app creation fails, that's also acceptable behavior
        pass


def test_very_large_responses(client: Any, db_client: Any) -> None:
    """Test handling of potentially large responses."""
    # Create many jobs to test large response handling
    jobs = []
    for i in range(50):  # Create enough jobs to make a substantial response
        job = create_test_job(
            db_client,
            job_config={"large_config": "x" * 1000, "index": i},  # Larger configs
            sweep_config_id=f"large_test_{i}",
        )
        jobs.append(job)

    # Test getting all jobs (potentially large response)
    resp = client.get("/jobs")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 50

    # Test paginated response with all jobs
    resp = client.get("/jobs?paginated=true&per_page=100")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 50


def test_request_without_content_type(
    client: Any, admin_headers: Dict[str, str]
) -> None:
    """Test requests without Content-Type header."""
    # Remove Content-Type from headers
    headers_without_content_type = {
        k: v for k, v in admin_headers.items() if k.lower() != "content-type"
    }

    resp = client.post(
        "/job/kill",
        content='{"job_id": "test-id"}',  # Send as raw content
        headers=headers_without_content_type,
    )
    # Should either work or return appropriate error
    assert resp.status_code in [200, 400, 404, 415, 422]


def test_empty_and_whitespace_only_strings(
    client: Any, db_client: Any, admin_headers: Dict[str, str]
) -> None:
    """Test handling of empty and whitespace-only strings."""
    job = create_test_job(db_client)
    job_id = job["id"]

    edge_case_strings = [
        "",  # Empty string
        " ",  # Single space
        "\t",  # Tab
        "\n",  # Newline
        "   \t\n ",  # Mixed whitespace
    ]

    for edge_string in edge_case_strings:
        # Test as job_id
        resp = client.post(
            "/job/kill", json={"job_id": edge_string}, headers=admin_headers
        )
        assert resp.status_code in [400, 404, 422], (
            f"Should handle edge string as job_id: '{repr(edge_string)}'"
        )

        # Test as reason
        resp = client.post(
            "/job/set-priority",
            json={"job_id": job_id, "priority": 500, "reason": edge_string},
            headers=admin_headers,
        )
        assert resp.status_code in [200, 400], (
            f"Should handle edge string as reason: '{repr(edge_string)}'"
        )
