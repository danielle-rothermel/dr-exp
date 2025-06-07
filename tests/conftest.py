"""Global pytest configuration and fixtures."""

import os
import pytest
import tempfile
import shutil
from pathlib import Path

from dr_exp.job_db import JobDBConfig, LocalJobDB, SupabaseJobDB


@pytest.fixture
def temp_job_db():
    """Provide a temporary LocalJobDB for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config = JobDBConfig(
            mode="files_local",
            base_path=tmpdir,
            storage_path=os.path.join(tmpdir, "storage")
        )
        config.validate()
        yield LocalJobDB(config)


@pytest.fixture(scope="session")
def supabase_test_mode():
    """Check if we should run Supabase integration tests."""
    return os.getenv("EXPMGR_MODE") == "supabase_local" and os.getenv("RUN_SUPABASE_TESTS") == "1"


@pytest.fixture
def reset_supabase_db():
    """Reset the local Supabase database before test."""
    if os.getenv("EXPMGR_MODE") == "supabase_local" and os.getenv("RUN_SUPABASE_TESTS") == "1":
        import subprocess
        try:
            # Reset the database
            subprocess.run(["supabase", "db", "reset", "--linked=false"], 
                         check=True, capture_output=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            pytest.skip("Could not reset Supabase database")


@pytest.fixture
def clean_supabase_client():
    """Provide a clean SupabaseJobDB client for testing."""
    if os.getenv("EXPMGR_MODE") != "supabase_local":
        pytest.skip("Requires EXPMGR_MODE=supabase_local")
    
    config = JobDBConfig.from_env()
    config.validate()
    return SupabaseJobDB(config)


# Pytest markers for organizing tests
def pytest_configure(config):
    """Configure pytest markers."""
    config.addinivalue_line("markers", "supabase: mark test as requiring local Supabase")
    config.addinivalue_line("markers", "slow: mark test as slow running")
    config.addinivalue_line("markers", "integration: mark test as integration test")


# Skip Supabase tests by default unless explicitly enabled
def pytest_collection_modifyitems(config, items):
    """Modify test collection to handle Supabase tests."""
    skip_supabase = pytest.mark.skip(reason="Supabase tests require EXPMGR_MODE=supabase_local and RUN_SUPABASE_TESTS=1")
    
    for item in items:
        # Skip Supabase integration tests unless explicitly enabled
        if "supabase_integration" in str(item.fspath):
            if not (os.getenv("EXPMGR_MODE") == "supabase_local" and os.getenv("RUN_SUPABASE_TESTS") == "1"):
                item.add_marker(skip_supabase)