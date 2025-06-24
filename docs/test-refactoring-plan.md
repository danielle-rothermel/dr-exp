# Test Refactoring Implementation Plan

## Overview
This document outlines the plan to refactor the test suite from step-based naming (test_step_X_Y.py) to a functional, standard structure organized by test type and component.

## Progress Tracking
Mark each commit as DONE when completed. The next agent should start with the first commit marked as TODO.

## Implementation Commits

### Phase 1: Create Test Infrastructure

**Commit 1:** `test: create new test directory structure` - DONE
```bash
mkdir -p tests/unit tests/integration tests/validation tests/fixtures tests/utils
touch tests/__init__.py tests/unit/__init__.py tests/integration/__init__.py
touch tests/validation/__init__.py tests/fixtures/__init__.py tests/utils/__init__.py
```

**Commit 2:** `test: add pytest configuration` - DONE
Create `tests/pytest.ini`:
```ini
[pytest]
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
addopts = -v --tb=short
markers =
    slow: marks tests as slow (deselect with '-m "not slow"')
    supabase: marks tests requiring Supabase (deselect with '-m "not supabase"')
    gpu: marks tests requiring GPU (deselect with '-m "not gpu"')
```

**Commit 3:** `test: create base test fixtures` - DONE
Create `tests/fixtures/conftest.py`:
```python
import pytest
import tempfile
from pathlib import Path
from dr_exp.core.job_db import JobDB

@pytest.fixture
def temp_experiment_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)

@pytest.fixture
def temp_job_db(temp_experiment_dir):
    return JobDB(
        base_path=str(temp_experiment_dir),
        experiment_name="test_exp",
        validate=False
    )

@pytest.fixture
def mock_config():
    return {
        "_target_": "dr_exp.trainers.test_trainer.train",
        "epochs": 10,
        "lr": 0.001
    }
```

**Commit 4:** `test: add job creation test utilities` - DONE
Create `tests/utils/job_helpers.py`:
```python
def create_test_job(job_db, priority=100, **kwargs):
    config = {
        "_target_": "dr_exp.trainers.test_trainer.train",
        "epochs": 10,
        **kwargs
    }
    return job_db.create_job(config, priority=priority)

def create_test_config(**overrides):
    base = {
        "_target_": "dr_exp.trainers.test_trainer.train",
        "epochs": 10,
        "lr": 0.001
    }
    base.update(overrides)
    return base

def create_multiple_jobs(job_db, count, priority_start=100, priority_step=50):
    job_ids = []
    for i in range(count):
        job_id = create_test_job(
            job_db, 
            priority=priority_start + i * priority_step,
            index=i
        )
        job_ids.append(job_id)
    return job_ids
```

**Commit 5:** `test: add mock implementations for external services` - DONE
Create `tests/utils/mocks.py`:
```python
from dr_exp.sync.supabase_client import SupabaseClient
from dr_exp.worker.base import Worker

class MockSupabaseClient(SupabaseClient):
    def __init__(self):
        self.uploaded_files = []
        self.bucket_name = "experiments"
    
    def upload_file(self, local_path, storage_path):
        self.uploaded_files.append((local_path, storage_path))
        return True
    
    def test_connection(self):
        return True

class MockWorker(Worker):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.executed_jobs = []
    
    def execute_job(self, job):
        self.executed_jobs.append(job["id"])
        return super().execute_job(job)

def mock_sync_function(item):
    """Mock sync function for testing."""
    return True
```

**Commit 6:** `test: add test environment configuration` - DONE
Create `tests/.env.test`:
```
SUPABASE_URL=http://localhost:54321
SUPABASE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZS1kZW1vIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImV4cCI6MTk4MzgxMjk5Nn0.EGIM96RAZx35lJzdJsyH-qQwv8Hdp7fsn3W0YpN81IU
TEST_MODE=true
```

### Phase 2: Refactor Unit Tests

**Commit 7:** `test: move JobDB tests to unit/test_job_db.py` - DONE
```bash
git mv tests/test_step_1_1.py tests/unit/test_job_db.py
# Update module docstring to: """Unit tests for JobDB core functionality."""
```

**Commit 8:** `test: update imports in test_job_db.py` - DONE
- Update imports to use fixtures from conftest
- Update imports to use utilities from tests/utils/
- Remove step references from docstrings
- Rename test functions if needed for clarity

**Commit 9:** `test: move job lifecycle tests to unit/test_job_lifecycle.py` - DONE
```bash
git mv tests/test_step_1_3.py tests/unit/test_job_lifecycle.py
# Update module docstring to: """Unit tests for job lifecycle management."""
```

**Commit 10:** `test: move worker tests to unit/test_worker.py` - TODO
```bash
git mv tests/test_step_2_1.py tests/unit/test_worker.py
# Update module docstring to: """Unit tests for Worker base functionality."""
```

