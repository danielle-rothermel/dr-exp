# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

`dr_exp` is a distributed experiment management system for deep learning research. It coordinates job execution across GPU clusters using a priority-based queue system with real-time monitoring.

## Development Commands

### Environment Setup
```bash
# Python dependencies
uv sync

# Frontend dependencies  
cd react-babysitter-ui && npm install

# Local database (recommended for development)
supabase start
export EXPMGR_MODE=supabase_local
```

### Running Services
```bash
# Backend API
uv run uvicorn dr_exp.api.main:app --reload

# Frontend
cd react-babysitter-ui && npm run dev

# Job management via CLI
uv run python scripts/manager_cli.py job upload-configs --sweep "model=resnet,vit"
uv run python scripts/manager_cli.py system run --gpus-per-node 2
```

### Testing & Quality
```bash
# Run tests with coverage
uv run pytest --cov=dr_exp --cov-report=term-missing

# Fast tests only
uv run pytest -m "fast"

# Skip Supabase-dependent tests
uv run pytest -m "not supabase"

# Linting
cd react-babysitter-ui && npm run lint
uv run ruff check src/ tests/
```

## Core Architecture

### Three-Mode System
1. **`EXPMGR_MODE=files_local`**: JSON files, no dependencies
2. **`EXPMGR_MODE=supabase_local`**: Local PostgreSQL via Docker
3. **`EXPMGR_MODE=supabase_remote`**: Cloud PostgreSQL for production

### Abstract Interface Pattern
The system uses `BaseJobDB` abstract interface to eliminate mixed responsibilities:
- `Manager` coordinates workers using only abstract methods
- `LocalJobDB` and `SupabaseJobDB` implement the same interface
- Factory pattern ensures consistent system configuration

### Component Structure
- **`src/dr_exp/job_db/`**: Database abstraction layer
- **`src/dr_exp/manage/`**: Manager/Worker coordination system  
- **`src/dr_exp/api/`**: FastAPI backend with WebSocket support
- **`src/dr_exp/cli/`**: Command-line interface with grouped commands
- **`src/dr_exp/logging/`**: Structured metrics and artifact logging
- **`react-babysitter-ui/`**: Real-time monitoring frontend

### Priority System
5-tier job priorities (0-1000):
- SYSTEM (900-1000): Critical maintenance
- URGENT (700-899): Deadline experiments
- HIGH (400-699): Important work
- NORMAL (100-399): Default range
- LOW (0-99): Background jobs

## Key Development Patterns

### Configuration Management
- Uses Hydra for complex config composition
- Supports hyperparameter sweeps via `--sweep` flag
- Environment-aware configuration in `src/dr_exp/job_db/config.py`

### Testing Strategy
- 172+ tests with pytest markers: `supabase`, `slow`, `fast`, `integration`, `unit`
- Event-driven testing using threading events for coordination
- Mock fixtures with enhanced time mocking
- Isolated test databases for parallel execution

### Database Operations
Always use abstract interface methods in business logic:
```python
# Good: Uses abstract interface
jobs = job_db.get_stale_jobs(max_age_seconds=300)
job_db.mark_jobs_failed(job_ids, reason="timeout")

# Avoid: Database-specific implementations in business logic
```

### CLI Command Development
Commands follow command pattern in `src/dr_exp/cli/commands/`:
- Inherit from `BaseCommand`
- Grouped by function: `job`, `system`, `admin`
- Use `scripts/manager_cli.py` as entry point

### Error Handling
- Comprehensive logging with structured output
- Graceful degradation for worker failures
- Automatic job heartbeat monitoring
- Stack trace preservation in error logging

## Integration Points

### deconCNN Training Library
- Uses Lightning callback wrapper pattern
- Official config support via `decon_trainer.py`
- Example configs in `src/dr_exp/train_examples/configs/`

### SLURM Integration
- Batch job submission via `scripts/slurm_job.sbatch`
- GPU discovery and resource management
- Distributed worker coordination

### Storage & Artifacts
- Supabase object storage for artifacts
- Local filesystem fallback
- Checkpoint compression and upload coordination

