"""Tests for test isolation and consistency."""

import tempfile
from pathlib import Path
from .conftest import create_test_job, JobStatus


def test_test_isolation_between_functions(tmp_path, monkeypatch):
    """Test that test functions don't interfere with each other."""
    from dr_exp.api.main import create_app
    from fastapi.testclient import TestClient

    # Create first isolated environment
    monkeypatch.setenv("ADMIN_API_KEY", "secret")
    monkeypatch.setenv("READER_API_KEY", "readkey")
    monkeypatch.setenv("EXPMGR_MODE", "files_local")
    monkeypatch.setenv("DR_EXP_BASE_PATH", str(tmp_path / "env1"))

    app1 = create_app(base_path=str(tmp_path / "env1"))
    client1 = TestClient(app1)
    db_client1 = app1.state.client

    # Create job in first environment
    job1 = create_test_job(db_client1, sweep_config_id="env1_job")

    # Create second isolated environment
    monkeypatch.setenv("DR_EXP_BASE_PATH", str(tmp_path / "env2"))

    app2 = create_app(base_path=str(tmp_path / "env2"))
    client2 = TestClient(app2)
    db_client2 = app2.state.client

    # Second environment should be empty
    resp2 = client2.get("/jobs")
    assert resp2.status_code == 200
    assert len(resp2.json()) == 0

    # Create job in second environment
    job2 = create_test_job(db_client2, sweep_config_id="env2_job")

    # Verify isolation - each environment should only see its own job
    resp1 = client1.get("/jobs")
    assert resp1.status_code == 200
    jobs1 = resp1.json()
    assert len(jobs1) == 1
    assert jobs1[0]["id"] == job1["id"]

    resp2 = client2.get("/jobs")
    assert resp2.status_code == 200
    jobs2 = resp2.json()
    assert len(jobs2) == 1
    assert jobs2[0]["id"] == job2["id"]

    # Jobs should have different IDs
    assert job1["id"] != job2["id"]


def test_temporary_directory_cleanup():
    """Test that temporary directories are properly cleaned up."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)

        # Create some test files
        (tmp_path / "test_file.json").write_text('{"test": "data"}')
        (tmp_path / "subdir").mkdir()
        (tmp_path / "subdir" / "nested.txt").write_text("nested content")

        # Verify files exist
        assert (tmp_path / "test_file.json").exists()
        assert (tmp_path / "subdir" / "nested.txt").exists()

    # After context manager, directory should be cleaned up
    assert not tmp_path.exists()


def test_environment_variable_isolation(monkeypatch):
    """Test that environment variables are properly isolated."""
    import os

    # Set some test environment variables
    monkeypatch.setenv("TEST_VAR", "test_value")
    monkeypatch.setenv("EXPMGR_MODE", "files_local")

    # Verify they're set
    assert os.getenv("TEST_VAR") == "test_value"
    assert os.getenv("EXPMGR_MODE") == "files_local"

    # Environment will be restored after test


def test_database_state_isolation(client, db_client):
    """Test that database state doesn't leak between tests."""
    # This test should start with an empty database
    resp = client.get("/jobs")
    assert resp.status_code == 200
    initial_jobs = resp.json()

    # In isolated mode, should start empty or with predictable state
    # (depending on whether other tests in same file have run)

    # Create a job
    job = create_test_job(db_client, sweep_config_id="isolation_test")

    # Verify it exists
    resp = client.get("/jobs")
    assert resp.status_code == 200
    jobs = resp.json()
    assert len(jobs) == len(initial_jobs) + 1

    # Job should be findable by ID
    resp = client.get(f"/job/{job['id']}")
    assert resp.status_code == 200
    assert resp.json()["id"] == job["id"]


def test_api_client_independence(tmp_path, monkeypatch):
    """Test that multiple API clients can operate independently."""
    from dr_exp.api.main import create_app
    from fastapi.testclient import TestClient

    # Setup environment
    monkeypatch.setenv("ADMIN_API_KEY", "secret")
    monkeypatch.setenv("EXPMGR_MODE", "files_local")
    monkeypatch.setenv("DR_EXP_BASE_PATH", str(tmp_path))

    # Create two separate app instances
    app1 = create_app(base_path=str(tmp_path))
    app2 = create_app(base_path=str(tmp_path))

    client1 = TestClient(app1)
    client2 = TestClient(app2)

    # Both should share the same underlying database
    db_client1 = app1.state.client
    job = create_test_job(db_client1)

    # Both clients should see the same job
    resp1 = client1.get(f"/job/{job['id']}")
    resp2 = client2.get(f"/job/{job['id']}")

    assert resp1.status_code == 200
    assert resp2.status_code == 200
    assert resp1.json()["id"] == resp2.json()["id"]


def test_fixture_consistency(client, db_client, admin_headers, reader_headers):
    """Test that fixtures provide consistent interface."""
    # Test that all required fixtures are available and work
    assert client is not None
    assert db_client is not None
    assert admin_headers is not None
    assert reader_headers is not None

    # Test client works
    resp = client.get("/health")
    assert resp.status_code == 200

    # Test database client works
    job = create_test_job(db_client)
    assert "id" in job

    # Test auth headers work
    assert "Authorization" in admin_headers
    assert "Authorization" in reader_headers
    assert admin_headers["Authorization"] != reader_headers["Authorization"]


def test_test_data_consistency():
    """Test that test data generation is consistent and predictable."""
    from .conftest import Priority

    # Test that constants are well-defined
    assert Priority.LOW < Priority.NORMAL < Priority.HIGH < Priority.URGENT
    assert Priority.LOW >= 0
    assert Priority.URGENT <= 1000

    # Test that job status constants are valid
    valid_statuses = {"queued", "running", "completed", "failed", "killed"}
    assert JobStatus.QUEUED in valid_statuses
    assert JobStatus.RUNNING in valid_statuses
    assert JobStatus.COMPLETED in valid_statuses
    assert JobStatus.FAILED in valid_statuses
    assert JobStatus.KILLED in valid_statuses


def test_error_state_isolation(client, db_client):
    """Test that error states don't affect subsequent tests."""
    # Try to access non-existent resource
    resp = client.get("/job/nonexistent-id")
    assert resp.status_code == 404

    # Try malformed request
    resp = client.post("/job/kill", json={"invalid": "data"})
    assert resp.status_code in [400, 401, 403, 422]

    # Normal operations should still work
    job = create_test_job(db_client)
    resp = client.get(f"/job/{job['id']}")
    assert resp.status_code == 200

    # Health check should still work
    resp = client.get("/health")
    assert resp.status_code == 200
