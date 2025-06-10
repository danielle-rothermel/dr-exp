# Step 0: Clean Slate Preparation

## Goal
Remove all existing complex implementations to prepare for the new single-mode JobDB architecture.

## Prerequisites
- Git repository with existing dr_exp codebase
- Backup of any important work (if needed)
- Understanding that this is a breaking change - old code will be deleted

## Overview

This step performs a comprehensive cleanup of the existing multi-mode JobDB architecture to make way for a simpler, file-based implementation with optional Supabase sync.

### What Gets Removed
1. **All JobDB implementations** (`src/dr_exp/job_db/`)
   - Abstract base class (`base_job_db.py`)
   - Local file implementation (`local_job_db.py`) 
   - Supabase implementation (`supabase_job_db.py`)
   - Configuration classes (`jobdb_config.py`)

2. **Factory patterns and mode configuration**
   - `src/dr_exp/utils/factory.py`
   - `src/dr_exp/utils/jobdb_factory.py`
   - `src/dr_exp/utils/cli_config.py`

3. **Old manager/worker system** (`src/dr_exp/manage/`)
   - Complex manager implementation
   - Process manager
   - Old worker implementation

4. **Complex CLI system** (`src/dr_exp/cli/`)
   - Command registry pattern
   - Command groups
   - All subcommands

5. **Mode-specific scripts**
   - `scripts/run_worker.py`
   - `scripts/run_manager.py`
   - `scripts/upload_configs.py`
   - `scripts/reset_local_jobdb.py`

### What Gets Created
- `src/dr_exp/core/` - For the new single JobDB implementation
- `src/dr_exp/sync/` - For Supabase sync functionality
- `src/dr_exp/worker/` - For the new simplified worker
- `tests/implementation/` - For step-by-step implementation tests

### What Stays
- `src/dr_exp/api/` - FastAPI implementation (for Phase 4)
- `src/dr_exp/logging/` - StructuredLogger and utilities
- `src/dr_exp/training/` - Training functions
- `src/dr_exp/utils/` - General utilities (excluding factory patterns)
- Various maintenance and utility scripts

## Key Actions
1. Create new branch: `architecture-redesign`
2. Delete all directories and files listed above
3. Create new directory structure with empty `__init__.py` files
4. Verify pytest, mypy, and ruff are installed
5. Run validation test to ensure cleanup is complete
6. Commit the changes with a clear breaking change message

## Validation

A pytest test (`tests/implementation/test_step_0_cleanup.py`) validates:
- Old directories are removed
- Old files are removed  
- New directories are created with `__init__.py` files
- Important directories (api, logging, training, utils) are preserved

Run: `pt tests/implementation/test_step_0_cleanup.py -v`

## Common Mistakes to Avoid
- Skipping branch creation - always work on a feature branch
- Trying to preserve parts of the old implementation
- Deleting too much (api/, logging/, training/, utils/)
- Forgetting to create the new directory structure
- Proceeding if validation fails

## Why This is Necessary

The existing codebase supports multiple JobDB implementations through inheritance and factory patterns. The new architecture uses a single JobDB class that always writes to files and optionally syncs to Supabase. Keeping the old code would:
- Confuse implementation agents
- Cause import conflicts  
- Maintain complexity we're trying to remove

## Completion Criteria
✅ All old implementations deleted  
✅ New directory structure created  
✅ Validation test passes  
✅ Code quality checks pass (`ckdr`)  
✅ Changes committed to feature branch

## Implementation Notes

### Divergences from Instructions
**Minor Issue Found**: The cleanup left empty directories `src/dr_exp/job_db/` and `src/dr_exp/manage/` that should have been removed. Also `src/dr_exp/cli/commands/` subdirectory wasn't cleaned.
- **Type**: Negative (incomplete cleanup)
- **Impact**: Caused test failure until manually removed
- **Resolution**: Directories were manually removed after discovery

### Implementation Quality Notes
- The validation test was well-structured and caught the incomplete cleanup
- Clean separation between what to keep and what to remove
- Good use of pytest for validation rather than just shell commands

### Lessons Learned
1. When removing directories with `rm -rf`, verify parent directories are also removed if empty
2. Validation tests are crucial for catching incomplete operations
3. Clear documentation of what stays vs. what goes helps prevent over-deletion

### Dependencies for Later Steps
- Creates `src/dr_exp/core/` where JobDB will live (Step 1.1)
- Creates `src/dr_exp/worker/` for Worker implementation (Step 2.1)  
- Creates `src/dr_exp/sync/` for sync queue (Step 2.2)
- Preserves `src/dr_exp/logging/` needed for StructuredLogger integration

### Technical Decisions
1. **Complete removal approach**: Rather than trying to refactor existing code, complete removal ensures no confusion
2. **Separate test directory**: `tests/implementation/` keeps new implementation tests isolated
3. **Preserve utility structure**: Keeping `utils/` directory even though some files were removed

### Testing Insights
- The validation test pattern (checking both removals and creations) proved very effective
- Using `os.path.exists()` rather than trying to import modules was the right approach
- Testing for `__init__.py` files ensures proper Python package structure

### Performance Considerations
- No performance impact - this is purely structural cleanup
- Removing complex inheritance hierarchies will improve import times

### Future Enhancement Opportunities
- Could add a cleanup script that verifies and removes all empty directories
- Might benefit from a "pre-flight check" that lists what will be deleted

### Cross-Step Patterns
This establishes the pattern of:
1. Clear goals and scope
2. Validation through pytest
3. Clean git commits with breaking change notices
4. Quality checks with `ckdr`

### Risk Areas
- Accidental deletion of needed files (mitigated by keeping clear lists)
- Import errors in remaining code that depended on deleted modules
- Empty directories causing subtle issues (as discovered)

## Next Step
Proceed to Step 1.1: Basic JobDB Structure

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