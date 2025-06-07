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

## Current Problem + Refactoring Plan

The core of the system—the coordination between the Manager and Worker—is not being reliably tested. The key integration tests in tests/manage/test_integration.py are currently skipped (@pytest.mark.skip) because they are flaky and non-deterministic, largely due to a reliance on time.sleep() for synchronization. This represents a critical gap in our confidence in the system's stability.

To address this, a comprehensive, four-phase plan has been developed, as detailed in test_refactor_plan.md. This plan goes beyond just fixing the skipped tests; it aims to systematically improve the entire test suite's reliability, maintainability, and coverage.

Your task is to execute the full plan outlined in test_refactor_plan.md. You will proceed through the phases in order, starting with the most critical fixes. This structured approach will:

- Restore confidence in the core functionality.
- Build a robust and deterministic testing infrastructure.
- Expand coverage to include critical edge cases and error conditions.

Begin with Phase 1, which focuses on fixing the skipped integration tests. Refer to test_refactor_plan.md for the specific implementation details for each phase.



