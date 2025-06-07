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

## Test Refactoring Plan (Phase 1 ✅ Complete)

**Phase 1 COMPLETED**: Critical manager-worker integration tests have been fixed and are now reliable.

Continue with the remaining phases outlined in `test_refactor_plan.md`:

- **Phase 2**: Enhance test infrastructure with better fixtures
- **Phase 3**: Add missing edge case coverage and concurrency tests  
- **Phase 4**: Optimize test performance and maintainability

## Test Development Reference

- **test_refactor_plan.md**: Four-phase plan with Phase 1 solutions and Phase 2+ guidance
- **TESTING_PATTERNS.md**: Technical patterns and best practices for reliable test development
- **tests/manage/test_integration.py**: Reference implementation of fixed integration tests

Key patterns: Use direct `trainer_fn` parameters, event-driven synchronization, and deterministic timing with `mock_time` fixture.



