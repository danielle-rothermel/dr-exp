# Prompt for Updating Step Guides to Use Pytest

## Task Summary
Update all implementation step guide files to use pytest instead of standalone test scripts. This is a mechanical change that follows a consistent pattern.

## Required Reading
1. First read: `docs/implementation_guides/impl_steps/UPDATE_STEPS_TO_PYTEST.md`
2. Then read: `docs/implementation_guides/impl_steps/STEP_EXECUTION_CONTEXT.md` (Section: Technical Standards > Testing Framework)

## Files to Update
Update all step guide files in `docs/implementation_guides/impl_steps/`:
- step_1_1_basic_jobdb.md
- step_1_2_concurrent_claiming.md
- step_1_3_job_lifecycle.md
- step_1_4_operational_features.md
- step_2_1_basic_worker.md
- step_2_2_sync_queue.md
- step_2_3_worker_threading.md
- step_2_4_cli_framework.md
- step_2_5_job_management_commands.md
- step_2_6_training_integration.md
- step_2_7_multi_worker_launcher.md
- step_2_8_config_sweeps.md
- step_2_9_slurm_integration.md
- step_3_1_database_schema.md
- step_3_2_supabase_client.md
- step_3_3_database_operations.md
- step_3_4_worker_sync_integration.md
- step_3_5_remote_read_operations.md

## Changes to Make in Each File

### 1. Find the Test File Creation Section
Look for a section like "### 3. Create test_step_X_X.py" (the number might vary)

Change the heading from:
```
### 3. Create test_step_X_X.py
```
To:
```
### 3. Create tests/implementation/test_step_X_X.py
```

### 2. Update the Test Code
In the Python code block after that heading:

a) Add `import pytest` after other imports (if not already present)

b) Remove ALL lines that say:
   - `print("✓ [anything]")`
   - `print("✅ [anything]")`
   - `print("\n✓ [anything]")`
   - Any other print statements showing test results

c) Remove the ENTIRE `if __name__ == "__main__":` block at the end, including:
   - The `if __name__ == "__main__":` line
   - All the function calls under it
   - Any print statements under it

### 3. Update the Validation Section
Find the "## Validation" section and replace:

Note: The validation section might have various comments before `ckdr` like "Run code quality checks" or "Code quality check". Standardize this to the comment shown below.

OLD:
```bash
# Run the test
uvrp test_step_X_X.py

# Expected output:
[various ✓ messages]

# Verify code quality
ckdr
```

NEW:
```bash
# Run the test with pytest
pt tests/implementation/test_step_X_X.py -v

# Expected output:
# ============================= test session starts ==============================
# tests/implementation/test_step_X_X.py::test_[function_name_1] PASSED
# tests/implementation/test_step_X_X.py::test_[function_name_2] PASSED
# [more test functions as appropriate]
# ============================== N passed in X.XXs ===============================

# Verify code quality (runs ruff linting/formatting + mypy type checks)
ckdr

# Expected: All checks passed!
```

Replace `[function_name_1]`, `[function_name_2]` etc. with the actual test function names from the test file.
Replace `N` with the actual number of test functions.

### 4. Special Cases

Some files might have additional test run instructions like:
```bash
# Create proper test file in tests directory
mkdir -p tests/core
cp test_step_1_*.py tests/core/
```

Remove these lines - we're using `tests/implementation/` for all tests.

## Example

Here's a before/after example for clarity:

**BEFORE:**
```python
### 3. Create test_step_1_1.py
```python
"""Test basic JobDB functionality."""
import tempfile

def test_something():
    """Test something."""
    # test code
    print("✓ Test passed!")

if __name__ == "__main__":
    test_something()
    print("\n✓ All tests passed!")
```

**AFTER:**
```python
### 3. Create tests/implementation/test_step_1_1.py
```python
"""Test basic JobDB functionality."""
import tempfile
import pytest

def test_something():
    """Test something."""
    # test code
```

## Validation of Your Work

After updating all files, verify your changes by checking:
1. No `print("✓")` statements remain in test code
2. No `if __name__ == "__main__":` blocks remain
3. All test files are now in `tests/implementation/`
4. All validation sections use `pt` command instead of `uvrp`
5. All validation sections show pytest-style output

## Important Notes
- Keep all the actual test logic unchanged - only remove prints and main blocks
- Keep all imports except add `import pytest` if missing
- Keep all docstrings
- Keep all test function names the same
- The test code itself should work exactly the same under pytest