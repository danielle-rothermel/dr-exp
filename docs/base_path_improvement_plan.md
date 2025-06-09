# Base Path Configuration Improvement Plan

## Problem Summary
The current system has configuration drift issues where jobs can be uploaded to one location but workers search in another, leading to "no_job" failures with poor error messages and difficult debugging.

## Phase 1: Documentation Fixes (Immediate - Work Out of Box)

### 1.1 Fix CLAUDE.md Examples
**Priority: Critical**
- [ ] Update all workflow examples to use consistent environment variables
- [ ] Remove conflicting `DR_EXP_BASE_PATH` values within same workflows
- [ ] Add explicit environment setup section
- [ ] Test all documented workflows end-to-end

**Current problematic pattern:**
```bash
# Upload (implicit environment)
uvrp scripts/upload_configs.py --config-name decon_config

# Worker (different environment)  
DR_EXP_BASE_PATH="./logs/decon_test" uv run python scripts/manager_cli.py system run_worker
```

**Fixed pattern:**
```bash
# Consistent environment for entire workflow
export EXPMGR_MODE=files_local
export DR_EXP_BASE_PATH="./logs"

# All commands use same paths
uvrp scripts/upload_configs.py --config-name decon_config
uv run python scripts/manager_cli.py system run_worker dev_worker ./work
```

### 1.2 Add Environment Setup Section
- [ ] Create clear "Environment Setup" section at top of CLAUDE.md
- [ ] Document all environment variables and their effects
- [ ] Provide copy-paste environment setup for each mode
- [ ] Explain what each variable controls

### 1.3 Add Troubleshooting Section
- [ ] Document common configuration mismatches
- [ ] Add "Jobs not being claimed" troubleshooting steps
- [ ] Include commands to verify configuration
- [ ] Add file location debugging tips

## Phase 2: Error Message Improvements (Quick Wins)

### 2.1 Enhanced Worker Status Messages
**Priority: High**
- [ ] Replace generic "no_job" with detailed diagnostics
- [ ] Show directory being searched and file count
- [ ] Display current configuration in error messages
- [ ] Add suggestions for common misconfigurations

**Implementation:**
```python
# In worker.py claim_job failure:
logger.info(f"No jobs found in {job_db.jobs_dir}")
logger.info(f"Directory exists: {os.path.exists(job_db.jobs_dir)}")
logger.info(f"Files in directory: {len(os.listdir(job_db.jobs_dir)) if os.path.exists(job_db.jobs_dir) else 0}")
logger.info(f"Configuration: EXPMGR_MODE={config.mode}, DR_EXP_BASE_PATH={config.base_path}")
```

### 2.2 Configuration Mismatch Detection
**Priority: High**
- [ ] Check for jobs in common alternative locations when none found
- [ ] Warn about potential configuration mismatches
- [ ] Suggest corrective actions

**Implementation:**
```python
def diagnose_empty_queue(current_jobs_dir):
    alternatives = ["./job_data", "./logs/job_data", "../job_data"]
    for alt_dir in alternatives:
        if alt_dir != current_jobs_dir and os.path.exists(alt_dir):
            job_files = [f for f in os.listdir(alt_dir) if f.endswith('.json')]
            if job_files:
                logger.warning(f"Found {len(job_files)} jobs in {alt_dir} instead of {current_jobs_dir}")
                logger.warning("Check DR_EXP_BASE_PATH environment variable consistency")
```

## Phase 3: Configuration Visibility (Medium Term)

### 3.1 Debug Commands
**Priority: Medium**
- [ ] Add `manager_cli.py debug config` command
- [ ] Add `manager_cli.py debug health-check` command
- [ ] Show all effective configuration values
- [ ] Display file system state

**Commands to implement:**
```bash
uv run python scripts/manager_cli.py debug config
uv run python scripts/manager_cli.py debug health-check
uv run python scripts/manager_cli.py debug list-jobs-all-locations
```

### 3.2 Configuration Validation
**Priority: Medium**
- [ ] Add configuration consistency checks between commands
- [ ] Validate that job directories exist and are accessible
- [ ] Check for common setup errors
- [ ] Provide fix suggestions

## Phase 4: Explicit Configuration (Long Term)

### 4.1 Command-Line Path Arguments
**Priority: Low**
- [ ] Add `--base-path` argument to all commands
- [ ] Add `--jobs-dir` argument for direct specification
- [ ] Make explicit arguments override environment variables
- [ ] Update help text to explain path resolution


### 4.3 Configuration File Support
**Priority: Low**
- [ ] Support `.dr_exp.yaml` configuration files
- [ ] Allow project-specific defaults
- [ ] Hierarchical config: file < environment < command args

## Phase 5: Robustness Improvements (Long Term)

### 5.1 Path Canonicalization
**Priority: Low**
- [ ] Always use absolute paths internally
- [ ] Resolve symlinks and relative paths consistently
- [ ] Normalize path separators across platforms

### 5.2 Atomic Configuration Loading
**Priority: Low**
- [ ] Ensure all components of a workflow use identical configuration
- [ ] Add configuration versioning/hashing
- [ ] Detect configuration changes mid-workflow

### 5.3 Integration Tests
**Priority: Medium**
- [ ] Add end-to-end tests for each documented workflow
- [ ] Test configuration mismatch scenarios
- [ ] Verify error messages are helpful
- [ ] Test cross-platform path handling

## Implementation Priority

### Week 1: Documentation Fixes
- Fix CLAUDE.md examples (Phase 1.1)
- Add environment setup section (Phase 1.2)
- Add troubleshooting section (Phase 1.3)

### Week 2: Quick Error Message Wins  
- Enhanced worker status messages (Phase 2.1)
- Configuration mismatch detection (Phase 2.2)

### Week 3-4: Visibility Commands
- Debug commands (Phase 3.1)
- Configuration validation (Phase 3.2)
- Integration tests (Phase 5.3)

### Future: Architecture Improvements
- Explicit configuration options (Phase 4)
- Robustness improvements (Phase 5)

## Success Metrics

### Immediate (Week 1)
- [ ] All CLAUDE.md workflows work out-of-the-box
- [ ] Zero configuration mismatches in documentation
- [ ] Clear environment setup instructions

### Short Term (Week 2-4)
- [ ] Helpful error messages for configuration issues
- [ ] Debug commands provide actionable information
- [ ] Users can self-diagnose common problems

### Long Term
- [ ] Configuration mismatches are impossible or caught immediately
- [ ] All error messages include suggested fixes
- [ ] New users can set up system without trial-and-error

## Notes
- Focus on making existing workflows work reliably before adding new features
- Prioritize error messages over preventing errors initially (faster wins)
- Test all changes against the original decon training use case
- Maintain backward compatibility with existing environment variable usage