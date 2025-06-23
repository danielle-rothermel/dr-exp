# Testing Standards for dr_exp

## Test Structure
```
tests/
├── conftest.py          # Shared fixtures
├── test_job_db.py       # Unit tests for JobDB
├── test_worker.py       # Worker tests
├── test_integration.py  # Full workflow tests
├── test_api.py         # API endpoint tests
└── test_cli.py         # CLI command tests
```

## Running Tests
- Full suite: `pt` or `uv run pytest`
- Specific test: `pt tests/test_job_db.py`
- With coverage: `pt --cov=dr_exp`
- Verbose output: `pt -v`
- Stop on first failure: `pt -x`

## Test Patterns

### Use Fixtures for Common Setup
```python
import pytest
from pathlib import Path

@pytest.fixture
def temp_job_dir(tmp_path):
    """Create a temporary job directory for testing."""
    job_dir = tmp_path / "jobs"
    job_dir.mkdir()
    return job_dir

def test_job_creation(temp_job_dir):
    """Test job creation with clean directory."""
    db = JobDB(base_path=temp_job_dir.parent)
    # Test continues...
```

### Parametrize for Multiple Test Cases
```python
@pytest.mark.parametrize("priority,expected", [
    (0, "low"),
    (500, "normal"),
    (1000, "urgent"),
])
def test_priority_classification(priority, expected):
    """Test priority level classification."""
    assert classify_priority(priority) == expected
```

### Mock External Dependencies
```python
from unittest.mock import patch, MagicMock

def test_worker_heartbeat():
    """Test worker heartbeat without actual file writes."""
    with patch('dr_exp.job_db.fcntl') as mock_fcntl:
        mock_fcntl.flock = MagicMock()
        # Test heartbeat logic
```

### Test Both Success and Failure Paths
```python
def test_job_claim_success():
    """Test successful job claim."""
    # Test happy path

def test_job_claim_no_jobs():
    """Test claim when no jobs available."""
    # Test empty queue case

def test_job_claim_concurrent():
    """Test concurrent claims don't conflict."""
    # Test race conditions
```

## Common Test Warnings

### ⚠️ CRITICAL: Test Intent is Sacred
```python
def test_job_priority_ordering():
    """Jobs MUST be claimed in priority order.
    
    ⚠️ This test verifies critical scheduling behavior.
    If it fails, the implementation has a priority bug.
    DO NOT modify this test - fix the implementation.
    """
    db = JobDB(base_path=tmp_path)
    
    # Create jobs with different priorities
    job1_id = db.create_job({"priority": 100})
    job2_id = db.create_job({"priority": 900})
    job3_id = db.create_job({"priority": 500})
    
    # Claims MUST happen in priority order
    assert db.claim_next_job("worker1")["id"] == job2_id  # 900 first
    assert db.claim_next_job("worker2")["id"] == job3_id  # 500 second
    assert db.claim_next_job("worker3")["id"] == job1_id  # 100 last
```

## Integration Test Patterns

### Full Workflow Tests
```python
def test_end_to_end_job_execution():
    """Test complete job lifecycle."""
    # 1. Create job
    # 2. Worker claims it
    # 3. Worker executes
    # 4. Worker completes
    # 5. Verify results
```

### Concurrency Tests
```python
def test_multiple_workers_no_conflicts():
    """Test multiple workers don't claim same job."""
    # Use threading or multiprocessing
    # Verify no job claimed twice
```

## Test Organization Best Practices

1. **One assertion per test** (when possible)
2. **Descriptive test names** that explain what's being tested
3. **Docstrings** that explain the test's purpose
4. **Arrange-Act-Assert** pattern
5. **Cleanup** in fixtures, not in tests

## Quality Gates for Tests

Before ANY commit, ensure:

```bash
# All tests pass
pt
# Expected output: "====== X passed ======"
# NO warnings, NO skips, NO failures

# With coverage
pt --cov=dr_exp --cov-report=term-missing
# Expected: >80% coverage, no critical paths uncovered

# Type checking passes
mp
# Expected: "Success: no issues found"

# Code quality passes
ckdr
# Expected: "All checks passed!"
```

## Init Command Tests

Create `tests/test_init_command.py`:

