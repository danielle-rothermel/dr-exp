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
- Phase 2: Worker with CLI interface
- Phases 3-6: Basic structure defined
- Integration pattern for deconCNN established

### Areas for Potential Refinement:
1. **Config Upload Process**: Currently uses existing scripts - could be simplified to use CLI
2. **Supabase Integration**: Phase 3 could be more prescriptive about error handling
3. **Testing Strategy**: Could add more comprehensive integration tests
4. **SLURM Integration**: Not yet covered - how to launch workers on cluster

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

## Remember
These docs are for **implementation**, not education. Every line should help an agent write correct code on the first try. When in doubt, be more explicit and prescriptive.