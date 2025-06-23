# Task: Review and Update Future Implementation Step Instructions

## Context
You are reviewing implementation guide documentation for a refactored ML experiment management system. Steps 0 through 3.2 have been completed and their documentation has been updated with retrospective analysis. Your task is to review the remaining step instruction files (Steps 3.3 onward) and update them based on patterns and lessons learned from the completed steps.

## Completed Steps Reference
The following steps have been implemented and analyzed:
- Step 0: Clean Slate Preparation
- Step 1.1: Basic JobDB
- Step 1.2: Concurrent Job Claiming
- Step 1.3: Job Lifecycle Management
- Step 1.4: Operational Features
- Step 2.1: Basic Worker Class
- Step 2.2: Sync Queue Implementation
- Step 2.3: Worker Threading Integration
- Step 2.4: CLI Framework
- Step 2.5: Job Management Commands
- Step 2.6: Training Integration
- Step 2.7: Multi-Worker Launcher
- Step 2.8: Config Sweeps
- Step 2.9: SLURM Integration
- Step 3.1: Database Schema
- Step 3.2: Supabase Client Basics

## Key Patterns to Fix

### 1. Datetime Usage
- **Issue**: Instructions use deprecated `datetime.utcnow()`
- **Fix**: Replace all instances with `datetime.now(UTC)`
- **Import**: Ensure `from datetime import datetime, UTC` is used

### 2. Field Naming Consistency
- **Issue**: Inconsistent field names between steps
- **Fix**: Use these standard field names:
  - `worker_id` (not `assigned_worker`)
  - `last_heartbeat` (not `heartbeat`)
  - `created_at`, `started_at`, `completed_at` for timestamps

### 3. JobDB Initialization
- **Pattern**: Tests use `JobDB(..., validate=False)` to skip validation
- **Update**: Include this pattern in test examples where appropriate

### 4. Import Statements
- **Issue**: Some test files missing required imports
- **Fix**: Ensure all test files include necessary imports (e.g., `import json` when using json operations)

### 5. CLI Context Pattern
- **Pattern**: Don't store JobDB in Click context
- **Update**: Each CLI command should create its own JobDB instance

## Improvements Based on Lessons Learned

### 1. Type Annotations
- Add complete type hints to all function signatures
- Use `from typing import Dict, Any, Optional, List` etc.

### 2. Error Handling
- Use specific exception types where possible
- Include full tracebacks in error files
- Don't catch exceptions too broadly

### 3. Test Design
- Use deterministic tests (avoid timing dependencies where possible)
- Include both success and failure scenarios
- Test edge cases explicitly

### 4. File Operations
- Always use `Path` from pathlib instead of string manipulation
- Ensure parent directories exist with `mkdir(parents=True, exist_ok=True)`
- Use context managers for file operations

### 5. Threading Considerations
- Set `daemon=True` on background threads
- Use `threading.Event` for shutdown coordination
- Include timeout on thread joins

### 6. Configuration
- Validate required fields early (e.g., `_target_` in Hydra configs)
- Use sensible defaults for optional parameters
- Document all configuration options

## Your Task

1. **Read each remaining step file** in `docs/implementation_guides/impl_steps/`
2. **Apply the fixes** listed above to code examples
3. **Incorporate improvements** based on lessons learned
4. **Maintain consistency** with patterns established in completed steps
5. **Preserve the intent** of each step while improving quality

## Specific Instructions

For each step file you update:
1. Fix all datetime usage to use `datetime.now(UTC)`
2. Ensure field naming is consistent across all code examples
3. Add missing imports to test files
4. Add type annotations to function signatures
5. Apply other improvements as relevant
6. Keep the overall structure and goals of each step unchanged
7. Don't change the fundamental architecture or approach

## Example Transform

### Before:
```python
def heartbeat(self, job_id: str):
    """Send heartbeat."""
    return self.update_job(job_id, {
        "heartbeat": datetime.utcnow().isoformat()
    })
```

### After:
```python
def heartbeat(self, job_id: str) -> bool:
    """Send heartbeat."""
    return self.update_job(job_id, {
        "last_heartbeat": datetime.now(UTC).isoformat()
    })
```

## Files to Update
Start with `step_3_3_database_operations.md` and continue through all remaining step files in the `impl_steps` directory:
- Step 3.3: Database Operations
- Step 3.4: Worker Sync Integration
- Step 3.5: Remote Read Operations

Remember: The goal is to make the future instructions more accurate and consistent based on what we learned from implementing the first steps, not to fundamentally change the architecture or approach.