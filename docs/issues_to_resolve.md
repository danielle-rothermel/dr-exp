# Issues to Resolve

This document tracks issues discovered during the quick start guide testing on 2025-06-10.

## Critical Issues

### 1. Path Resolution Problems
- **Issue**: Relative paths cause FileNotFoundError in worker sync_queue operations
- **Symptom**: Worker fails with `FileNotFoundError: [Errno 2] No such file or directory: 'debug_experiment/test_run/sync_queue/...'`
- **Workaround**: Use absolute paths with `$(pwd)` prefix
- **Root Cause**: Unknown - needs investigation


### 2. Submit Command Config Composition
- **Issue**: No support for Hydra-style config composition
- **Impact**: Cannot use `--config-path` and `--config-name` pattern
- **Expected**: `submit --config-path configs --config-name decon_config`
- **Actual**: Only accepts direct config file path
- **Root Cause Investigation**:
  - Submit command uses `yaml.safe_load()` to read single file (line 94 in cli/main.py)
  - Does NOT use Hydra's config loading system
  - `defaults:` lists in configs are completely ignored
  - Config composition features are unavailable
  - Worker DOES use Hydra (`hydra.utils.call(config)`) but only after config is loaded
- **Example Problem**: DeconCNN configs use composition:
  ```yaml
  defaults:
    - machine: cluster
    - paths: default
    - model: resnet18_cifar
    - optim: adamw
    - lrsched: timm_cosine
    - /transform@train_transforms: train_transform
    - /transform@eval_transforms: eval_transform
  ```
  These references are not resolved, causing missing key errors
- **Available Solution**: 
  - Hydra should be used to support config composition
  - DeconCNN provides validation functions that should be used:
      - `validate_model_config()`: Validates architecture, init_method, nonlinearity, etc.
      - `validate_optimizer_config()`: Validates optimizer name, lr, weight_decay
      - `validate_scheduler_config()`: Validates scheduler type, warmup, lr_min
      - `validate_training_config()`: Validates epochs, batch_size, limit_train_batches
      - These are exported from `deconcnn.config_validator` module
- **Integration Needed**: Submit command should call these validators before creating job
- **Better Solution**: Maintain complete config directory structure with:
  - Full set of config directories from deconCNN (model/, optim/, etc.)
  - Canonical test config that must always pass CI
  - Adapted paths/default.yaml for dr_exp storage
