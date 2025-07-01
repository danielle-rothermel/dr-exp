"""Unit tests for FastAPI endpoints in simple_api.py."""

import os
from pathlib import Path
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient

from dr_exp.api.simple_api import app
from dr_exp.core.job_db import JobDB


class TestAPIEndpoints:
    """Test cases for FastAPI endpoints."""

    def setup_method(self) -> None:
        """Set up test environment for each test."""
        # Clear global job_db
        import dr_exp.api.simple_api

        dr_exp.api.simple_api.job_db = None

    def test_startup_event_success(self) -> None:
        """Test successful startup event initialization."""
        with (
            patch.dict(
                os.environ,
                {"DR_EXP_BASE_PATH": "/test/path", "DR_EXP_EXPERIMENT": "test_exp"},
            ),
            patch("dr_exp.api.simple_api.JobDB") as mock_job_db_class,
        ):
            mock_job_db = Mock(spec=JobDB)
            mock_job_db.experiment_name = "test_exp"
            mock_job_db.enable_remote_read.return_value = True
            mock_job_db.sync_mode.return_value = "remote"
            mock_job_db_class.return_value = mock_job_db

            with patch("builtins.print") as mock_print:
                # Import and call startup manually to test
                from dr_exp.api.simple_api import startup_event

                # Use asyncio to run the coroutine
                import asyncio

                asyncio.run(startup_event())

                # Verify JobDB was initialized correctly
                mock_job_db_class.assert_called_once_with(
                    base_path="/test/path", experiment_name="test_exp"
                )
                mock_job_db.enable_remote_read.assert_called_once()

                mock_print.assert_any_call("Remote read enabled for test_exp")
                mock_print.assert_any_call("Sync mode: remote")

    def test_startup_event_missing_env_vars(self) -> None:
        """Test startup event with missing environment variables."""
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("builtins.print") as mock_print,
        ):
            from dr_exp.api.simple_api import startup_event

            import asyncio

            asyncio.run(startup_event())

            mock_print.assert_called_with(
                "ERROR: DR_EXP_BASE_PATH and DR_EXP_EXPERIMENT must be set"
            )

    def test_startup_event_remote_read_failed(self) -> None:
        """Test startup event when remote read fails."""
        with (
            patch.dict(
                os.environ,
                {"DR_EXP_BASE_PATH": "/test/path", "DR_EXP_EXPERIMENT": "test_exp"},
            ),
            patch("dr_exp.api.simple_api.JobDB") as mock_job_db_class,
        ):
            mock_job_db = Mock(spec=JobDB)
            mock_job_db.experiment_name = "test_exp"
            mock_job_db.enable_remote_read.return_value = False
            mock_job_db_class.return_value = mock_job_db

            with patch("builtins.print") as mock_print:
                from dr_exp.api.simple_api import startup_event

                import asyncio

                asyncio.run(startup_event())

                mock_print.assert_called_with(
                    "Remote read not available - using local data only"
                )

    def test_root_endpoint_initialized(self) -> None:
        """Test root endpoint when JobDB is initialized."""
        with patch("dr_exp.api.simple_api.job_db") as mock_job_db:
            mock_job_db.experiment_name = "test_exp"
            mock_job_db.sync_mode.return_value = "remote"

            client = TestClient(app)
            response = client.get("/")

            assert response.status_code == 200
            data = response.json()
            assert data["service"] == "dr_exp API"
            assert data["version"] == "1.0.0"
            assert data["experiment"] == "test_exp"
            assert data["sync_mode"] == "remote"

    def test_root_endpoint_not_initialized(self) -> None:
        """Test root endpoint when JobDB is not initialized."""
        with patch("dr_exp.api.simple_api.job_db", None):
            client = TestClient(app)
            response = client.get("/")

            assert response.status_code == 200
            data = response.json()
            assert data["service"] == "dr_exp API"
            assert data["experiment"] is None
            assert data["sync_mode"] == "not_initialized"

    def test_get_experiment_info_success(self) -> None:
        """Test get experiment info endpoint success."""
        with patch("dr_exp.api.simple_api.job_db") as mock_job_db:
            expected_info = {
                "experiment_name": "test_exp",
                "total_jobs": 10,
                "status_counts": {"queued": 3, "running": 2, "completed": 5},
            }
            mock_job_db.get_experiment_info_remote.return_value = expected_info

            client = TestClient(app)
            response = client.get("/experiment/info")

            assert response.status_code == 200
            assert response.json() == expected_info
            mock_job_db.get_experiment_info_remote.assert_called_once()

    def test_get_experiment_info_not_initialized(self) -> None:
        """Test get experiment info when JobDB not initialized."""
        with patch("dr_exp.api.simple_api.job_db", None):
            client = TestClient(app)
            response = client.get("/experiment/info")

            assert response.status_code == 503
            assert response.json()["detail"] == "Service not initialized"

    def test_list_jobs_remote(self) -> None:
        """Test list jobs endpoint with remote data."""
        with patch("dr_exp.api.simple_api.job_db") as mock_job_db:
            mock_job_db.remote_enabled = True
            expected_jobs = [
                {"id": "job_1", "status": "completed"},
                {"id": "job_2", "status": "running"},
            ]
            mock_job_db.list_jobs_remote.return_value = expected_jobs

            client = TestClient(app)
            response = client.get("/jobs?status=running&limit=10&use_remote=true")

            assert response.status_code == 200
            data = response.json()
            assert data["jobs"] == expected_jobs
            assert data["count"] == 2
            assert data["source"] == "remote"

            mock_job_db.list_jobs_remote.assert_called_once_with(status="running")

    def test_list_jobs_local(self) -> None:
        """Test list jobs endpoint with local data."""
        with patch("dr_exp.api.simple_api.job_db") as mock_job_db:
            mock_job_db.remote_enabled = False
            expected_jobs = [{"id": "job_1", "status": "queued"}]
            mock_job_db.list_jobs.return_value = expected_jobs

            client = TestClient(app)
            response = client.get("/jobs?use_remote=false")

            assert response.status_code == 200
            data = response.json()
            assert data["jobs"] == expected_jobs
            assert data["source"] == "local"

            mock_job_db.list_jobs.assert_called_once_with(status=None)

    def test_list_jobs_limit_applied(self) -> None:
        """Test list jobs applies limit correctly."""
        with patch("dr_exp.api.simple_api.job_db") as mock_job_db:
            mock_job_db.remote_enabled = True
            # Return more jobs than limit
            all_jobs = [{"id": f"job_{i}"} for i in range(5)]
            mock_job_db.list_jobs_remote.return_value = all_jobs

            client = TestClient(app)
            response = client.get("/jobs?limit=3")

            assert response.status_code == 200
            data = response.json()
            assert len(data["jobs"]) == 3
            assert data["count"] == 3

    def test_list_jobs_not_initialized(self) -> None:
        """Test list jobs when JobDB not initialized."""
        with patch("dr_exp.api.simple_api.job_db", None):
            client = TestClient(app)
            response = client.get("/jobs")

            assert response.status_code == 503
            assert response.json()["detail"] == "Service not initialized"

    def test_get_job_remote_success(self) -> None:
        """Test get job endpoint with remote data success."""
        with patch("dr_exp.api.simple_api.job_db") as mock_job_db:
            mock_job_db.remote_enabled = True
            expected_job = {"id": "job_123", "status": "completed", "config": {}}
            mock_job_db.get_job_remote.return_value = expected_job

            client = TestClient(app)
            response = client.get("/jobs/job_123?use_remote=true")

            assert response.status_code == 200
            assert response.json() == expected_job
            mock_job_db.get_job_remote.assert_called_once_with("job_123")

    def test_get_job_local_success(self) -> None:
        """Test get job endpoint with local data success."""
        with patch("dr_exp.api.simple_api.job_db") as mock_job_db:
            expected_job = {"id": "job_123", "status": "queued"}
            mock_job_db.get_job.return_value = expected_job

            client = TestClient(app)
            response = client.get("/jobs/job_123?use_remote=false")

            assert response.status_code == 200
            assert response.json() == expected_job
            mock_job_db.get_job.assert_called_once_with("job_123")

    def test_get_job_not_found(self) -> None:
        """Test get job endpoint when job not found."""
        with patch("dr_exp.api.simple_api.job_db") as mock_job_db:
            mock_job_db.remote_enabled = True
            mock_job_db.get_job_remote.return_value = None

            client = TestClient(app)
            response = client.get("/jobs/nonexistent")

            assert response.status_code == 404
            assert response.json()["detail"] == "Job not found"

    def test_get_job_not_initialized(self) -> None:
        """Test get job when JobDB not initialized."""
        with patch("dr_exp.api.simple_api.job_db", None):
            client = TestClient(app)
            response = client.get("/jobs/job_123")

            assert response.status_code == 503
            assert response.json()["detail"] == "Service not initialized"

    def test_list_job_artifacts_success(self) -> None:
        """Test list job artifacts endpoint success."""
        with patch("dr_exp.api.simple_api.job_db") as mock_job_db:
            mock_job_db.remote_enabled = True
            mock_remote_client = Mock()
            mock_job_db.remote_client = mock_remote_client

            sync_records = [
                {
                    "file_path": "/path/to/model.pt",
                    "file_type": "checkpoint",
                    "size_bytes": 1024,
                    "checksum": "abc123",
                    "completed_at": "2023-01-01T12:00:00Z",
                    "status": "completed",
                },
                {
                    "file_path": "/path/to/log.txt",
                    "file_type": "log",
                    "size_bytes": 512,
                    "checksum": "def456",
                    "completed_at": "2023-01-01T12:01:00Z",
                    "status": "pending",  # Should be filtered out
                },
            ]
            mock_remote_client.get_job_sync_status.return_value = sync_records

            client = TestClient(app)
            response = client.get("/jobs/job_123/artifacts")

            assert response.status_code == 200
            data = response.json()
            assert data["job_id"] == "job_123"
            assert len(data["artifacts"]) == 1  # Only completed
            assert data["count"] == 1

            artifact = data["artifacts"][0]
            assert artifact["file_name"] == "model.pt"
            assert artifact["file_type"] == "checkpoint"
            assert artifact["size_bytes"] == 1024

    def test_list_job_artifacts_no_remote(self) -> None:
        """Test list job artifacts when remote not enabled."""
        with patch("dr_exp.api.simple_api.job_db") as mock_job_db:
            mock_job_db.remote_enabled = False

            client = TestClient(app)
            response = client.get("/jobs/job_123/artifacts")

            assert response.status_code == 503
            assert response.json()["detail"] == "Remote storage not available"

    def test_list_job_artifacts_not_initialized(self) -> None:
        """Test list job artifacts when JobDB not initialized."""
        with patch("dr_exp.api.simple_api.job_db", None):
            client = TestClient(app)
            response = client.get("/jobs/job_123/artifacts")

            assert response.status_code == 503

    def test_list_job_artifacts_exception(self) -> None:
        """Test list job artifacts handles exceptions."""
        with patch("dr_exp.api.simple_api.job_db") as mock_job_db:
            mock_job_db.remote_enabled = True
            mock_remote_client = Mock()
            mock_job_db.remote_client = mock_remote_client
            mock_remote_client.get_job_sync_status.side_effect = Exception("DB error")

            client = TestClient(app)
            response = client.get("/jobs/job_123/artifacts")

            assert response.status_code == 500
            assert "DB error" in response.json()["detail"]

    def test_download_job_artifacts_success(self) -> None:
        """Test download job artifacts endpoint success."""
        with patch("dr_exp.api.simple_api.job_db") as mock_job_db:
            mock_job_db.remote_enabled = True
            downloaded_paths = [Path("model.pt"), Path("log.txt")]
            mock_job_db.download_job_artifacts.return_value = downloaded_paths
            mock_job_db.get_storage_path.return_value = Path("/storage/job_123")

            client = TestClient(app)
            response = client.post("/jobs/job_123/download")

            assert response.status_code == 200
            data = response.json()
            assert data["job_id"] == "job_123"
            assert data["downloaded_files"] == ["model.pt", "log.txt"]
            assert data["count"] == 2
            assert data["target_dir"] == "/storage/job_123"

    def test_download_job_artifacts_not_initialized(self) -> None:
        """Test download job artifacts when JobDB not initialized."""
        with patch("dr_exp.api.simple_api.job_db", None):
            client = TestClient(app)
            response = client.post("/jobs/job_123/download")

            assert response.status_code == 503
            assert response.json()["detail"] == "Service not initialized"

    def test_download_job_artifacts_no_remote(self) -> None:
        """Test download job artifacts when remote not enabled."""
        with patch("dr_exp.api.simple_api.job_db") as mock_job_db:
            mock_job_db.remote_enabled = False

            client = TestClient(app)
            response = client.post("/jobs/job_123/download")

            assert response.status_code == 503
            assert response.json()["detail"] == "Remote storage not available"

    def test_download_job_artifacts_exception(self) -> None:
        """Test download job artifacts handles exceptions."""
        with patch("dr_exp.api.simple_api.job_db") as mock_job_db:
            mock_job_db.remote_enabled = True
            mock_job_db.download_job_artifacts.side_effect = Exception(
                "Download failed"
            )

            client = TestClient(app)
            response = client.post("/jobs/job_123/download")

            assert response.status_code == 500
            assert "Download failed" in response.json()["detail"]

    def test_get_queue_stats_success(self) -> None:
        """Test get queue stats endpoint success."""
        with patch("dr_exp.api.simple_api.job_db") as mock_job_db:
            experiment_info = {
                "total_jobs": 15,
                "status_counts": {
                    "queued": 5,
                    "running": 3,
                    "completed": 7,
                    "failed": 0,
                },
            }
            mock_job_db.get_experiment_info_remote.return_value = experiment_info

            client = TestClient(app)
            response = client.get("/queue/stats")

            assert response.status_code == 200
            data = response.json()
            assert data["total_jobs"] == 15
            assert data["by_status"] == experiment_info["status_counts"]
            assert data["queue_length"] == 5
            assert data["active_jobs"] == 3

    def test_get_queue_stats_not_initialized(self) -> None:
        """Test get queue stats when JobDB not initialized."""
        with patch("dr_exp.api.simple_api.job_db", None):
            client = TestClient(app)
            response = client.get("/queue/stats")

            assert response.status_code == 503
            assert response.json()["detail"] == "Service not initialized"

    def test_health_check_healthy(self) -> None:
        """Test health check endpoint when healthy."""
        with patch("dr_exp.api.simple_api.job_db") as mock_job_db:
            mock_job_db.remote_enabled = True
            mock_remote_client = Mock()
            mock_job_db.remote_client = mock_remote_client
            mock_remote_client.test_connection.return_value = True

            client = TestClient(app)
            response = client.get("/health")

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "healthy"
            assert data["job_db"] is True
            assert data["remote_enabled"] is True
            assert data["remote_connection"] is True

    def test_health_check_not_initialized(self) -> None:
        """Test health check when JobDB not initialized."""
        with patch("dr_exp.api.simple_api.job_db", None):
            client = TestClient(app)
            response = client.get("/health")

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "unhealthy"
            assert data["job_db"] is False
            assert data["remote_enabled"] is False

    def test_health_check_remote_connection_failed(self) -> None:
        """Test health check when remote connection fails."""
        with patch("dr_exp.api.simple_api.job_db") as mock_job_db:
            mock_job_db.remote_enabled = True
            mock_remote_client = Mock()
            mock_job_db.remote_client = mock_remote_client
            mock_remote_client.test_connection.side_effect = Exception(
                "Connection failed"
            )

            client = TestClient(app)
            response = client.get("/health")

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "healthy"  # Still healthy, just remote failed
            assert data["remote_connection"] is False

    def test_health_check_no_remote_client(self) -> None:
        """Test health check when remote enabled but no client."""
        with patch("dr_exp.api.simple_api.job_db") as mock_job_db:
            mock_job_db.remote_enabled = True
            mock_job_db.remote_client = None

            client = TestClient(app)
            response = client.get("/health")

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "healthy"
            assert data["remote_enabled"] is True
            # Should not have remote_connection key when no client
            assert "remote_connection" not in data

    def test_cors_middleware_enabled(self) -> None:
        """Test that CORS middleware is properly configured."""
        client = TestClient(app)

        # Make a simple GET request with Origin header
        response = client.get("/", headers={"Origin": "http://localhost:3000"})

        # Should have CORS headers - the middleware reflects the origin
        assert "access-control-allow-origin" in response.headers
        # With allow_origins=["*"], it should allow any origin
        assert response.headers["access-control-allow-origin"] in [
            "*",
            "http://localhost:3000",
        ]
