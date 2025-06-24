# dr_exp Test Suite

This directory contains the test suite for the dr_exp deep learning experiment manager, organized by test type and functionality.

## Test Structure

```
tests/
├── unit/           # Unit tests for individual components
├── integration/    # Integration tests for system interactions
├── validation/     # Validation tests for correctness and compliance
├── fixtures/       # Shared test fixtures
├── utils/          # Test utilities and helpers
└── README.md       # This file
```

### Unit Tests (`tests/unit/`)
Fast, isolated tests for individual components:
- `test_job_db.py` - JobDB core functionality
- `test_job_lifecycle.py` - Job lifecycle management
- `test_worker.py` - Worker base functionality
- `test_sync_queue.py` - SyncQueue functionality
- `test_structured_logger.py` - Structured logging

### Integration Tests (`tests/integration/`)
Tests for system interactions and workflows:
- `test_cli.py` - CLI command integration
- `test_cli_job_management.py` - CLI job management commands
- `test_concurrency.py` - Multi-worker concurrency
- `test_database_schema.py` - Database schema and operations
- `test_hydra_config.py` - Hydra configuration system
- `test_job_operations.py` - Job operation workflows
- `test_supabase_client.py` - Supabase client integration
- `test_training_integration.py` - End-to-end training workflows
- `test_worker_launcher.py` - Multi-worker launcher
- `test_worker_sync.py` - Worker synchronization

### Validation Tests (`tests/validation/`)
Tests for correctness, compliance, and project structure:
- `test_documentation.py` - Documentation accuracy
- `test_project_structure.py` - Project structure integrity
- `test_worker_logging.py` - Worker logging functionality

## Test Markers

The test suite uses pytest markers to categorize tests:

- `@pytest.mark.slow` - Tests that take a long time to run
- `@pytest.mark.supabase` - Tests requiring Supabase services
- `@pytest.mark.gpu` - Tests requiring GPU access

## Running Tests

### Run All Tests
```bash
pytest
```

### Run by Test Type
```bash
# Unit tests only (fast)
pytest tests/unit

# Integration tests only
pytest tests/integration

# Validation tests only
pytest tests/validation
```

### Run by Markers
```bash
# Skip slow tests
pytest -m "not slow"

# Skip Supabase tests (useful when offline)
pytest -m "not supabase"

# Run only GPU tests
pytest -m gpu

# Skip both slow and Supabase tests
pytest -m "not slow and not supabase"
```

### Run Specific Test Files
```bash
# Test specific functionality
pytest tests/unit/test_job_db.py
pytest tests/integration/test_cli.py

# Test with verbose output
pytest tests/unit/test_job_db.py -v

# Test with detailed output on failures
pytest tests/unit/test_job_db.py -vvs
```

## Test Configuration

The test suite is configured via `tests/pytest.ini`:
- Test discovery patterns
- Marker definitions
- Default options

## Test Utilities

### Fixtures (`tests/fixtures/`)
Shared test fixtures for common setup:
- `temp_experiment_dir()` - Temporary experiment directory
- `temp_job_db()` - Temporary JobDB instance
- `mock_config()` - Standard test configuration

### Helpers (`tests/utils/`)
Test helper functions and utilities:
- `job_helpers.py` - Job creation and manipulation helpers
- `mocks.py` - Mock implementations for external services

## Development Guidelines

### Writing Tests
1. **Organize by functionality** - Place tests in the appropriate directory (unit/integration/validation)
2. **Use descriptive names** - Test functions should clearly describe what they test
3. **Use fixtures** - Leverage shared fixtures to reduce duplication
4. **Mark appropriately** - Use pytest markers for tests with special requirements
5. **Keep tests fast** - Unit tests should run quickly; mark slow tests appropriately

### Test Isolation
- Tests should be independent and able to run in any order
- Use temporary directories for file operations
- Clean up resources in teardown or use context managers
- Mock external services to avoid dependencies

### Continuous Integration
Tests are designed to run in CI environments:
- Tests marked with `@pytest.mark.supabase` may be skipped if Supabase is not available
- Tests marked with `@pytest.mark.gpu` may be skipped on CPU-only systems
- Slow tests can be excluded for faster CI runs