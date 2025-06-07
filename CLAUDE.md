# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

### Python Backend
- **Install dependencies**: `uv sync`
- **Run tests**: `uv run pytest`
- **Start API server**: `uv run uvicorn dr_exp.api.main:app --reload` (serves on http://localhost:8000)
- **Run manager**: `uv run python scripts/run_manager.py`
- **Run worker**: `uv run python scripts/run_worker.py`
- **Manager CLI**: `uv run python scripts/manager_cli.py <command>` (see CLI Commands section)
- **Reset local job database**: `uv run python scripts/reset_local_jobdb.py`

### React Frontend
- **Navigate to frontend**: `cd react-babysitter-ui`
- **Install dependencies**: `npm install`
- **Start dev server**: `npm run dev` (serves on http://localhost:5173)
- **Build**: `npm run build`
- **Lint**: `npm run lint`

### Supabase (for real database mode)
- **Install Supabase CLI**: `npm install -g supabase` or via Homebrew
- **Start local Supabase**: `supabase start` (requires Docker)
- **Stop local Supabase**: `supabase stop`

## Architecture Overview

This is an experiment management system for coordinating deep learning experiments on SLURM GPU clusters. The system supports both local development (mock mode) and production deployment (real mode).

### Components

1. **Job Database Layer** (`src/dr_exp/job_db/`):
   - `BaseJobDB`: Abstract base class defining the interface
   - `LocalJobDB`: Mock database using local JSON files for development
   - `SupabaseJobDB`: Real PostgreSQL database client for production
   - Factory pattern in `utils/jobdb_factory.py` switches between them via `EXPMGR_MODE` env var

2. **Manager/Worker System** (`src/dr_exp/manage/`):
   - `manager_logic.py`: Spawns and monitors worker processes on SLURM nodes
   - `worker_logic.py`: Individual workers that claim jobs and execute training
   - Heartbeat system for health monitoring and automatic recovery
   - Support for multiple workers per GPU (configurable)

3. **Priority System** (`src/dr_exp/utils/priority.py`):
   - Priority range: 0-1000 with predefined classes (SYSTEM, URGENT, HIGH, NORMAL, LOW)
   - Job reservations with timeout mechanism
   - Priority boost/set capabilities with audit trail
   - "Run One" feature for immediate execution of high-priority jobs

4. **API Layer** (`src/dr_exp/api/`):
   - FastAPI backend serving job data to the React UI
   - WebSocket support for real-time updates
   - Endpoints for listing jobs, getting configs, fetching metrics
   - Admin endpoints for killing/requeuing jobs (requires API key)
   - Metrics caching for performance

5. **React Frontend** (`react-babysitter-ui/`):
   - Real-time monitoring interface for experiments
   - Job table with status tracking and priority display
   - Detailed job views with metrics visualization
   - Built with React 19, Vite, TailwindCSS v4

6. **Logging System** (`src/dr_exp/logging/`):
   - `StructuredLogger`: Comprehensive metrics and artifact logging
   - Local file storage in mock mode
   - Supabase object storage in production mode
   - Configurable logging paths and formats

7. **Training Examples** (`src/dr_exp/train_examples/`):
   - Dummy trainer implementation demonstrating integration
   - Hydra configs for experiment configuration
   - Example parameter sweeps and overrides

### Environment Configuration

- `EXPMGR_MODE`: Set to "mock" for local development, "real" for production
- `DR_EXP_BASE_PATH`: Base directory for job data storage
- `ADMIN_API_KEY`: API key for admin endpoints (defaults to "testkey")
- Supabase connection vars: `SUPABASE_URL`, `SUPABASE_KEY`, `SUPABASE_SERVICE_ROLE_KEY`
- `PYTHONPATH`: Should include the project root for proper imports

### CLI Commands

The manager CLI (`scripts/manager_cli.py`) provides comprehensive job management:

**Job Operations:**
- `upload-configs`: Generate and upload experiment configurations
  - `--sweep`: Specify parameter sweeps (e.g., "model=resnet,vit lr=0.01,0.001")
  - `--priority`: Set initial priority (0-1000)
- `list-jobs`: List jobs with filtering options
  - `--status`: Filter by status (queued, running, completed, failed, killed)
  - `--limit`: Number of jobs to display
- `get-job <job_id>`: Get detailed information about a specific job
- `kill-job <job_id>`: Kill a running job
- `requeue-job <job_id>`: Requeue a failed/killed job

**Priority Management:**
- `boost-priority <job_id> --amount <n>`: Increase job priority
- `set-priority <job_id> --priority <n>`: Set absolute priority
- `run-one`: Create and immediately execute a high-priority job
  - `--overrides`: Hydra-style config overrides
  - `--priority`: Priority level (default: 850)

**Maintenance:**
- `reap-stale`: Clean up stale jobs (jobs without recent heartbeats)
- `cleanup-storage`: Remove old job data and logs
- `reset-db`: Reset the local job database (mock mode only)

### Key Design Patterns

- **Factory Pattern**: Database client selection based on environment
- **Abstract Base Classes**: Consistent interfaces for job DB and logging
- **Multiprocessing**: Manager spawns worker processes with proper isolation
- **Heartbeat System**: Workers send regular heartbeats, manager monitors health
- **Storage Abstraction**: Unified interface for local files and cloud storage
- **Priority Queue**: Jobs processed by priority with reservation system
- **Event-Driven Updates**: WebSocket for real-time UI updates

### Development Workflow

1. **Local Development Setup**:
   ```bash
   # Create .env file with mock mode
   echo "EXPMGR_MODE=mock" > .env
   
   # Install dependencies
   uv sync
   cd react-babysitter-ui && npm install && cd ..
   
   # Start backend and frontend
   uv run uvicorn dr_exp.api.main:app --reload &
   cd react-babysitter-ui && npm run dev
   ```

2. **Running Experiments**:
   ```bash
   # Upload configs with priority
   uv run python scripts/manager_cli.py upload-configs --sweep "model=resnet,vit" --priority 500
   
   # Start manager (spawns workers)
   uv run python scripts/run_manager.py
   
   # Or run individual workers
   uv run python scripts/run_worker.py
   ```

3. **Testing**:
   ```bash
   # Run all tests
   uv run pytest
   
   # Run specific test module
   uv run pytest tests/manage/test_manager.py
   
   # Run with coverage
   uv run pytest --cov=dr_exp
   ```

4. **Production Deployment**:
   - Set `EXPMGR_MODE=real` with Supabase credentials
   - Deploy on SLURM cluster
   - Submit jobs via `sbatch scripts/slurm_job.sbatch`
   - Monitor via web UI or CLI

### Testing Strategy

- **Unit Tests**: Each component has dedicated unit tests
- **Integration Tests**: Manager/worker interaction, API endpoints
- **Mock Mode Testing**: Most tests run in mock mode for speed
- **Fixtures**: Shared test utilities in `conftest.py` files
- **Test Organization**: Tests mirror source structure in `tests/`

### SLURM Integration

- **Job Script**: `scripts/slurm_job.sbatch` for cluster submission
- **GPU Detection**: Automatic GPU discovery via `nvidia-smi`
- **Worker Scaling**: Configurable workers per GPU
- **Resource Management**: Proper cleanup on job termination