**Commit 11:** `test: move sync queue tests to unit/test_sync_queue.py` - TODO
```bash
git mv tests/test_step_2_2.py tests/unit/test_sync_queue.py
# Update module docstring to: """Unit tests for SyncQueue functionality."""
```

**Commit 12:** `test: extract structured logger tests` - TODO
- Extract StructuredLogger tests from test_step_2_6.py
- Create tests/unit/test_structured_logger.py
- Move only the test_structured_logger function

### Phase 3: Refactor Integration Tests

**Commit 13:** `test: consolidate concurrency tests` - TODO
- Create tests/integration/test_concurrency.py
- Move all tests from test_step_1_2.py
- Add tests from test_priority_concurrency_fix.py
- Remove original files after consolidation

**Commit 14:** `test: move job operations tests` - TODO
```bash
git mv tests/test_step_1_4.py tests/integration/test_job_operations.py
# Update module docstring to: """Integration tests for job operations."""
```

**Commit 15:** `test: move worker sync integration tests` - TODO
```bash
git mv tests/test_step_2_3.py tests/integration/test_worker_sync.py
# Update module docstring to: """Integration tests for worker with sync functionality."""
```

**Commit 16:** `test: move CLI tests to integration/test_cli.py` - TODO
```bash
git mv tests/test_step_2_4.py tests/integration/test_cli.py
# Update module docstring to: """Integration tests for CLI commands."""
```

**Commit 17:** `test: move CLI job management tests` - TODO
```bash
git mv tests/test_step_2_5.py tests/integration/test_cli_job_management.py
# Update module docstring to: """Integration tests for CLI job management commands."""
```

**Commit 18:** `test: extract training integration tests` - TODO
- Move remaining tests from test_step_2_6.py to appropriate files
- Delete test_step_2_6.py after extraction

**Commit 19:** `test: move worker launcher tests` - TODO
```bash
git mv tests/test_step_2_7.py tests/integration/test_worker_launcher.py
# Update module docstring to: """Integration tests for WorkerLauncher."""
```

**Commit 20:** `test: move database schema tests` - TODO
```bash
git mv tests/test_step_3_1.py tests/integration/test_database_schema.py
# Update module docstring to: """Integration tests for database schema and operations."""
```

**Commit 21:** `test: move Supabase client tests` - TODO
```bash
git mv tests/test_step_3_2.py tests/integration/test_supabase_client.py
# Add @pytest.mark.supabase decorator to all test functions
```

**Commit 22:** `test: move Hydra config tests` - TODO
```bash
git mv tests/test_hydra_fix.py tests/integration/test_hydra_config.py
# Update module docstring to: """Integration tests for Hydra configuration."""
```

### Phase 4: Refactor Validation Tests

**Commit 23:** `test: move worker logging validation tests` - TODO
```bash
git mv tests/test_worker_logging_fix.py tests/validation/test_worker_logging.py
# Update module docstring to: """Validation tests for worker logging functionality."""
```

**Commit 24:** `test: move documentation validation tests` - TODO
```bash
git mv tests/test_doc_fixes.py tests/validation/test_documentation.py
# Update module docstring to: """Validation tests for documentation accuracy."""
```

**Commit 25:** `test: rename cleanup tests to project structure validation` - TODO
```bash
git mv tests/test_step_0_cleanup.py tests/validation/test_project_structure.py
# Update module docstring and test names to reflect project structure validation
```

### Phase 5: Final Updates

**Commit 26:** `test: update all test imports for new structure` - TODO
- Update imports in all test files to use shared fixtures
- Update imports to use test utilities
- Remove any relative imports
- Ensure all tests import from the new structure

**Commit 27:** `test: add test README documentation` - TODO
Create `tests/README.md` with:
- Test structure explanation
- How to run different test suites
- Test markers and their usage
- Examples of running subsets of tests

**Commit 28:** `test: remove old test files and check for missing tests` - TODO
- Check for any remaining test_step_*.py files in other phases (2_8, 2_9, 3_3, 3_4, 3_5)
- Move them to appropriate locations or remove if empty
- Clean up any test artifacts

**Commit 29:** `test: add test coverage configuration` - TODO
Create `.coveragerc`:
```ini
[run]
source = src/dr_exp
omit = 
    */tests/*
    */test_*
    */__pycache__/*

[report]
exclude_lines =
    pragma: no cover
    def __repr__
    raise AssertionError
    raise NotImplementedError
```

**Commit 30:** `test: verify all tests pass` - TODO
- Run `pytest` to ensure all tests pass
- Run `pytest -m "not supabase"` to verify non-Supabase tests
- Fix any import issues or test failures
- Update CI configuration if needed

## Notes for Implementation

1. Each commit should be small and focused (15-30 lines)
2. Run tests after each phase to ensure nothing is broken
3. Use `git mv` to preserve file history when moving files
4. Update imports incrementally to avoid breaking changes
5. Mark commits as DONE immediately after completion
6. If a test file mentioned in the plan doesn't exist, note it and continue