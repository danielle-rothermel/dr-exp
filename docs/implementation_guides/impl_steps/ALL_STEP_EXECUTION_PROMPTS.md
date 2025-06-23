# Execution Prompts for All Implementation Steps

## Step 0: Clean Slate Preparation

Please implement Step 0: Clean Slate Preparation by:

1. First reading: docs/implementation_guides/impl_steps/STEP_EXECUTION_CONTEXT.md
2. Then reading: docs/implementation_guides/impl_steps/step_0_clean_slate_preparation.md
3. Following the implementation guide exactly as written
4. Running all validation commands before considering the task complete

Critical Requirements:
- Create the new branch FIRST before deleting anything
- Execute ALL deletions exactly as specified
- Create ALL new directories including tests/implementation/
- Ensure the pytest validation shows 4 tests passing
- Ensure ckdr shows "All checks passed!"

Do NOT:
- Skip the branch creation
- Keep any files that should be deleted
- Modify tests if they fail
- Proceed if any validation fails

Report any issues rather than making assumptions.

---

## Step 1.1: Basic JobDB Structure

Please implement Step 1.1: Basic JobDB Structure by:

1. First reading: docs/implementation_guides/impl_steps/STEP_EXECUTION_CONTEXT.md
2. Then reading: docs/implementation_guides/impl_steps/step_1_1_basic_jobdb.md
3. Following the implementation guide exactly as written
4. Running all validation commands before considering the task complete

Critical Requirements:
- Create src/dr_exp/core/__init__.py if it doesn't exist
- Implement ALL methods shown in the JobDB class
- Include the validate parameter in __init__
- Use datetime.now(UTC) for timestamps
- Create the test file in tests/implementation/
- Ensure pytest shows all tests passing
- Ensure ckdr shows "All checks passed!"

Do NOT:
- Add features not in the specification
- Use datetime.utcnow() - use datetime.now(UTC)
- Create abstract base classes
- Modify tests if they fail
- Proceed if any validation fails

Report any issues rather than making assumptions.

---

## Step 1.2: Concurrent Job Claiming

Please implement Step 1.2: Concurrent Job Claiming by:

1. First reading: docs/implementation_guides/impl_steps/STEP_EXECUTION_CONTEXT.md
2. Then reading: docs/implementation_guides/impl_steps/step_1_2_concurrent_claiming.md
3. Following the implementation guide exactly as written
4. Running all validation commands before considering the task complete

Critical Requirements:
- Import fcntl for file locking
- Update claim_next_job with atomic file locking
- Implement the exact locking pattern shown
- Add update_job method if not already present
- Ensure concurrent test demonstrates no conflicts
- Ensure pytest shows all tests passing
- Ensure ckdr shows "All checks passed!"

Do NOT:
- Use a different locking mechanism
- Add complex coordination logic
- Modify the locking pattern
- Skip the concurrent test
- Proceed if any validation fails

Report any issues rather than making assumptions.

---

## Step 1.3: Job Lifecycle Management

Please implement Step 1.3: Job Lifecycle Management by:

1. First reading: docs/implementation_guides/impl_steps/STEP_EXECUTION_CONTEXT.md
2. Then reading: docs/implementation_guides/impl_steps/step_1_3_job_lifecycle.md
3. Following the implementation guide exactly as written
4. Running all validation commands before considering the task complete

Critical Requirements:
- Add ALL lifecycle methods (complete_job, fail_job, heartbeat)
- Add sync queue methods (add_to_sync_queue, get_sync_queue)
- Add get_experiment_info method
- Ensure heartbeats update last_heartbeat field
- Ensure pytest shows all tests passing
- Ensure ckdr shows "All checks passed!"

Do NOT:
- Skip any methods
- Change method signatures
- Add extra features
- Modify tests if they fail
- Proceed if any validation fails

Report any issues rather than making assumptions.

---

## Step 1.4: Operational Features

Please implement Step 1.4: Operational Features by:

1. First reading: docs/implementation_guides/impl_steps/STEP_EXECUTION_CONTEXT.md
2. Then reading: docs/implementation_guides/impl_steps/step_1_4_operational_features.md
3. Following the implementation guide exactly as written
4. Running all validation commands before considering the task complete

Critical Requirements:
- Add mark_job_failed (NOT kill_job)
- Add recover_stale_jobs with heartbeat timeout
- Add boost_priority that takes a LIST of job IDs
- Use the exact method signatures shown
- Ensure pytest shows all tests passing
- Ensure ckdr shows "All checks passed!"

