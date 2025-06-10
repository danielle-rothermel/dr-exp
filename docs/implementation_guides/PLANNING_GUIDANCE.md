# Planning Guidance for dr_exp Implementation Guides

## Purpose of These Docs
These implementation guides are designed for **less intelligent agents with smaller context windows** to implement the dr_exp system. The goal is to provide exact implementation details while preventing common engineering mistakes.

## Core Planning Principles

### 1. Simplicity Over Cleverness
- Single JobDB implementation (no abstract interfaces)
- File locking for concurrency (no distributed systems)
- Hydra's `_target_` for dispatch (no custom routing)
- Direct file paths (no complex configuration)

### 2. Fail Fast Philosophy
- Use `assert` statements, not exceptions
- Validate early (e.g., `_target_` at job creation)
- No fallback mechanisms or recovery logic
- Clear error messages

### 3. Explicit Over Implicit
- Configs must specify `_target_` explicitly
- No magic or auto-detection
- All paths and names are explicit
- No hidden behavior

## Key Technical Decisions

### 1. Job Dispatch via Hydra
Jobs contain `_target_: module.function` that points to the training function. Workers simply call `hydra.utils.call(config)`. This eliminates all dispatch logic.

### 2. Concurrent Worker Access
File locking (`fcntl`) in `claim_next_job()` handles everything. Multiple workers can run simultaneously with no coordination needed. The implementation already handles this correctly.

### 3. Integration Pattern for ML Libraries
- Libraries (like deconCNN) provide minimal changes (e.g., MetricsCallback)
- dr_exp provides wrapper functions with `_target_`-compatible signatures
- Configs remain in the library's native format
- StructuredLogger stays in dr_exp

### 4. Operational Features
- CLI provides all user interaction (`dr_exp` command)
- Jobs can be killed, boosted, or run individually
- Dead workers auto-recover after 5 minutes
- No complex orchestration needed

## What to Focus On

### DO Focus On:
1. **Exact implementation code** - Agents should copy/paste
2. **Clear file paths** - Where exactly to create files
3. **Validation steps** - How to verify each phase works
4. **Common mistakes to avoid** - Explicit "DO NOT" sections

### DON'T Focus On:
1. **Explanations of why** - Keep theory minimal
2. **Alternative approaches** - One way only
3. **Backwards compatibility** - Clean slate
4. **Error recovery** - Fail fast instead

## Current State of Planning

### Completed:
- Phase 1: Clean JobDB with operational methods
- Phase 2: Worker with CLI interface, launcher for multi-worker deployment, and config submission commands
- Phase 2.5: SLURM Integration with long-running launcher design
- Phases 3-6: Basic structure defined
- Integration pattern for deconCNN established

### Areas for Potential Refinement:
1. **Supabase Integration**: Phase 3 could be more prescriptive about error handling

## Guidelines for Future Planning

### When Adding Features:
1. First ask: "Can this be done with existing primitives?"
2. If new code needed, can it be <50 lines?
3. Does it maintain fail-fast philosophy?
4. Is there a simpler way?

### When Reviewing Plans:
1. Are instructions copy-paste ready?
2. Do tests verify the feature works?
3. Are common mistakes explicitly called out?
4. Is the scope minimal?

### Red Flags to Avoid:
- Abstract base classes or interfaces
- Configuration files for configuration
- Fallback mechanisms
- Hidden or automatic behavior
- Complex state management
- Backwards compatibility
- "Smart" or "adaptive" features

## Implementation Order
Phases should be implemented strictly in order:
1. Phase 1: JobDB (foundation)
2. Phase 2: Worker + CLI (execution)
3. Phase 3: Supabase (remote features)
4. Phase 4: API (monitoring)
5. Phase 5: Cloud (optional)
6. Phase 6: Cleanup tools

Each phase builds on the previous. Skipping breaks assumptions.

## Key Constraints
- **Mac/Linux only** - No Windows support needed
- **Python 3.10+** - Use modern Python features
- **Single experiment per JobDB** - No multi-tenancy
- **Local filesystem is truth** - Supabase is read-only mirror

## Success Criteria
The implementation is successful when:
1. A user can submit jobs via CLI
2. Workers claim jobs by priority
3. Multiple workers don't conflict
4. Dead workers don't block jobs
5. Users can monitor/control jobs via CLI
6. No complex configuration needed

## Development Tooling Standards

### Dependency Management
- ALL dependencies managed via `uv` (not pip)
- Add dependencies: `uv add package` or `uv add --dev package`
- Run scripts: `uv run python scripts/...` (aliased as `uvrp`)

### Code Quality
- After EVERY code change: Run `ckdr` (ruff check + format + mypy)
- Type hints required on ALL functions
- Follow existing import patterns

### Testing
- Use pytest for all tests (not standalone scripts)
- Tests go in `tests/` directory mirroring `src/` structure
- Run tests with `pt` (alias for `uv run pytest`)
- Test files named `test_*.py`

## Quality Gate Philosophy

### NEVER Accept Broken Tests
When `ckdr` or `pt` fails, you MUST:
1. **Fix the root cause** - Don't modify tests to pass, fix the code
2. **Understand why it failed** - Read the full error, understand the intent
3. **Fix ALL issues** - Even "unrelated" failures often reveal integration problems
4. **Preserve test intent** - Tests document expected behavior, don't weaken them

