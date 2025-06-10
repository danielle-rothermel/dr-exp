# Step Execution Context

This document provides essential context for agents executing individual implementation steps. Read this before executing any step.

## Core Architecture Principles

1. **Single JobDB Implementation**: One JobDB class that always writes to filesystem, no modes or variants
2. **Filesystem is Truth**: All data is written to `/scratch` first, Supabase is only a read-only mirror
3. **File Locking for Concurrency**: Use `fcntl` for atomic operations, no distributed coordination
4. **Hydra Dispatch**: Jobs use `_target_` field for function routing, no hardcoded dispatch
5. **Fail Fast**: Use assertions for validation, not exceptions

## Directory Structure

All experiments follow this structure:
```
{base_path}/{experiment_name}/
├── jobs/         # Job JSON files (job_id.json)
├── storage/      # Job artifacts (run_{job_id}/)
├── sync_queue/   # Pending uploads
├── logs/         # Operational logs
├── control/      # Control files for commands
└── .jobdb        # JobDB metadata file
```

## Technical Standards

### Testing Framework
- **Use pytest** for all tests (NOT standalone scripts)
- Tests go in `tests/implementation/` directory
- Test files named `test_step_X_X.py`
- Run with `pt tests/implementation/test_step_X_X.py -v`
- No `if __name__ == "__main__"` blocks in tests
- No print statements for test results (pytest handles output)

### Type Safety (mypy)
- ALL functions must have type hints
- Use concrete types, not Any
- If mypy complains, fix the code not the type
- Run type checking with `mypy` (included in `ckdr`)

### Code Style (ruff)
- Follow ruff's formatting rules
- Fix all linting issues
- No `# noqa` comments to disable checks
- Run formatting with `ruff format` (included in `ckdr`)

### Validation
- Use assertions for preconditions
- Fail immediately on invalid inputs
- No fallback values or error recovery

### Code Quality
- Must pass `ckdr` (runs both ruff and mypy)
- Must pass all tests with `pt` (pytest)
- No skipping tests or disabling checks

## Key Implementation Rules

### For JobDB (Phase 1)
- Single class, no inheritance
- Direct file operations, no abstraction layers
- Experiment initialization with validate parameter
- All times use `datetime.now(UTC)`

### For Workers (Phase 2)
- Workers are independent processes
- Each worker has unique ID
- Background threads for sync and heartbeat
- Graceful shutdown on SIGTERM

### For CLI (Phase 2)
- Commands follow pattern: `dr_exp --base-path X --experiment Y command`
- All paths are explicit, no defaults
- Direct integration with JobDB

### For Supabase (Phase 3)
- Optional sync, not required for operation
- One-way sync (local → remote)
- Checksums for deduplication
- Network errors don't stop workers

## Common Mistakes to Avoid

1. **DO NOT** create abstract base classes or interfaces
2. **DO NOT** add configuration files or modes
3. **DO NOT** use exceptions for validation - use assertions
4. **DO NOT** modify tests to pass - fix the implementation
5. **DO NOT** add error recovery or fallback logic
6. **DO NOT** import modules that don't exist yet

## Import Organization

When adding imports:
1. Place with existing imports at top of file
2. Group by: stdlib, third-party, local
3. Never import in middle of file
4. Use absolute imports from `dr_exp`

## Testing Requirements

Every implementation must:
1. Include test file following the step guide
2. Pass ALL tests without modification
3. Follow test patterns from examples
4. Test both success and failure cases

## File Creation Rules

1. Create directories with `parents=True`
2. Use `Path` from pathlib, not string manipulation
3. Always specify encoding when opening files
4. Close files properly or use context managers

## Remember

- The step guides are complete - follow them exactly
- Don't add features not specified
- Keep implementations simple and direct
- When in doubt, choose the simpler approach