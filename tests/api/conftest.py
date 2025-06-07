"""Shared fixtures and utilities for API tests."""

import json
from pathlib import Path
from typing import Dict, Any, Optional, List

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
                "val_accuracy": 0.1 + (i * 0.01),
                "timestamp": f"2024-01-01T10:{30+i:02d}:00Z"
            }
            f.write(json.dumps(metric) + "\n")
    
    return metrics_path


def create_multiple_jobs(
    db_client,
    count: int,
    status_distribution: Optional[Dict[str, float]] = None,
    priority_range: Optional[tuple] = None
) -> List[Dict[str, Any]]:
    """Create multiple test jobs with configurable distributions.
    
    Parameters
    ----------
    db_client : BaseJobDB
        Database client to create jobs with
    count : int
        Number of jobs to create
    status_distribution : Dict[str, float], optional
        Status distribution (e.g., {"queued": 0.5, "running": 0.3, "completed": 0.2})
    priority_range : tuple, optional
        Priority range as (min, max), defaults to (50, 500)
        
    Returns
    -------
    List[Dict[str, Any]]
        List of created job records
    """
    if status_distribution is None:
        status_distribution = {
            JobStatus.QUEUED: 0.4,
            JobStatus.RUNNING: 0.3,
            JobStatus.COMPLETED: 0.2,
            JobStatus.FAILED: 0.1
        }
    
    if priority_range is None:
        priority_range = (50, 500)
    
    import random
    jobs = []
    statuses = list(status_distribution.keys())
    weights = list(status_distribution.values())
    
    for i in range(count):
        status = random.choices(statuses, weights=weights)[0]
        priority = random.randint(priority_range[0], priority_range[1])
        
        job = create_test_job(
            db_client,
            job_config={"batch_size": 32, "model": f"model_{i}", "lr": 0.001 + (i * 0.0001)},
            sweep_config_id=f"multi_sweep_{i}",
            status=status,
            priority=priority
        )
        jobs.append(job)
    
    return jobs


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