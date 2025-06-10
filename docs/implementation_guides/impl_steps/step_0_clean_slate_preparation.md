# Step 0: Clean Slate Preparation

## Goal (1 sentence)
Remove all existing complex implementations to prepare for the new single-mode JobDB architecture.

## Prerequisites
- [ ] Git repository with existing dr_exp codebase
- [ ] Backup of any important work (if needed)
- [ ] Understanding that this is a breaking change - old code will be deleted

## Implementation

### 1. Create new branch for architecture redesign
```bash
# Create and switch to new branch
git checkout -b architecture-redesign

# Push branch to remote
git push -u origin architecture-redesign

# Verify you're on the correct branch
git branch --show-current
# Expected output: architecture-redesign
```

### 2. Delete all complex JobDB implementations
```bash
# Remove entire job_db directory with all its implementations
rm -rf src/dr_exp/job_db/

# This removes:
# - base_job_db.py (abstract interface)
# - local_job_db.py (JSON file implementation)
# - supabase_job_db.py (database implementation)
# - jobdb_config.py (configuration classes)
# - __init__.py
```

### 3. Delete factory patterns and complex configuration
```bash
# Remove factory implementations
rm -f src/dr_exp/utils/factory.py
rm -f src/dr_exp/utils/jobdb_factory.py
rm -f src/dr_exp/utils/cli_config.py

# These files implemented the multi-mode pattern we're removing
```

### 4. Delete old manager and worker implementations
```bash
# Remove entire manage directory
rm -rf src/dr_exp/manage/

# This removes:
# - manager.py
# - process_manager.py
# - worker.py
# - __init__.py
```

### 5. Delete complex CLI system
```bash
# Remove entire CLI directory
rm -rf src/dr_exp/cli/

# This removes:
# - main.py
# - base_command.py
# - command_groups.py
# - registry.py
# - commands/ directory with all subcommands
# - __init__.py
```

### 6. Delete mode-specific scripts
```bash
# Remove scripts tied to old architecture
rm -f scripts/run_worker.py
rm -f scripts/run_manager.py
rm -f scripts/upload_configs.py
rm -f scripts/reset_local_jobdb.py

# Keep these scripts (they're still useful):
# - scripts/manager_cli.py (will be updated later)
# - scripts/run_decon_worker.py (specific to decon)
# - scripts/start_backend.py (API server)
# - scripts/test_supabase.py (connection testing)
# - scripts/cleanup_run_data.py (storage cleanup)
# - scripts/reap_stale_jobs.py (maintenance)
```

### 7. Create new directory structure
```bash
# Create directories for new implementation
mkdir -p src/dr_exp/core/
mkdir -p src/dr_exp/sync/
mkdir -p src/dr_exp/worker/

# Create empty __init__.py files
touch src/dr_exp/core/__init__.py
touch src/dr_exp/sync/__init__.py
touch src/dr_exp/worker/__init__.py

# Create test directory structure for implementation tests
mkdir -p tests/implementation/
touch tests/implementation/__init__.py
```

### 8. Ensure testing tools are installed
```bash
# Verify pytest, mypy, and ruff are available
uv pip list | grep -E "pytest|mypy|ruff"

# If any are missing, install them
uv add --dev pytest pytest-cov pytest-xdist
uv add --dev mypy
uv add --dev ruff

# Verify the ckdr alias works (should run ruff + mypy)
ckdr

# Verify the pt alias works (should run pytest)
pt --version
```

### 9. Verify cleanup was successful
```bash
# These commands should return no results:
ls src/dr_exp/job_db/ 2>/dev/null
# Expected: No such file or directory

ls src/dr_exp/manage/ 2>/dev/null
# Expected: No such file or directory

ls src/dr_exp/cli/ 2>/dev/null
# Expected: No such file or directory

# These files should not exist:
ls src/dr_exp/utils/factory.py 2>/dev/null
# Expected: No such file or directory

ls src/dr_exp/utils/jobdb_factory.py 2>/dev/null
# Expected: No such file or directory

# These directories should exist and be empty:
ls src/dr_exp/core/
# Expected: __init__.py (empty file)

ls src/dr_exp/sync/
# Expected: __init__.py (empty file)

ls src/dr_exp/worker/
# Expected: __init__.py (empty file)
```

### 10. Check what remains
```bash
# View remaining structure
find src/dr_exp -type f -name "*.py" | grep -v __pycache__ | sort

# Should show only:
# - src/dr_exp/__init__.py
# - src/dr_exp/py.typed
# - src/dr_exp/api/* (keep API for later phases)
# - src/dr_exp/logging/* (keep logging utilities)
# - src/dr_exp/training/* (keep training modules)
# - src/dr_exp/utils/* (keep some utilities, deleted others)
# - src/dr_exp/core/__init__.py (new, empty)
# - src/dr_exp/sync/__init__.py (new, empty)
# - src/dr_exp/worker/__init__.py (new, empty)
```

