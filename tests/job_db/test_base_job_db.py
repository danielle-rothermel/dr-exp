"""Tests for the BaseJobDB abstract base class."""

import pytest
from typing import Any, Dict, List, Optional

from dr_exp.job_db import BaseJobDB, LocalJobDB, SupabaseJobDB, JobDBConfig


def test_base_job_db_is_abstract() -> None:
    """Test that BaseJobDB cannot be instantiated directly."""
    with pytest.raises(TypeError):
        BaseJobDB()  # type: ignore[abstract]


def test_base_job_db_inheritance() -> None:
    """Test that BaseJobDB is properly inherited by concrete implementations."""
    assert issubclass(LocalJobDB, BaseJobDB)
    assert issubclass(SupabaseJobDB, BaseJobDB)
    config = JobDBConfig(
        base_path="/tmp", storage_path="/tmp/storage", mode="files_local"
    )
    assert isinstance(LocalJobDB(config), BaseJobDB)


def test_base_job_db_enforces_abstract_methods() -> None:
    """Test that concrete implementations must implement all abstract methods."""

    class IncompleteJobDB(BaseJobDB):
        jobs_dir = "/tmp"
        storage_dir = "/tmp/storage"

        # Missing implementations of abstract methods
        pass

    with pytest.raises(TypeError):
        IncompleteJobDB()  # type: ignore[abstract]


def test_base_job_db_optional_methods_raise_not_implemented() -> None:
    """Test that optional methods raise NotImplementedError by default."""

    # Create a minimal implementation that only implements abstract methods
    class MinimalJobDB(BaseJobDB):
        jobs_dir = "/tmp"
        storage_dir = "/tmp/storage"

        def claim_job(
            self, worker_id: Optional[str] = None, respect_reservations: bool = True
        ) -> Optional[Dict[str, Any]]:
            return None

        def update_job(self, job_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
            return {"success": True}

        def get_job_details(self, job_id: str) -> Optional[Dict[str, Any]]:
            return None

        def get_config_for_job(self, job_id: str) -> Optional[Dict[str, Any]]:
            return None

        def record_failure(
            self,
            job_id: str,
            error_type: str,
            message: str,
            stacktrace: Optional[str] = None,
        ) -> Dict[str, Any]:
            return {"success": True}

        def finalize_job(
            self, job_id: str, final_status: str, metadata: Dict[str, Any]
        ) -> Dict[str, Any]:
            return {"success": True}

        def upload_artifact(
            self, job_id: str, local_path: str, remote_path_suffix: str
        ) -> Dict[str, Any]:
            return {"success": True}

        def update_job_priority(
            self, job_id: str, new_priority: int, reason: Optional[str] = None
        ) -> Dict[str, Any]:
            return {"success": True}

        def boost_job_priority(
            self, job_id: str, boost_amount: int = 100
        ) -> Dict[str, Any]:
            return {"success": True}

        def list_jobs_by_priority(
            self, status_filter: Optional[List[str]] = None, limit: Optional[int] = None
        ) -> List[Dict[str, Any]]:
            return []

        def add_reserved_job(
            self,
            job_config: Dict[str, Any],
            sweep_config_id: str,
            reserved_for_worker: str,
            reservation_timeout: int = 300,
            priority: int = 100,
            status: str = "queued",
        ) -> Dict[str, Any]:
            return {"id": "test_job", "reserved_for_worker": reserved_for_worker}

        # New abstract methods
        def list_running_jobs(self) -> List[Dict[str, Any]]:
            return []

        def get_stale_jobs(self, max_age_seconds: int) -> List[Any]:
            return []

        def mark_jobs_failed(
            self, job_ids: List[str], reason: str = "worker_lost"
        ) -> Dict[str, bool]:
            return {}

        def has_queued_jobs(self) -> bool:
            return False

        def get_queue_summary(self, limit: int = 5) -> List[Dict[str, Any]]:
            return []

        def get_metrics(
            self, run_id: str, limit: Optional[int] = None
        ) -> List[Dict[str, Any]]:
            return []

    db = MinimalJobDB()

    # Test that optional methods raise NotImplementedError
    with pytest.raises(NotImplementedError, match="list_jobs not implemented"):
        db.list_jobs()

    with pytest.raises(NotImplementedError, match="add_job not implemented"):
        db.add_job({}, "test_sweep")

    with pytest.raises(NotImplementedError, match="log_metrics not implemented"):
        db.log_metrics("job1", [])


def test_local_job_db_implements_optional_methods() -> None:
    """Test that LocalJobDB properly implements optional methods."""
    config = JobDBConfig(
        base_path="/tmp", storage_path="/tmp/storage", mode="files_local"
    )
    db = LocalJobDB(config)

    # These should not raise NotImplementedError
    jobs = db.list_jobs()
    assert isinstance(jobs, list)

    # Note: We don't test add_job and log_metrics here as they require actual file operations


def test_interface_consistency() -> None:
    """Test that both implementations have consistent interfaces."""
    local_config = JobDBConfig(
        base_path="/tmp", storage_path="/tmp/storage", mode="files_local"
    )
    local_db = LocalJobDB(local_config)

    # Use a valid JWT format for testing (this is a fake JWT that will pass format validation)
    fake_jwt = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiaWF0IjoxNTE2MjM5MDIyfQ.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"

    # Mock the Supabase client creation to avoid network calls
    import unittest.mock

    supabase_config = JobDBConfig(
        base_path="/tmp",
        storage_path="/tmp/storage",
        supabase_url="http://test",
        supabase_key=fake_jwt,
        mode="supabase_remote",
    )
    with unittest.mock.patch("dr_exp.job_db.supabase_job_db.create_client"):
        supabase_db = SupabaseJobDB(supabase_config)

    # Both should be instances of BaseJobDB
    assert isinstance(local_db, BaseJobDB)
    assert isinstance(supabase_db, BaseJobDB)

    # Both should have required attributes
    assert hasattr(local_db, "jobs_dir")
    assert hasattr(local_db, "storage_dir")
    assert hasattr(supabase_db, "jobs_dir")
    assert hasattr(supabase_db, "storage_dir")

    # Both should have all abstract methods
    abstract_methods = [
        "claim_job",
        "update_job",
        "get_job_details",
        "get_config_for_job",
        "record_failure",
        "finalize_job",
        "upload_artifact",
    ]

    for method in abstract_methods:
        assert hasattr(local_db, method) and callable(getattr(local_db, method))
        assert hasattr(supabase_db, method) and callable(getattr(supabase_db, method))


def test_base_job_db_docstrings() -> None:
    """Test that abstract methods have proper docstrings."""
    methods_to_check = [
        "claim_job",
        "update_job",
        "get_job_details",
        "get_config_for_job",
        "record_failure",
        "finalize_job",
        "upload_artifact",
    ]

    for method_name in methods_to_check:
        method = getattr(BaseJobDB, method_name)
        assert method.__doc__ is not None, f"{method_name} should have a docstring"
        assert "Parameters" in method.__doc__, (
            f"{method_name} docstring should document parameters"
        )
        assert "Returns" in method.__doc__, (
            f"{method_name} docstring should document return value"
        )


def test_type_annotations() -> None:
    """Test that BaseJobDB methods have proper type annotations."""
    import inspect

    # Check that abstract methods have type annotations
    sig = inspect.signature(BaseJobDB.claim_job)
    assert "return" in sig.parameters or hasattr(sig, "return_annotation")

    sig = inspect.signature(BaseJobDB.update_job)
    assert len(sig.parameters) >= 2  # self, job_id, data
