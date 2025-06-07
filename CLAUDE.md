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



