# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

### Python Backend
- **Install dependencies**: `uv sync`
- **Run tests**: `uv run pytest`
- **Start API server**: `uv run uvicorn dr_exp.api.main:app --reload` (serves on http://localhost:8000)
- **Run manager CLI**: `uv run python scripts/manager_cli.py <command>`
- **Run worker**: `uv run python scripts/run_worker.py`
- **Reset local job database**: `uv run python scripts/reset_local_jobdb.py`

### React Frontend
- **Navigate to frontend**: `cd react-babysitter-ui`
- **Install dependencies**: `npm install`
- **Start dev server**: `npm run dev` (serves on http://localhost:5173)
- **Build**: `npm run build`
- **Lint**: `npm run lint`

### Supabase (for real database mode)
- **Install Supabase CLI**: via npm or Homebrew
- **Start local Supabase**: `supabase start` (requires Docker)

## Architecture Overview

This is an experiment management system for coordinating deep learning experiments on SLURM GPU clusters. The system has three main modes:

### Components
1. **Job Database Layer** (`src/dr_exp/job_db/`):
   - `LocalDBClient`: Mock database using local JSON files for development
   - `SupabaseClient`: Real PostgreSQL database client for production
   - Factory pattern in `utils/jobdb_factory.py` switches between them via `EXPMGR_MODE` env var

2. **Manager/Worker System** (`src/dr_exp/manage/`):
   - `Manager`: Spawns and monitors worker processes on SLURM nodes
   - `worker_logic`: Individual workers that claim jobs and execute training
   - Workers use `StructuredLogger` for metrics/artifacts logging

3. **API Layer** (`src/dr_exp/api/`):
   - FastAPI backend that serves job data to the React UI
   - Endpoints for listing jobs, getting configs, fetching metrics
   - Admin endpoints for killing/requeuing jobs (requires API key)

4. **React Frontend** (`react-babysitter-ui/`):
   - Real-time monitoring interface for experiments
   - Uses Axios to communicate with FastAPI backend
   - Built with React 19, Vite, TailwindCSS

5. **Training Examples** (`src/dr_exp/train_examples/`):
   - Dummy trainer implementation and Hydra configs
   - Shows how to integrate user training code with the system

### Environment Configuration
- `EXPMGR_MODE`: Set to "mock" for local development, "real" for production
- `DR_EXP_BASE_PATH`: Base directory for job data storage
- `ADMIN_API_KEY`: API key for admin endpoints (defaults to "testkey")
- Supabase connection vars: `SUPABASE_URL`, `SUPABASE_KEY`, `SUPABASE_SERVICE_ROLE_KEY`

### Key Design Patterns
- **Factory pattern**: `get_supabase_client()` returns appropriate client based on environment
- **Multiprocessing**: Manager spawns worker processes, one per GPU with configurable workers per GPU
- **Heartbeat system**: Workers send regular heartbeats, manager restarts stale workers
- **Storage abstraction**: Local file storage in mock mode, Supabase object storage in real mode

### Development Workflow
1. Use mock mode (`EXPMGR_MODE=mock`) for local development
2. Start both backend (`uvicorn`) and frontend (`npm run dev`) for full UI testing
3. Manager CLI handles config upload, job submission, and cleanup tasks
4. Tests are in `tests/` directory, organized by component