# Step 2.4: CLI Framework

## Goal
Create a basic CLI structure with worker run and job submit commands using Click.

## Prerequisites
- Step 2.3 completed and validated
- Required files exist: Worker with threading support
- Click installed: `uv add click`

## Overview

This step creates a command-line interface using Click framework:
- **Global options**: Base path and experiment name for all commands
- **Worker command**: Run workers with configurable sync
- **Job management**: Submit and list jobs
- **Experiment management**: Initialize and check status
- **Colored output**: Status indicators for better readability

## Key Components

### CLI Architecture
1. **Group command** (`@click.group()`)
   - Global `--base-path` and `--experiment` options
   - Context passing between commands
   - No JobDB in context (created per command)

2. **Core Commands**
   - `init` - Create experiment directory structure
   - `submit` - Create jobs from YAML/JSON configs
   - `list` - Display jobs with filtering
   - `status` - Show experiment summary
   - `worker` - Run worker process

### Design Decisions
- **No persistent JobDB**: Each command creates its own instance
- **Simple sync function**: Just prints for now (real sync in later steps)
- **Exit codes**: Non-zero on worker failures
- **Colored output**: Green=completed, Red=failed, Yellow=running

### Configuration Support
- YAML and JSON config files
- Required `_target_` field for Hydra
- Priority option for job submission
- Example config created on init

## Validation

Test coverage includes:
- Experiment initialization
- Job submission with priority
- Job listing with status filter
- Experiment status summary
- Worker execution via CLI
- Error handling for bad configs

Run: `pt tests/implementation/test_step_2_4.py -v`

## Implementation Notes

### Divergences from Instructions
1. **JobDB not stored in context**: Instructions show storing in `ctx.obj`
   - **Type**: Design improvement
   - **Reason**: Cleaner to create JobDB per command
   - **Impact**: Each command creates fresh JobDB instance

2. **Additional directories in init**: Implementation adds `logs` and `control`
   - **Type**: Enhancement
   - **Reason**: Needed for full system operation

3. **Type annotations**: Implementation adds full type hints
   - **Type**: Code quality improvement
   - **Impact**: Better IDE support and type checking

4. **Error handling in tests**: Tests now initialize experiment before submit
   - **Type**: Test robustness
   - **Reason**: JobDB validation requires initialized experiment

5. **Sync message handling**: Test doesn't check for sync messages
   - **Type**: Test realism
   - **Reason**: Sync messages appear asynchronously in background thread

### Implementation Quality Notes
- Clean command structure with Click decorators
- Good error messages with exit codes
- Colored output improves usability
- Context passing is minimal and clean
- Tests use CliRunner for isolation

### Lessons Learned
1. Click's context system is powerful but should be used sparingly
2. Creating JobDB per command is cleaner than storing in context
3. CliRunner provides excellent test isolation
4. Exit codes are important for scripting
5. Colored output significantly improves UX

### Dependencies for Later Steps
- CLI structure ready for additional commands (Step 2.5)
- Worker command will need real sync function
- Submit command ready for sweep functionality
- Status command can be extended with more metrics

### Technical Decisions
1. **Click over argparse**: More declarative and powerful
2. **No interactive prompts**: All input via options/arguments
3. **Flat command structure**: No nested command groups
4. **Exit codes**: Standard Unix conventions
5. **YAML/JSON support**: Flexibility in config format

### Testing Insights
- CliRunner captures output cleanly
- Need to test both success and error paths
- File operations need proper cleanup
- Exit codes are testable
- Mock sync function simplifies testing

### Performance Considerations
- Each command creates new JobDB (minimal overhead)
- No persistent connections or state
- Quick startup time for all commands
- No background processes from CLI

### Future Enhancement Opportunities
1. Progress bars for long operations
2. JSON output mode for scripting
3. Config validation before submission
4. Bulk job operations
5. Interactive mode for exploration
6. Shell completion support
7. Remote JobDB support

### Cross-Step Patterns
- Consistent error handling
- Clean separation of concerns
- Comprehensive test coverage
- Type annotations throughout

### Risk Areas
1. **Global options repetition**: Must specify for every command
2. **No config validation**: Invalid configs fail at runtime
3. **No authentication**: Anyone can submit jobs
4. **Path handling**: Relative paths might cause issues
5. **Large job lists**: No pagination support

## Common Mistakes to Avoid
- Using argparse (Click is simpler and more powerful)
- Adding complex command structures (keep it flat and simple)
- Forgetting to pass context between commands
- Mixing business logic with CLI code (keep it thin)
- Adding interactive prompts (all parameters via flags/options)
- Storing state in global variables

## Next Step
Proceed to Step 2.5: Job Management Commands