### 11. Commit the cleanup
```bash
# Stage all deletions
git add -A

# Review what will be committed
git status

# Commit with clear message
git commit -m "feat: remove all multi-mode JobDB implementations

- Delete job_db/ directory with all mode-specific implementations
- Delete manage/ directory with old worker/manager code  
- Delete cli/ directory to rebuild from scratch
- Delete factory patterns and mode configuration
- Delete mode-specific scripts
- Create new directory structure for single-mode implementation

BREAKING CHANGE: This removes all existing JobDB functionality.
The system will be rebuilt with a simpler architecture."
```

## Validation
```bash
# Create pytest validation test
cat > tests/implementation/test_step_0_cleanup.py << 'EOF'
"""Test that Step 0 cleanup was successful."""
import os
import pytest
from pathlib import Path


def test_old_directories_removed():
    """Verify old directories have been deleted."""
    old_dirs = [
        "src/dr_exp/job_db",
        "src/dr_exp/manage", 
        "src/dr_exp/cli"
    ]
    
    for dir_path in old_dirs:
        assert not os.path.exists(dir_path), f"Directory should be deleted: {dir_path}"


def test_old_files_removed():
    """Verify old files have been deleted."""
    old_files = [
        "src/dr_exp/utils/factory.py",
        "src/dr_exp/utils/jobdb_factory.py",
        "src/dr_exp/utils/cli_config.py",
        "scripts/run_worker.py",
        "scripts/run_manager.py",
        "scripts/upload_configs.py",
        "scripts/reset_local_jobdb.py"
    ]
    
    for file_path in old_files:
        assert not os.path.exists(file_path), f"File should be deleted: {file_path}"


def test_new_directories_created():
    """Verify new directories exist with __init__.py files."""
    new_dirs = [
        "src/dr_exp/core",
        "src/dr_exp/sync",
        "src/dr_exp/worker",
        "tests/implementation"
    ]
    
    for dir_path in new_dirs:
        assert os.path.exists(dir_path), f"Directory should exist: {dir_path}"
        init_file = os.path.join(dir_path, "__init__.py")
        assert os.path.exists(init_file), f"Missing __init__.py in: {dir_path}"


def test_remaining_structure():
    """Verify important directories were kept."""
    kept_dirs = [
        "src/dr_exp/api",
        "src/dr_exp/logging",
        "src/dr_exp/training",
        "src/dr_exp/utils"
    ]
    
    for dir_path in kept_dirs:
        assert os.path.exists(dir_path), f"Directory should still exist: {dir_path}"
EOF

# Run validation with pytest
pt tests/implementation/test_step_0_cleanup.py -v

# Expected output:
# ============================= test session starts ==============================
# tests/implementation/test_step_0_cleanup.py::test_old_directories_removed PASSED
# tests/implementation/test_step_0_cleanup.py::test_old_files_removed PASSED
# tests/implementation/test_step_0_cleanup.py::test_new_directories_created PASSED
# tests/implementation/test_step_0_cleanup.py::test_remaining_structure PASSED
# ============================== 4 passed in 0.XXs ===============================

# Also run code quality checks
ckdr

# Expected: All checks passed!
```

## Common Mistakes
- DO NOT: Skip the branch creation - work on a feature branch
- DO NOT: Try to preserve parts of the old implementation - remove it all
- DO NOT: Delete the api/, logging/, training/, or utils/ directories entirely
- DO NOT: Forget to create the new directory structure
- DO NOT: Proceed to Step 1.1 if validation fails

## Important Notes

### What We're Keeping
- `src/dr_exp/api/` - FastAPI implementation (Phase 4)
- `src/dr_exp/logging/` - StructuredLogger and utilities
- `src/dr_exp/training/` - Training functions (decon, dummy)
- `src/dr_exp/utils/` - Some utilities (but not factory/config ones)
- `tests/` - All tests (will be updated as we go)
- `configs/` - Hydra configuration files
- `scripts/` - Some scripts (API, cleanup, Supabase utilities)

### What We're Removing
- All JobDB implementations (base, local, supabase)
- All manager/worker code (will rebuild simpler)
- All CLI code (will rebuild simpler)
- Factory patterns and mode configuration
- Mode-specific scripts

### Why This is Necessary
The existing codebase has multiple implementations of JobDB (LocalJobDB, SupabaseJobDB) that inherit from BaseJobDB. The new architecture uses a single JobDB class that always writes to files and optionally syncs to Supabase. Keeping the old code would:
1. Confuse implementation agents
2. Cause import conflicts
3. Maintain complexity we're trying to remove

## Next Step
Proceed to Step 1.1: Basic JobDB Structure