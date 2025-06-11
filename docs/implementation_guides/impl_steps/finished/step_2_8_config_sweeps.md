# Step 2.8: Config Sweeps

## Goal
Add parameter sweep functionality to generate and submit multiple job configurations from a single command.

## Prerequisites
- Step 2.7 completed and validated
- CLI framework with job submission working
- Hydra configs being used for job configuration
- JobDB can create jobs with configs

## Overview

This step implements parameter sweep generation for ML experiments:
- **Parameter parsing**: Parse sweep strings like "model=r18,r50 lr=0.01,0.001"
- **Config generation**: Create all combinations using itertools.product
- **Hydra integration**: Compose configs with overrides
- **Validation**: Ensure _target_ exists and is importable
- **CLI command**: Submit sweeps with dry-run preview
- **Progress tracking**: Show progress for large sweeps

## Key Components

### sweep_utils.py Functions
Utilities for sweep operations:
1. **`parse_sweep_params()`** - Parse "key=val1,val2" format strings
2. **`generate_sweep_configs()`** - Create all config combinations
3. **`load_hydra_config()`** - Load base config with overrides
4. **`validate_sweep_config()`** - Check _target_ is importable

### Sweep CLI Command
Full-featured sweep submission:
- Base config with parameter overrides
- Target override option
- Dry-run mode for preview
- Progress reporting for large sweeps
- Priority setting for all jobs

### Design Decisions
- **Simple format**: key=val1,val2 parsing (no eval)
- **Cartesian product**: All parameter combinations
- **Hydra composition**: Leverage existing config system
- **Early validation**: Check imports before job creation
- **Batch progress**: Report every 10 jobs for large sweeps

## Validation

Test coverage includes:
- Parameter string parsing (basic, nested, edge cases)
- Config generation with combinations
- Target validation and import checking
- CLI dry-run mode
- Actual job creation
- Target override functionality
- Large sweep progress reporting

Run: `pt tests/implementation/test_step_2_8.py -v`

## Implementation Notes

### Minor Enhancement from Instructions
The implementation added `from typing import cast` import for better type handling, which wasn't in the original instructions but improves type safety.

### Implementation Quality Notes
- Clean separation of parsing and generation logic
- Good error handling for invalid configs
- Efficient config generation with itertools
- Comprehensive validation before job creation
- User-friendly progress reporting

### Lessons Learned
1. Simple key=value parsing is sufficient for most sweeps
2. Hydra's compose API handles nested overrides well
3. Early validation prevents broken job creation
4. Progress reporting essential for large sweeps
5. Dry-run mode crucial for user confidence

### Dependencies for Later Steps
- SLURM scripts will use sweep for large experiments (Step 2.9)
- Web UI will display sweep relationships
- Analysis tools can group sweep results
- Sweep metadata helps result aggregation

### Technical Decisions
1. **String parsing**: Simple split operations vs complex parsers
2. **Itertools.product**: Clean way to generate combinations
3. **Hydra compose**: Reuse existing config system
4. **Import validation**: Catch errors before job submission
5. **Batch creation**: Submit all at once for consistency

### Testing Insights
- Mock file systems for config loading tests
- CliRunner perfect for testing CLI commands
- Separate parsing from generation for unit testing
- Test both small and large sweeps
- Verify all parameter combinations generated

### Performance Considerations
- Config loading overhead minimal for reasonable sweeps
- Memory usage scales with sweep size (all configs in memory)
- Job creation is sequential (could parallelize)
- Progress reporting balances info vs spam
- Dry-run prevents accidental large submissions

### Future Enhancement Opportunities
1. Support range syntax (lr=0.001:0.1:10 for log scale)
2. Add conditional parameters (if model=X then Y=Z)
3. Implement random sampling for huge spaces
4. Support loading sweeps from YAML files
5. Add sweep result analysis commands
6. Enable parallel job creation
7. Support nested list parameters

### Cross-Step Patterns
- CLI command structure consistent
- Config validation patterns reused
- Progress reporting similar to launcher
- Error handling follows JobDB patterns
- Test structure matches other steps

### Risk Areas
1. **Memory usage**: Large sweeps load all configs
2. **Accidental large sweeps**: Mitigated by dry-run
3. **Invalid combinations**: User must understand their parameter space
4. **Config resolution**: Complex overrides might fail
5. **Import validation**: Dynamic imports can be tricky

## Common Mistakes to Avoid
- Trying to evaluate parameters as Python expressions
- Forgetting to validate target existence
- Creating enormous sweeps without dry-run first
- Using overly complex parameter formats
- Not understanding Hydra override syntax

## Next Step
Proceed to Step 2.9: SLURM Integration