```python
import pytest
from pathlib import Path
from click.testing import CliRunner
from dr_exp.cli import cli

def test_init_creates_directories(tmp_path):
    """Test init creates all required directories."""
    runner = CliRunner()
    result = runner.invoke(cli, [
        '--base-path', str(tmp_path),
        '--experiment', 'test_exp',
        'init'
    ])
    
    assert result.exit_code == 0
    assert (tmp_path / 'test_exp' / 'jobs').exists()
    assert (tmp_path / 'test_exp' / 'storage').exists()
    assert (tmp_path / 'test_exp' / 'sync_queue').exists()
    assert (tmp_path / 'test_exp' / 'logs').exists()
    assert (tmp_path / 'test_exp' / 'control').exists()
    assert (tmp_path / 'test_exp' / 'slurm_logs').exists()
    assert (tmp_path / 'test_exp' / '.gitignore').exists()
    assert (tmp_path / 'test_exp' / 'README.md').exists()

def test_init_already_exists(tmp_path):
    """Test init detects existing experiment."""
    exp_path = tmp_path / 'test_exp'
    exp_path.mkdir(parents=True)
    # Create all required directories
    for dir_name in ['jobs', 'storage', 'sync_queue', 'logs', 'control']:
        (exp_path / dir_name).mkdir()
    
    runner = CliRunner()
    result = runner.invoke(cli, [
        '--base-path', str(tmp_path),
        '--experiment', 'test_exp',
        'init'
    ])
    
    assert result.exit_code == 0
    assert '✓ Experiment already initialized' in result.output

def test_init_force_overwrites(tmp_path):
    """Test --force flag overwrites existing experiment."""
    exp_path = tmp_path / 'test_exp'
    exp_path.mkdir(parents=True)
    old_file = exp_path / 'old_file.txt'
    old_file.write_text('old content')
    
    runner = CliRunner()
    result = runner.invoke(cli, [
        '--base-path', str(tmp_path),
        '--experiment', 'test_exp',
        'init',
        '--force'
    ])
    
    assert result.exit_code == 0
    assert '✅ Experiment initialized successfully!' in result.output
    # Old file should still exist (we don't delete, just create missing)
    assert old_file.exists()

def test_init_with_examples(tmp_path):
    """Test --with-examples creates sample configs."""
    runner = CliRunner()
    result = runner.invoke(cli, [
        '--base-path', str(tmp_path),
        '--experiment', 'test_exp',
        'init',
        '--with-examples'
    ])
    
    assert result.exit_code == 0
    assert (tmp_path / 'test_exp' / 'example_configs' / 'test_simple.yaml').exists()
    assert (tmp_path / 'test_exp' / 'example_configs' / 'decon_example.yaml').exists()
    
def test_init_validates_permissions(tmp_path, monkeypatch):
    """Test init checks write permissions."""
    # This test would need to mock permission errors
    # Implementation depends on OS-specific permission handling
    pass

def test_validate_command_success(tmp_path):
    """Test validate command on properly initialized experiment."""
    # First init
    runner = CliRunner()
    result = runner.invoke(cli, [
        '--base-path', str(tmp_path),
        '--experiment', 'test_exp',
        'init'
    ])
    assert result.exit_code == 0
    
    # Then validate
    result = runner.invoke(cli, [
        '--base-path', str(tmp_path),
        '--experiment', 'test_exp',
        'validate'
    ])
    
    assert result.exit_code == 0
    assert '✅ All checks passed!' in result.output

def test_validate_command_missing_dirs(tmp_path):
    """Test validate command detects missing directories."""
    # Create partial structure
    exp_path = tmp_path / 'test_exp'
    exp_path.mkdir(parents=True)
    (exp_path / 'jobs').mkdir()
    # Missing other directories
    
    runner = CliRunner()
    result = runner.invoke(cli, [
        '--base-path', str(tmp_path),
        '--experiment', 'test_exp',
        'validate'
    ])
    
    assert result.exit_code == 0
    assert '❌ Validation failed' in result.output
    assert 'Missing directory' in result.output

def test_init_then_submit(tmp_path):
    """Test full workflow from init to job submission."""
    runner = CliRunner()
    
    # Init with examples
    result = runner.invoke(cli, [
        '--base-path', str(tmp_path),
        '--experiment', 'test_exp',
        'init',
        '--with-examples'
    ])
    assert result.exit_code == 0
    
    # Submit job using example config
    result = runner.invoke(cli, [
        '--base-path', str(tmp_path),
        '--experiment', 'test_exp',
        'submit',
        str(tmp_path / 'test_exp' / 'example_configs' / 'test_simple.yaml')
    ])
    assert result.exit_code == 0
    assert 'Created job' in result.output
```

## Common Testing Mistakes to Avoid

### ❌ Bad: Modifying Tests to Pass
```python
# WRONG - Don't change expected values
def test_calculation():
    result = calculate_something()
    assert result == 42  # Changed from 100 to match buggy output
```

### ✅ Good: Fix Implementation
```python
# RIGHT - Keep test, fix the code
def test_calculation():
    result = calculate_something()
    assert result == 100  # Original expectation preserved
```

### ❌ Bad: Catching Exceptions to Pass
```python
# WRONG - Don't hide failures
def test_file_operations():
    try:
        result = read_file("data.txt")
        assert result is not None
    except FileNotFoundError:
        pass  # Test passes even though it shouldn't
```

### ✅ Good: Test Expected Behavior
```python
# RIGHT - Be explicit about expectations
def test_file_operations():
    # Setup: ensure file exists
    Path("data.txt").write_text("content")
    
    result = read_file("data.txt")
    assert result == "content"

def test_file_not_found():
    """Test behavior when file doesn't exist."""
    with pytest.raises(FileNotFoundError):
        read_file("missing.txt")
```

## Test Maintenance

1. **Update tests when requirements change** (with clear commits explaining why)
2. **Remove obsolete tests** (don't just skip them)
3. **Keep tests fast** (<1 second per unit test)
4. **Use marks for slow tests**: `@pytest.mark.slow`
5. **Document flaky tests** and fix the flakiness

## Remember

Tests are the living specification of the system. They define what the code SHOULD do. When tests fail, fix the code to match the test's expectations, not the other way around.