### Common Anti-Patterns to AVOID
❌ **DO NOT**:
- Skip failing tests with `@pytest.mark.skip`
- Modify assertions to match broken behavior
- Add try/except to hide errors
- Weaken type hints to avoid mypy errors
- Disable ruff rules with `# noqa`
- Change test data to make tests pass

✅ **DO**:
- Fix the implementation to match test expectations
- Strengthen type hints when mypy complains
- Refactor code when ruff identifies issues
- Investigate why "unrelated" tests fail
- Ask for clarification if test intent is unclear

### The Quality Gate Rule
**No code proceeds until ALL of these pass:**
```bash
ckdr  # Must show: "All checks passed!"
pt    # Must show: "X passed" with no failures/skips
```

If you cannot make these pass by fixing the code properly, STOP and ask for help.

## System Requirements and Constraints

This section consolidates all requirements identified during planning, both from our SLURM integration discussion and from analyzing all implementation guides.

### 1. HPC Environment Requirements
- **Long-running GPU allocations**: System must hold GPUs for up to 47 hours
- **Multiple workers per GPU**: Support 2-4 workers per GPU with CUDA MPS
- **Rapid job turnaround**: New jobs should start within seconds when workers are idle
- **SLURM compatibility**: Clean integration with SLURM job scheduler
- **No artificial GPU keep-alive**: Respect other users, accept termination if underutilized
- **Graceful shutdown**: Stop cleanly before SLURM time limits

### 2. Scale and Performance Requirements  
- **24 total GPUs**: System designed for clusters with ~24 GPUs available
- **File locking**: `fcntl` must handle all concurrent access (no distributed systems)
- **Independent workers**: No inter-worker communication, JobDB handles coordination
- **Atomic operations**: Each job claim/update must be atomic
- **Non-blocking sync**: Background uploads must not block job execution
- **5-minute heartbeat timeout**: For automatic stale job recovery

### 3. Operational Workflows
- **Submit jobs anytime**: While launcher is running, jobs start immediately
- **Long experiment cycles**: Experiments may run for days with continuous job submission
- **Priority-based scheduling**: 0-1000 range, highest priority runs first
- **Job control**: Kill, boost priority, or run specific jobs on demand
- **Automatic recovery**: Dead workers restart if jobs pending, stale jobs recover
- **Status monitoring**: Regular status logs every 5 minutes

### 4. User Experience Requirements
- **Single entry point**: One `sbatch` command starts everything
- **Minimal configuration**: Just experiment name and worker count
- **Clear status visibility**: Logs show jobs completed, workers alive, runtime
- **No manual worker management**: Launcher handles all spawning/monitoring
- **CLI for all operations**: Unified `dr_exp` command interface

### 5. Technical Architecture
- **Single JobDB implementation**: No abstract interfaces or multiple backends
- **Hydra dispatch**: Jobs use `_target_` field for function routing  
- **Local filesystem is truth**: All writes go to /scratch first
- **Supabase as mirror**: Eventually consistent, read-only copy
- **Fail fast philosophy**: Assertions not exceptions, no recovery logic

### 6. Integration Requirements
- **CUDA MPS support**: For efficient GPU sharing between workers
- **Python 3.10+**: Use modern language features
- **Mac/Linux only**: No Windows support needed
- **ML library pattern**: Minimal changes to existing libraries via wrappers
- **No complex dependencies**: Just essential packages

### 7. Data Management
- **Experiment isolation**: Single experiment per JobDB instance
- **Clear directory structure**: `jobs/`, `storage/`, `sync_queue/` organization
- **Storage categorization**: Metrics, logs, models tracked separately
- **Interactive cleanup tools**: With dry-run and confirmation steps
- **Sync queue management**: Track and retry failed uploads

### 8. Reliability and Recovery
- **Worker auto-restart**: When jobs are pending and worker dies
- **Periodic maintenance**: Stale job recovery every 10 minutes
- **Heartbeat monitoring**: Detect hung/dead workers via heartbeats
- **Signal handling**: Graceful shutdown on SIGTERM/SIGINT
- **Queue persistence**: Jobs survive worker/launcher restarts

### 9. Deployment Constraints
- **Single launcher process**: Not complex job arrays or distributed coordination
- **47-hour runtime limit**: Leave buffer for cleanup before 48-hour SLURM limit
- **Environment flexibility**: Support 1-3 GPU allocations dynamically
- **Minimal SLURM configuration**: Reusable script with environment variables

### 10. Design Philosophy Constraints
- **Simplicity over features**: Every feature must be essential
- **Explicit over implicit**: No hidden behavior or magic
- **Direct over abstract**: Concrete implementations, not frameworks
- **Fail fast over resilience**: Clear errors, not complex recovery
- **Convention over configuration**: Sensible defaults, minimal options

These requirements drive all implementation decisions and should be referenced when evaluating any proposed changes or additions to the system.

## Remember
These docs are for **implementation**, not education. Every line should help an agent write correct code on the first try. When in doubt, be more explicit and prescriptive.