- **Key Benefits**:
  - Configs serve as living documentation (can't get out of sync)
  - Enables proper Hydra config composition
  - Test coverage ensures compatibility with deconCNN updates
  - Users can discover options by browsing config files
- **Requirements**:
  - Copy config structure from deconCNN source
  - Adapt paths to use dr_exp storage locations
  - Add canonical_test.yaml that exercises all validators
  - Include in test suite to catch breaking changes

### 3. Error Handling
- **Issue**: Sync queue errors crash the worker instead of graceful handling
- **Symptom**: Worker exits completely on sync_queue FileNotFoundError
- **Expected**: Log error and continue processing job
- Why this happens: Looking at the worker code (around line 229 and 251):
  - Worker discovers artifacts and tries to add them to sync_queue
  - If that fails, it tries to save an error file
  - But saving the error file ALSO tries to add to sync_queue
  - This creates a circular failure where error handling itself errors
- As a result, jobs are stuck in "running" when workers fail
    - **Issue**: Jobs stuck in "running" state when worker fails
    - **Symptom**: Job remains "running" after worker crash, recover command finds no stale jobs
    - **Expected**: Automatic recovery after heartbeat timeout
    - **Impact**: Manual intervention required (kill command)
- Additionally, understanding what happens is hard because the errors aren't surfaced
    - **Issue**: Worker errors not clearly surfaced
    - **Example**: Sync queue errors buried in traceback
    - **Need**: Clear error reporting in job status

### 4. Init Command Inconsistencies
- **Issue**: Creates `example_config.yaml` but no `.jobdb` metadata file
- **Note**: Guide mentions `.jobdb` file but it's not created or not visible

### 5. Help Message Mismatch
- **Issue**: Init command suggests incorrect submit syntax
- **Shows**: `dr_exp --base-path ./debug_experiment --experiment test_run submit example_config.yaml`
- **Reality**: Needs full path to config file, not just filename

### 6. Test Cleanup Issue
- **Issue**: Tests create job directories in repository root
- **Symptom**: 29 `job_*` directories created during test run
- **Location**: Top-level repository directory
- **Impact**: Pollutes repository with test artifacts
- **Root Cause**: Tests likely using relative paths without proper temp directory setup

## Major Issues

### 1. Boost Command Misleading Name
- **Issue**: Command name suggests relative boost but sets absolute priority
- **Expected Behavior**: `boost job_id --amount 200` to increase priority by 200
- **Actual Behavior**: `boost job_id --priority 800` sets priority to exactly 800
- **User Impact**: Confusion about how to use the command effectively
- **Suggestion**: Either rename to `set-priority` or change to relative boost behavior

### 2. Validate Command Limited Scope
- **Issue**: Only validates directory structure, not experiment health
- **Current Checks**: Directory existence only
- **Missing Checks**:
  - Job file integrity (valid JSON, required fields)
  - Config validity (can they be loaded?)
  - Orphaned storage directories
  - Sync queue health
  - Worker state consistency
- **Impact**: Users may think experiment is healthy when it has data issues

## Suggested Improvements

### 1. Move Worker Temporary Directory Under Experiment
- **Current Behavior**: Worker requires `--working-dir` parameter, creates job directories wherever specified
- **Problem**: Leads to scattered work directories, requires absolute paths, pollutes repository
- **Suggested Solution**: Remove `--working-dir` parameter entirely and always use `worker_tmp/` within experiment
- **Proposed Structure**:
  ```
  base_path/
  └── experiment1/
      ├── jobs/
      ├── storage/
      ├── sync_queue/
      ├── logs/
      ├── control/
      └── worker_tmp/     # Worker temporary execution directories
          ├── job_xxx/
          └── job_yyy/
  ```
- **Benefits**:
  - All experiment files in one location
  - No `--working-dir` parameter to confuse users
  - Cleaner repository (no scattered work directories)
  - Easier cleanup (delete one experiment directory removes everything)
  - Path resolution simplified (all paths relative to experiment)
  - Prevents accidental job directory creation in wrong locations
  - Enforces consistent directory structure across all deployments
- **Implementation**: 
  - Remove `--working-dir` option from CLI
  - Worker always uses `{base_path}/{experiment}/worker_tmp/`
  - Add `worker_tmp/` to experiment initialization

## To Verify After Fixes

### 1. Submit Command Overrides Support
- **Original Issue**: No support for `--overrides` parameter
- **Expected**: `submit config.yaml --overrides "epochs=10,batch_size=64"`
- **Current Status**: No --overrides option exists
- **Hypothesis**: Should work automatically once Hydra config composition is implemented
- **Reason**: Hydra's `compose()` API handles both composition and overrides
- **To Verify**: After fixing issue #3, test that override syntax works without additional changes

### 2. Checkpoint Storage Location
- **Original Issue**: Could not test checkpoint saving due to config complexity (issue #17)
- **Expected Behavior**:
  - Checkpoints saved to `{base_path}/{experiment}/storage/run_{job_id}/`
  - NO files in default PyTorch Lightning location (`./lightning_logs/`)
  - NO files in Hydra's default output directory
- **Current Status**: Untested due to config loading failures
- **Hypothesis**: Should work correctly once configs can be loaded
- **Reason**: DeconCNN trainer already sets `default_root_dir = storage_path`
- **To Verify**: 
  - Submit job with `enable_checkpointing: true`
  - Confirm checkpoints appear only in experiment storage
  - Verify no `lightning_logs/` directory created anywhere

### 3. DeconCNN Logging Behavior
- Verify that if we update the deconcnn logging location the logs in fact appear where we expect.  If not, look for where they are actually being written.

## Potential Implementation Plan Mistakes

### 1. Missing Submit Options
- **Issue**: No `--tag` or `--description` options in submit command
- **Impact**: Cannot add metadata to jobs for organization
- **Note**: Original guide showed these options but they don't exist

### 2. Missing .jobdb File
- **Documentation Claims**: Multiple docs mention `.jobdb` metadata file in experiment structure
- **Reality**: No code creates or uses this file
- **Investigation**: 
  - Init command creates all directories but no .jobdb file
  - JobDB class doesn't reference or create it
  - System works perfectly without it
- **Likely Explanation**: Documentation artifact from planning phase
- **Potential Contents**: Could have stored experiment-level metadata (creation time, description, etc.)
- **Impact**: None - system is fully functional without it

### 3. Undocumented example_config.yaml Creation
- **Behavior**: Init command creates `example_config.yaml` in experiment directory
- **Documentation**: Not mentioned in quick start guide or most docs
- **Content**: Basic test trainer config with comments
- **Impact**: Minor - helpful but unexpected file creation
- **Location**: Created at `{base_path}/{experiment}/example_config.yaml`

### 4. Worker File Logging Not Implemented
- **Issue**: Workers do not create log files as documented
- **Expected**: Log files at `logs/worker_<worker_id>.log`
- **Actual**: Workers only output to stdout/stderr
- **Impact**: Cannot monitor worker activity with `tail -f` as shown in guide
- **Documentation Claims**: Quick Start guide shows monitoring with `tail -f $(pwd)/debug_experiment/test_run/logs/worker_debug_worker.log`

### 5. run-one Command Documentation Error
- **Issue**: Quick Start guide shows incorrect syntax for run-one
- **Documentation Shows**: `run-one configs/test_job.yaml`
- **Actual Syntax**: `run-one <job_id> [--working-dir <path>]`
- **Impact**: Users following guide will get "No job found" error
- **Workaround**: Must submit job first to get ID, then use run-one

### 6. Error File Format Discrepancy
- **Issue**: Documentation mentions `error.json` but system creates `error.txt`
- **Documentation**: "View error details: cat .../error.json | jq ."
- **Reality**: Error details saved as plain text in `error.txt`
- **Impact**: Minor - just a documentation inconsistency

### 7. Sync Queue Items Not Being Processed
- **Issue**: Sync queue items accumulate but are never processed
- **Symptom**: After running a worker, 5 sync items remain pending indefinitely
- **Example**: `sync-status` shows "Pending: 5" even after job completion
- **Impact**: Could lead to unbounded growth and eventual disk space issues
- **Root Cause**: Unknown - sync processing mechanism may not be implemented

## Testing Environment

- Platform: macOS Darwin 24.3.0
- Python: 3.12 (via uv)
- Working Directory: `/Users/daniellerothermel/drotherm/repos/dr_exp`
- Test Date: 2025-06-10
- Additional Testing Results: See `/docs/testing_results_2025-06-10.md`
