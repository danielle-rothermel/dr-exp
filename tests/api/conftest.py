"""Shared fixtures and utilities for API tests."""

import json
from pathlib import Path
from typing import Dict, Any, Optional

import pytest
from fastapi.testclient import TestClient

from dr_exp.api.main import create_app


@pytest.fixture
def isolated_app(tmp_path, monkeypatch):
    """Create an isolated API app with fresh database."""
    monkeypatch.setenv("ADMIN_API_KEY", "secret")
    monkeypatch.setenv("READER_API_KEY", "readkey")
    monkeypatch.setenv("EXPMGR_MODE", "files_local")
    monkeypatch.setenv("DR_EXP_BASE_PATH", str(tmp_path))
    
    app = create_app(base_path=str(tmp_path))
    return app


@pytest.fixture
def client(isolated_app):
    """Create test client from isolated app."""
    return TestClient(isolated_app)


@pytest.fixture
def db_client(isolated_app):
    """Get database client from isolated app."""
    return isolated_app.state.client


@pytest.fixture
def admin_headers():
    """Authentication headers for admin user."""
    return {"Authorization": "Bearer secret"}


@pytest.fixture
def reader_headers():
    """Authentication headers for reader user."""
    return {"Authorization": "Bearer readkey"}


@pytest.fixture
def invalid_headers():
    """Invalid authentication headers for testing."""
    return {"Authorization": "Bearer invalid"}


# Test data factories
def create_test_job(
    db_client,
    job_config: Optional[Dict[str, Any]] = None,
    sweep_config_id: str = "test_sweep",
    status: str = "queued",
    priority: int = 100,
    **kwargs
) -> Dict[str, Any]:
    """Create a test job with sensible defaults."""
    if job_config is None:
        job_config = {"model": {"name": "test_model"}, "lr": 0.001}
    
    return db_client.add_job(
        job_config=job_config,
        sweep_config_id=sweep_config_id,
        status=status,
        priority=priority,
        **kwargs
    )


def create_test_metrics(db_client, job_id: str, num_metrics: int = 10):
    """Create test metrics file for a job."""
    run_dir = Path(db_client.storage_dir) / f"run_{job_id}"
    run_dir.mkdir(parents=True, exist_ok=True)
    metrics_path = run_dir / "metrics.jsonl"
    
    with open(metrics_path, "w") as f:
        for i in range(num_metrics):
            metric = {
                "step": i,
                "train_loss": 2.0 - (i * 0.01),
                "val_loss": 1.8 - (i * 0.008),
                "val_accuracy": 0.1 + (i * 0.01)
            }
            f.write(json.dumps(metric) + "\n")
    
    return metrics_path


# Priority test constants
class Priority:
    LOW = 50
    NORMAL = 200
    HIGH = 500
    URGENT = 800
    SYSTEM = 950


# Job status constants  
class JobStatus:
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    KILLED = "killed"