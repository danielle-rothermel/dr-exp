# CLAUDE.md

## System Overview

dr_exp is a distributed job scheduler for machine learning experiments. Its core components are:
- Manager (src/dr_exp/manage/manager.py): Assigns jobs from the queue.
- Worker (src/dr_exp/manage/worker.py): Executes a single job.
- JobDB (src/dr_exp/job_db/): A database (Supabase or local) for job state.
- API (src/dr_exp/api/main.py): A FastAPI backend for the UI and CLI.
- CLI (src/dr_exp/cli/): A command-line interface for managing the system.

## Development Commands

### Python Backend
- **Install dependencies**: `uv sync`
- **Run tests**: `uv run pytest`
- **Start API server**: `uv run uvicorn dr_exp.api.main:app --reload` (serves on http://localhost:8000)
- **Run manager**: `uv run python scripts/run_manager.py`
- **Run worker**: `uv run python scripts/run_worker.py`
- **Manager CLI**: `uv run python scripts/manager_cli.py <command>` (see CLI Commands section)
- **Reset local job database**: `uv run python scripts/reset_local_jobdb.py`

### Supabase
- **Install Supabase CLI**: `brew install supabase/tap/supabase` (recommended) or other methods
- **Start local Supabase**: `supabase start` (requires Docker)
- **Stop local Supabase**: `supabase stop`
- **Reset local database**: `supabase db reset` (applies all migrations)

### Environment Configuration

- `EXPMGR_MODE`: Database mode selection
  - `"files_local"`: Local JSON files (simple, no Docker required)
  - `"supabase_local"`: Local Supabase with full features (requires Docker)
  - `"supabase_remote"`: Production Supabase (requires cloud account)
- `DR_EXP_BASE_PATH`: Base directory for job data storage
- `ADMIN_API_KEY`: API key for admin endpoints (defaults to "testkey")
- Supabase connection vars (for supabase_remote): `SUPABASE_URL`, `SUPABASE_KEY`, `SUPABASE_SERVICE_ROLE_KEY`
- `PYTHONPATH`: Should include the project root for proper imports

## Testing

**Test Infrastructure:**
- Comprehensive test suite with enhanced fixtures in `tests/conftest.py` and `tests/manage/conftest.py`
- Parallel test execution using pytest-xdist for improved performance
- Test categorization with markers for fast/slow/concurrency/integration tests

**Running Tests:**
- **All tests**: `uv run pytest`
- **Parallel execution**: `uv run pytest -n auto`
- **Fast tests only**: `uv run pytest -m "fast"`
- **Skip slow tests**: `uv run pytest -m "not slow"`
- **Specific test types**: `uv run pytest -m "concurrency"` or `uv run pytest -m "integration"`

**Key Testing Patterns:** Use direct `trainer_fn` parameters, event-driven synchronization, and enhanced fixtures for deterministic testing.

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

See `DECON_INTEGRATION_GUIDE.md` for complete details and next steps.