Do NOT:
- Add reservation system features
- Use different method names
- Change the method signatures
- Add extra features not specified
- Proceed if any validation fails

Phase 1 Complete! After this step, run: `pt tests/implementation/test_step_1_*.py -v`

Report any issues rather than making assumptions.

---

## Step 2.1: Basic Worker Class

Please implement Step 2.1: Basic Worker Class by:

1. First reading: docs/implementation_guides/impl_steps/STEP_EXECUTION_CONTEXT.md
2. Then reading: docs/implementation_guides/impl_steps/step_2_1_basic_worker.md
3. Following the implementation guide exactly as written
4. Running all validation commands before considering the task complete

Critical Requirements:
- Create src/dr_exp/worker/__init__.py if needed
- Implement Worker class with exact __init__ signature
- Use hydra.utils.call for job execution
- Implement graceful shutdown on SIGTERM
- Inject job metadata into config
- Ensure pytest shows all tests passing
- Ensure ckdr shows "All checks passed!"

Do NOT:
- Add threading yet (that's Step 2.3)
- Implement sync functionality yet
- Create complex error handling
- Modify tests if they fail
- Proceed if any validation fails

Report any issues rather than making assumptions.

---

## Step 2.2: Sync Queue Implementation

Please implement Step 2.2: Sync Queue Implementation by:

1. First reading: docs/implementation_guides/impl_steps/STEP_EXECUTION_CONTEXT.md
2. Then reading: docs/implementation_guides/impl_steps/step_2_2_sync_queue.md
3. Following the implementation guide exactly as written
4. Running all validation commands before considering the task complete

Critical Requirements:
- Create src/dr_exp/sync/__init__.py if needed
- Implement SyncQueue class separately from Worker
- Include retry logic with exponential backoff
- Calculate checksums for deduplication
- Persist queue state to JSON
- Ensure pytest shows all tests passing
- Ensure ckdr shows "All checks passed!"

Do NOT:
- Integrate with Worker yet (that's Step 2.3)
- Actually upload to Supabase (that's Phase 3)
- Skip the retry logic
- Modify tests if they fail
- Proceed if any validation fails

Report any issues rather than making assumptions.

---

## Step 2.3: Worker Threading Integration

Please implement Step 2.3: Worker Threading Integration by:

1. First reading: docs/implementation_guides/impl_steps/STEP_EXECUTION_CONTEXT.md
2. Then reading: docs/implementation_guides/impl_steps/step_2_3_worker_threading.md
3. Following the implementation guide exactly as written
4. Running all validation commands before considering the task complete

Critical Requirements:
- Update Worker class to add background threads
- Add sync thread using SyncQueue
- Add heartbeat thread
- Implement proper thread lifecycle management
- Ensure threads stop on shutdown
- Ensure pytest shows all tests passing
- Ensure ckdr shows "All checks passed!"

Do NOT:
- Change the SyncQueue implementation
- Add more threads than specified
- Skip thread cleanup on shutdown
- Modify tests if they fail
- Proceed if any validation fails

Report any issues rather than making assumptions.

---

## Step 2.4: CLI Framework

Please implement Step 2.4: CLI Framework by:

1. First reading: docs/implementation_guides/impl_steps/STEP_EXECUTION_CONTEXT.md
2. Then reading: docs/implementation_guides/impl_steps/step_2_4_cli_framework.md
3. Following the implementation guide exactly as written
4. Running all validation commands before considering the task complete

Critical Requirements:
- Create src/dr_exp/cli/ directory structure
- Use Click for CLI framework
- Implement base structure with context passing
- Add init and worker commands
- Use the exact command structure shown
- Ensure pytest shows all tests passing
- Ensure ckdr shows "All checks passed!"

Do NOT:
- Add commands not specified
- Use argparse instead of Click
- Skip the context setup
- Modify tests if they fail
- Proceed if any validation fails

Report any issues rather than making assumptions.

---

## Step 2.5: Job Management Commands

Please implement Step 2.5: Job Management Commands by:

1. First reading: docs/implementation_guides/impl_steps/STEP_EXECUTION_CONTEXT.md
2. Then reading: docs/implementation_guides/impl_steps/step_2_5_job_management_commands.md
3. Following the implementation guide exactly as written
4. Running all validation commands before considering the task complete

Critical Requirements:
- Add ALL specified commands to the CLI
- Implement job submission from YAML files
- Add list, kill, boost commands
- Add status and recovery commands
- Ensure all commands work as specified
- Ensure pytest shows all tests passing
- Ensure ckdr shows "All checks passed!"

Do NOT:
- Skip any commands
- Change command names or options
- Add extra features
- Modify tests if they fail
- Proceed if any validation fails

Report any issues rather than making assumptions.

---

## Step 2.6: Training Integration

Please implement Step 2.6: Training Integration by:

1. First reading: docs/implementation_guides/impl_steps/STEP_EXECUTION_CONTEXT.md
2. Then reading: docs/implementation_guides/impl_steps/step_2_6_training_integration.md
3. Following the implementation guide exactly as written
4. Running all validation commands before considering the task complete

Critical Requirements:
- Create dummy_trainer.py exactly as shown
- Integrate StructuredLogger
- Test full job execution pipeline
- Ensure artifacts are created
- Ensure sync queue gets populated
- Ensure pytest shows all tests passing
- Ensure ckdr shows "All checks passed!"

Do NOT:
- Skip the dummy trainer
- Modify StructuredLogger integration
- Add complex training logic
- Modify tests if they fail
- Proceed if any validation fails

Report any issues rather than making assumptions.

---

## Step 2.7: Multi-Worker Launcher

Please implement Step 2.7: Multi-Worker Launcher by:

1. First reading: docs/implementation_guides/impl_steps/STEP_EXECUTION_CONTEXT.md
2. Then reading: docs/implementation_guides/impl_steps/step_2_7_multi_worker_launcher.md
3. Following the implementation guide exactly as written
4. Running all validation commands before considering the task complete

Critical Requirements:
- Create WorkerLauncher class with GPU discovery
- Implement process monitoring and restart
- Add graceful shutdown on SIGTERM
- Create control file support
- Add status file generation
- Ensure pytest shows all tests passing
- Ensure ckdr shows "All checks passed!"

Do NOT:
- Try to manage GPU allocation directly
- Create complex worker coordination
- Skip signal handling
- Modify tests if they fail
- Proceed if any validation fails

Report any issues rather than making assumptions.

---

## Step 2.8: Config Sweeps

Please implement Step 2.8: Config Sweeps by:

1. First reading: docs/implementation_guides/impl_steps/STEP_EXECUTION_CONTEXT.md
2. Then reading: docs/implementation_guides/impl_steps/step_2_8_config_sweeps.md
3. Following the implementation guide exactly as written
4. Running all validation commands before considering the task complete

Critical Requirements:
- Create sweep_utils.py with parameter parsing
- Implement config generation with itertools.product
- Add sweep command to CLI
- Support dry-run mode
- Validate _target_ is importable
- Ensure pytest shows all tests passing
- Ensure ckdr shows "All checks passed!"

Do NOT:
- Use eval() for parameter parsing
- Skip target validation
- Make the format complex
- Modify tests if they fail
- Proceed if any validation fails

Report any issues rather than making assumptions.

---

## Step 2.9: SLURM Integration

Please implement Step 2.9: SLURM Integration by:

1. First reading: docs/implementation_guides/impl_steps/STEP_EXECUTION_CONTEXT.md
2. Then reading: docs/implementation_guides/impl_steps/step_2_9_slurm_integration.md
3. Following the implementation guide exactly as written
4. Running all validation commands before considering the task complete

Critical Requirements:
- Create SLURM batch script with CUDA MPS
- Add SLURM management commands to CLI
- Create helper scripts for batch submission
- Handle SLURM environment variables
- Ensure cleanup on exit
- Ensure pytest shows all tests passing
- Ensure ckdr shows "All checks passed!"

Do NOT:
- Hardcode paths in scripts
- Skip cleanup trap
- Ignore SLURM time limits
- Modify tests if they fail
- Proceed if any validation fails

Phase 2 Complete! After this step, run: `pt tests/implementation/test_step_2_*.py -v`

Report any issues rather than making assumptions.

---

## Step 3.1: Database Schema

Please implement Step 3.1: Database Schema by:

1. First reading: docs/implementation_guides/impl_steps/STEP_EXECUTION_CONTEXT.md
2. Then reading: docs/implementation_guides/impl_steps/step_3_1_database_schema.md
3. Following the implementation guide exactly as written
4. Running all validation commands before considering the task complete

Critical Requirements:
- Create SQL migration files in correct order
- Include all tables, indexes, and RLS policies
- Set up storage bucket configuration
- Use the exact schema shown
- Test against local Supabase
- Ensure pytest shows all tests passing
- Ensure ckdr shows "All checks passed!"

Do NOT:
- Skip any SQL statements
- Change table or column names
- Add extra features
- Modify tests if they fail
- Proceed if any validation fails

Report any issues rather than making assumptions.

---

## Step 3.2: Supabase Client Basics

Please implement Step 3.2: Supabase Client Basics by:

1. First reading: docs/implementation_guides/impl_steps/STEP_EXECUTION_CONTEXT.md
2. Then reading: docs/implementation_guides/impl_steps/step_3_2_supabase_client.md
3. Following the implementation guide exactly as written
4. Running all validation commands before considering the task complete

Critical Requirements:
- Create SupabaseClient class
- Implement file upload with retries
- Calculate checksums correctly
- Handle errors gracefully
- Create test with mocking
- Ensure pytest shows all tests passing
- Ensure ckdr shows "All checks passed!"

Do NOT:
- Actually upload to Supabase in tests
- Skip error handling
- Change the retry logic
- Modify tests if they fail
- Proceed if any validation fails

Report any issues rather than making assumptions.

---

## Step 3.3: Database Operations

Please implement Step 3.3: Database Operations by:

1. First reading: docs/implementation_guides/impl_steps/STEP_EXECUTION_CONTEXT.md
2. Then reading: docs/implementation_guides/impl_steps/step_3_3_database_operations.md
3. Following the implementation guide exactly as written
4. Running all validation commands before considering the task complete

Critical Requirements:
- Add ALL database operation methods
- Implement batch operations
- Handle network errors gracefully
- Ensure experiment isolation
- Test with proper mocking
- Ensure pytest shows all tests passing
- Ensure ckdr shows "All checks passed!"

Do NOT:
- Skip any methods
- Change method signatures
- Remove error handling
- Modify tests if they fail
- Proceed if any validation fails

Report any issues rather than making assumptions.

---

## Step 3.4: Worker Sync Integration

Please implement Step 3.4: Worker Sync Integration by:

1. First reading: docs/implementation_guides/impl_steps/STEP_EXECUTION_CONTEXT.md
2. Then reading: docs/implementation_guides/impl_steps/step_3_4_worker_sync_integration.md
3. Following the implementation guide exactly as written
4. Running all validation commands before considering the task complete

Critical Requirements:
- Update SyncQueue to use real SupabaseClient
- Add sync status tracking
- Implement proper error handling
- Ensure worker continues on sync failures
- Test the integration thoroughly
- Ensure pytest shows all tests passing
- Ensure ckdr shows "All checks passed!"

Do NOT:
- Break existing Worker functionality
- Make sync failures stop the worker
- Skip status tracking
- Modify tests if they fail
- Proceed if any validation fails

Report any issues rather than making assumptions.

---

## Step 3.5: Remote Read Operations

Please implement Step 3.5: Remote Read Operations by:

1. First reading: docs/implementation_guides/impl_steps/STEP_EXECUTION_CONTEXT.md
2. Then reading: docs/implementation_guides/impl_steps/step_3_5_remote_read_operations.md
3. Following the implementation guide exactly as written
4. Running all validation commands before considering the task complete

Critical Requirements:
- Add remote read methods to JobDB
- Implement download functionality
- Create simple API if specified
- Handle missing data gracefully
- Test all remote operations
- Ensure pytest shows all tests passing
- Ensure ckdr shows "All checks passed!"

Do NOT:
- Make remote reads required
- Break local functionality
- Skip error handling
- Modify tests if they fail
- Proceed if any validation fails

Phase 3 Complete! After this step, run: `pt tests/implementation/ -v`

Report any issues rather than making assumptions.

---

## General Instructions for All Steps

1. **Always read STEP_EXECUTION_CONTEXT.md first** - It contains critical standards
2. **Follow the step guide exactly** - Do not add or remove features
3. **Tests must pass without modification** - Fix your implementation, not the tests
4. **Code quality must pass** - Both pytest and ckdr must succeed
5. **Work sequentially** - Complete each step before moving to the next
6. **Communicate issues** - Ask for help rather than making assumptions

## Success Criteria

For each step:
- ✅ All specified files created
- ✅ All tests passing with pytest
- ✅ Code quality passing with ckdr
- ✅ No modifications to test expectations
- ✅ Follows all technical standards

## Common Pitfalls to Avoid

- Don't add features "for completeness" - implement only what's specified
- Don't use different names or signatures - match exactly
- Don't skip validation - both pytest and ckdr must pass
- Don't modify tests - they define the specification
- Don't proceed with failures - fix issues before continuing