## Common Development Tasks

### Adding New Commands
1. Create command class in `src/dr_exp/cli/commands/`
2. Register in `src/dr_exp/cli/registry.py`
3. Add to appropriate group in `src/dr_exp/cli/command_groups.py`
4. Follow existing command patterns

### Database Schema Changes
1. Create migration in `supabase/migrations/`
2. Update abstract interface in `BaseJobDB` if needed
3. Implement in both `LocalJobDB` and `SupabaseJobDB`
4. Add tests for new functionality

### Frontend Development
- React 19 with Vite build system
- Tailwind CSS for styling
- WebSocket integration for real-time updates
- Axios for HTTP requests

## CRITICAL DEVELOPMENT PRINCIPLES

⚠️ **ALL code changes must follow these mandatory principles:**

### 1. **Fail Fast and Loud - NEVER Silent Failures**
```python
# ❌ WRONG - Silent failure with default
value = config.get("required_field", "default")

# ✅ CORRECT - Immediate failure  
value = config["required_field"]  # KeyError if missing

# ❌ WRONG - Continues with None
result = upload_file(path)
storage_path = result.get("storage_path")  # None if upload failed

# ✅ CORRECT - Fails immediately
result = upload_file(path)
storage_path = result["storage_path"]  # KeyError if upload failed
```

**Requirements:**
- Never use `.get()` with defaults to mask missing required data
- Prefer `KeyError`/`AttributeError` over silent `None` returns
- Add validation that raises `ValueError`/`TypeError` when assumptions violated
- Use assertions for invariants that must always be true

### 2. **Zero Backward Compatibility - Break Everything Immediately**
```python
# ❌ WRONG - Backward compatibility masks interface changes
def process_result(result):
    if isinstance(result, dict):  # Old format
        return result.get("status", "unknown")
    return result.status  # New format

# ✅ CORRECT - Force immediate migration
def process_result(result: TrainingResult):  # Type enforced
    return result.status  # AttributeError if wrong type
```

**Requirements:**
- Make incompatible changes obvious through `TypeError`/`AttributeError`
- Force all callers to update to new patterns explicitly  
- Never provide fallback behavior that masks interface changes
- Use strict type annotations and runtime type checking

### 3. **Flag Strange Patterns - Stop and Alert User**
**When you encounter ANY of these patterns, STOP immediately and alert the user:**

- `.get(key, default)` patterns that could mask missing data
- Exception handling that continues with partial/invalid state  
- Functions that return `None` instead of raising exceptions
- Double/redundant operations (like recording failures twice)
- Magic defaults or implicit behavior that could hide bugs
- Silent type coercions or data transformations

### 4. **Enforce Strict Contracts**
```python
# ❌ WRONG - Loose dictionary interface
def train(config: dict) -> dict:
    return {"status": "success", "acc": 0.95}

# ✅ CORRECT - Strict dataclass contract
def train(config: TrainingConfig) -> TrainingResult:
    return TrainingResult(status="success", final_val_acc=0.95, ...)
```

**Requirements:**
- Use dataclasses with validation over loose dictionaries
- Require all parameters explicitly rather than providing defaults
- Make required fields fail immediately if missing
- Document and enforce exact contracts between components

## deconCNN Integration Status

**✅ COMPLETE**: Core integration between deconCNN and dr_exp is working
- Training function: `src/dr_exp/train_examples/decon_trainer.py`
- Type system: `src/dr_exp/training/result.py` with strict `TrainingResult` enforcement
- Config system: Proper Hydra composition with deconCNN validation
- Worker: `scripts/run_decon_worker.py` with type enforcement

**Usage:**
```bash
# Upload and run deconCNN training jobs
export DR_EXP_BASE_PATH="./experiment_data"
EXPMGR_MODE="files_local" uv run python scripts/upload_configs.py \
  --base-config-path /path/to/configs --config-name decon_integration_config
EXPMGR_MODE="files_local" uv run python scripts/run_decon_worker.py
```

When making changes, ensure compatibility across all three database modes, maintain the abstract interface pattern, and strictly follow the development principles above.