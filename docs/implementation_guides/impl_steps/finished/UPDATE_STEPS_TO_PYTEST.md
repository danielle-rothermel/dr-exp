# Updating Step Guides to Use Pytest

This document describes the changes needed to update all step guides from standalone test scripts to proper pytest tests.

## Required Changes for Each Step Guide

### 1. Update Test File Creation Section

**OLD Pattern:**
```python
### 3. Create test_step_X_X.py
```python
"""Test description."""
import tempfile
from src.dr_exp... import ...

def test_something():
    """Test something."""
    # test code
    assert something
    print("✓ Test passed!")

if __name__ == "__main__":
    test_something()
```

**NEW Pattern:**
```python
### 3. Create tests/implementation/test_step_X_X.py
```python
"""Test description."""
import tempfile
import pytest
from pathlib import Path

from src.dr_exp... import ...


def test_something():
    """Test something."""
    # test code
    assert something
    # NO print statements - pytest handles output


def test_another_thing():
    """Test another thing."""
    # test code
    assert another_thing


# NO if __name__ == "__main__" block!
```

### 2. Update Validation Section

**OLD Pattern:**
```bash
# Run the test
uvrp test_step_X_X.py

# Expected output:
✓ Test passed!
✓ All tests passed!

# Verify code quality
ckdr
```

**NEW Pattern:**
```bash
# Run the test with pytest
pt tests/implementation/test_step_X_X.py -v

# Expected output:
# ============================= test session starts ==============================
# tests/implementation/test_step_X_X.py::test_something PASSED
# tests/implementation/test_step_X_X.py::test_another_thing PASSED
# ============================== N passed in X.XXs ===============================

# Verify code quality
ckdr

# Expected: All checks passed!
```

### 3. Key Changes to Make

1. **Move test file location**: `test_step_X_X.py` → `tests/implementation/test_step_X_X.py`
2. **Remove print statements**: No `print("✓ Test passed!")`
3. **Remove main block**: No `if __name__ == "__main__":`
4. **Add pytest import**: Include `import pytest` at top
5. **Use pytest features**: Can now use fixtures, parametrize, etc.
6. **Update run command**: `uvrp test_step_X_X.py` → `pt tests/implementation/test_step_X_X.py -v`

### 4. Example Conversion

Let's convert a test from Step 1.1:

**Before:**
```python
def test_jobdb_basic():
    """Test creating and retrieving jobs."""
    with tempfile.TemporaryDirectory() as tmpdir:
        job_db = JobDB(base_path=tmpdir, experiment_name="test_exp", validate=False)
        # ... test code ...
        print("✓ All tests passed!")

if __name__ == "__main__":
    test_jobdb_basic()
```

**After:**
```python
def test_jobdb_basic(tmp_path):
    """Test creating and retrieving jobs."""
    job_db = JobDB(base_path=str(tmp_path), experiment_name="test_exp", validate=False)
    # ... test code ...
    # No print statement!
```

Note: We can use pytest's `tmp_path` fixture instead of `tempfile.TemporaryDirectory()`!

## Steps That Need Updating

- [ ] Step 1.1: Basic JobDB Structure
- [ ] Step 1.2: Concurrent Job Claiming  
- [ ] Step 1.3: Job Lifecycle Management
- [ ] Step 1.4: Operational Features
- [ ] Step 2.1: Basic Worker Class
- [ ] Step 2.2: Sync Queue Implementation
- [ ] Step 2.3: Worker Threading Integration
- [ ] Step 2.4: CLI Framework
- [ ] Step 2.5: Job Management Commands
- [ ] Step 2.6: Training Integration
- [ ] Step 2.7: Multi-Worker Launcher
- [ ] Step 2.8: Config Sweeps
- [ ] Step 2.9: SLURM Integration
- [ ] Step 3.1: Database Schema
- [ ] Step 3.2: Supabase Client Basics
- [ ] Step 3.3: Database Operations
- [ ] Step 3.4: Worker Sync Integration
- [ ] Step 3.5: Remote Read Operations

## Additional Benefits of Using Pytest

1. **Better test discovery**: `pt` will find all tests automatically
2. **Fixtures**: Use `tmp_path`, `monkeypatch`, etc.
3. **Parametrization**: Test multiple cases with one function
4. **Better output**: Clear pass/fail reporting
5. **Coverage**: Can run with `--cov` flag
6. **Parallel execution**: Use `-n auto` for faster runs
7. **Markers**: Skip tests conditionally with `@pytest.mark.skipif`

## Running All Implementation Tests

After conversion, agents can run all implementation tests with:
```bash
# Run all implementation tests
pt tests/implementation/ -v

# Run with coverage
pt tests/implementation/ --cov=src/dr_exp

# Run in parallel
pt tests/implementation/ -n auto
```