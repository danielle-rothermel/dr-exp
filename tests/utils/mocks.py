"""Mock implementations for external services in tests."""

from typing import Any
from dr_exp.sync.supabase_client import SupabaseClient
from dr_exp.worker.base import Worker


class MockSupabaseClient(SupabaseClient):
    """Mock Supabase client for testing."""

    def __init__(self) -> None:
        self.uploaded_files = []
        self.bucket_name = "experiments"

    def upload_file(self, local_path: str, storage_path: str) -> bool:
        """Mock file upload."""
        self.uploaded_files.append((local_path, storage_path))
        return True

    def test_connection(self) -> bool:
        """Mock connection test."""
        return True


class MockWorker(Worker):
    """Mock worker for testing."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize mock worker."""
        super().__init__(*args, **kwargs)
        self.executed_jobs = []

    def execute_job(self, job: dict[str, Any]) -> Any:
        """Mock job execution."""
        self.executed_jobs.append(job["id"])
        return super().execute_job(job)


def mock_sync_function(item: Any) -> bool:
    """Mock sync function for testing."""
    return True
