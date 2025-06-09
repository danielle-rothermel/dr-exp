# Base Path Configuration Improvement Plan

## Problem Summary
The current system has configuration drift issues where jobs can be uploaded to one location but workers search in another, leading to "no_job" failures with poor error messages and difficult debugging.

## Phase 4: Explicit Configuration (Long Term)

### 4.1 Command-Line Path Arguments
**Priority: Low**
- [ ] Add `--base-path` argument to all commands
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

