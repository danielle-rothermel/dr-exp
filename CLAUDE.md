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

### Supabase
- **Install Supabase CLI**: `brew install supabase/tap/supabase` (recommended) or other methods
- **Start local Supabase**: `supabase start` (requires Docker)
- **Stop local Supabase**: `supabase stop`
- **Reset local database**: `supabase db reset` (applies all migrations)

## Architecture Overview

This is an experiment management system for coordinating deep learning experiments on SLURM GPU clusters. The system supports three modes: local development with JSON files (files_local), local development with full Supabase features (supabase_local), and production deployment (supabase_remote).

### Components

1. **Job Database Layer** (`src/dr_exp/job_db/`):
   - `BaseJobDB`: Abstract base class defining the interface
   - `LocalJobDB`: Simple database using local JSON files for basic development
   - `SupabaseJobDB`: PostgreSQL database client for both local and production Supabase
   - Factory pattern in `utils/jobdb_factory.py` switches between them via `EXPMGR_MODE` env var

2. **Manager/Worker System** (`src/dr_exp/manage/`):
   - `manager.py`: Streamlined manager that coordinates workers using abstract interface methods
   - `worker.py`: Individual workers with improved error handling and separation of concerns
   - `process_manager.py`: Process management abstraction for launching and monitoring workers
   - Heartbeat system for health monitoring and automatic recovery
   - Support for multiple workers per GPU (configurable)
   - Clean separation between coordination logic and database implementation details

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
   - Local file storage in files_local mode
   - Supabase object storage in production mode
   - Configurable logging paths and formats

7. **Training Examples** (`src/dr_exp/train_examples/`):
   - Dummy trainer implementation demonstrating integration
   - Hydra configs for experiment configuration
   - Example parameter sweeps and overrides

8. **System Factory** (`src/dr_exp/utils/factory.py`):
   - `SystemConfig`: Unified configuration for all system components
   - `Factory`: Creates properly integrated managers, workers, and database clients
   - `create_system()`: Main entry point for system initialization
   - Environment-aware configuration with reasonable defaults
   - Shared instances to ensure consistency across components

### Environment Configuration

- `EXPMGR_MODE`: Database mode selection
  - `"files_local"`: Local JSON files (simple, no Docker required)
  - `"supabase_local"`: Local Supabase with full features (requires Docker)
  - `"supabase_remote"`: Production Supabase (requires cloud account)
- `DR_EXP_BASE_PATH`: Base directory for job data storage
- `ADMIN_API_KEY`: API key for admin endpoints (defaults to "testkey")
- Supabase connection vars (for supabase_remote): `SUPABASE_URL`, `SUPABASE_KEY`, `SUPABASE_SERVICE_ROLE_KEY`
- `PYTHONPATH`: Should include the project root for proper imports

**Local Supabase Setup:**
```bash
# Start local Supabase (auto-applies migrations)
supabase start

# Set mode for local Supabase
export EXPMGR_MODE=supabase_local

# Local Supabase automatically configures:
# - URL: http://127.0.0.1:54321
# - Service role key: Auto-configured
# - Storage bucket: experiment-artifacts
```

### CLI Commands

The manager CLI (`scripts/manager_cli.py`) provides comprehensive job management using grouped commands:

**System Commands (`manager-cli system <command>`):**
- `run`: Start the manager process with worker supervision
  - `--gpus-per-node`: Number of GPUs available (default: 1)
  - `--workers-per-gpu`: Workers per GPU (default: 1)
  - `--heartbeat-timeout`: Worker timeout in seconds (default: 60)
  - `--idle-timeout-mins`: Manager idle timeout (default: 30)
- `discover-gpus`: List visible GPU IDs from environment
- `run-worker <worker_id> <work_dir>`: Run a single worker process
- `status`: Show system status, configuration, and environment info

**Job Commands (`manager-cli job <command>`):**
- `list-jobs`: List jobs ordered by priority
  - `--status`: Filter by status (queued, running, completed, failed, killed)
  - `--limit`: Number of jobs to display (default: 20)
- `boost-priority <job_id>`: Increase job priority
  - `--amount`: Priority boost amount (default: 100)
- `set-priority <job_id> <priority>`: Set absolute priority (0-1000)
  - `--reason`: Optional reason for change
- `run-one`: Create and immediately execute a high-priority job
  - `--overrides`: Hydra-style config overrides (e.g., "model=resnet,lr=0.001")
  - `--priority`: Priority level (default: 850)
  - `--config-path`: Path to config directory
  - `--config-name`: Config file name (default: config.yaml)
- `upload-configs`: Generate and upload experiment configurations
  - `--sweep`: Parameter sweeps (e.g., "model=resnet,vit lr=0.01,0.001")
  - `--priority`: Set initial priority (0-1000)

**Admin Commands (`manager-cli admin <command>`):**
- `reap-stale-jobs`: Mark jobs with stale heartbeats as failed
  - `--max-age-mins`: Heartbeat age threshold (default: 60)
- `cleanup-run-data`: Remove old job data and upload directories

**Examples:**
```bash
# Start manager with 2 GPUs, 2 workers each
uv run python scripts/manager_cli.py system run --gpus-per-node 2 --workers-per-gpu 2

# Check system status
uv run python scripts/manager_cli.py system status

# List queued jobs
uv run python scripts/manager_cli.py job list-jobs --status queued

# Upload configs with sweep
uv run python scripts/manager_cli.py job upload-configs --sweep "model=resnet,vit lr=0.01,0.001"

# Run single job immediately
uv run python scripts/manager_cli.py job run-one --overrides "model=resnet,lr=0.001"

# Clean up stale jobs
uv run python scripts/manager_cli.py admin reap-stale-jobs
```

### Key Design Patterns

- **Streamlined Architecture**: Clean separation between coordination logic and implementation details
- **Abstract Interface Methods**: Manager uses only abstract methods, eliminating database-specific code paths
- **Factory Pattern**: Unified system creation with shared instances and consistent configuration
- **Process Management Abstraction**: Clean separation between manager coordination and process lifecycle
- **Improved Error Handling**: Structured error management with comprehensive logging and recovery
- **Heartbeat System**: Workers send regular heartbeats, manager monitors health with automatic recovery
- **Storage Abstraction**: Unified interface for local files and cloud storage
- **Priority Queue**: Jobs processed by priority with reservation system
- **Event-Driven Updates**: WebSocket for real-time UI updates
- **Command Pattern CLI**: Extensible command architecture with grouped subcommands and centralized validation
- **Environment Awareness**: SLURM-aware configuration with automatic directory management

### Development Workflow

1. **Local Development Setup (Recommended: Supabase Local)**:
   ```bash
   # Install dependencies
   uv sync
   cd react-babysitter-ui && npm install && cd ..
   
   # Start local Supabase
   supabase start
   
   # Set mode for local Supabase
   export EXPMGR_MODE=supabase_local
   
   # Start backend and frontend
   uv run uvicorn dr_exp.api.main:app --reload &
   cd react-babysitter-ui && npm run dev
   ```

   **Alternative: Files Local (No Docker)**:
   ```bash
   # Set mode for simple file storage
   export EXPMGR_MODE=files_local
   
   # Start backend and frontend
   uv run uvicorn dr_exp.api.main:app --reload &
   cd react-babysitter-ui && npm run dev
   ```

2. **Running Experiments**:
   ```bash
   # Upload configs with priority (works with any mode)
   uv run python -m scripts.manager_cli upload-configs --sweep "model=resnet,vit" --priority 500
   
   # Start manager (spawns workers automatically)
   uv run python scripts/run_manager.py --gpus-per-node 2 --workers-per-gpu 2
   
   # Or run individual workers (useful for development/testing)
   uv run python scripts/run_worker.py --worker-id dev_worker
   
   # Use the manager CLI for comprehensive control
   uv run python scripts/manager_cli.py run --gpus-per-node 2 --workers-per-gpu 2
   
   # Run a single high-priority job immediately
   uv run python scripts/manager_cli.py run-one --overrides "model=resnet,lr=0.001"
   ```

3. **Testing**:
   ```bash
   # Run all tests (most run in files_local mode for speed)
   uv run pytest
   
   # Run specific test module
   uv run pytest tests/manage/test_manager.py
   
   # Run with coverage
   uv run pytest --cov=dr_exp
   
   # Run Supabase integration tests (requires local Supabase)
   uv run python scripts/test_supabase.py --type isolated
   
   # Run all Supabase tests with database reset
   uv run python scripts/test_supabase.py --type all --reset-db
   ```

4. **Database Management**:
   ```bash
   # Local Supabase: Reset and reapply migrations
   supabase db reset
   
   # Files Local: Reset JSON database
   uv run python scripts/reset_local_jobdb.py
   
   # View local Supabase data in browser
   open http://127.0.0.1:54323
   ```

5. **Production Deployment**:
   - Set `EXPMGR_MODE=supabase_remote` with Supabase credentials
   - Deploy on SLURM cluster
   - Submit jobs via `sbatch scripts/slurm_job.sbatch`
   - Monitor via web UI or CLI

### Architecture Improvements (Recent Refactoring)

The system has been significantly refactored to achieve a cleaner, more maintainable architecture:

- **Streamlined Interface Methods**: New abstract methods in `BaseJobDB` eliminate database-specific code from manager
  - `list_running_jobs()`: Get currently running jobs
  - `get_stale_jobs()`: Find jobs with stale heartbeats  
  - `mark_jobs_failed()`: Batch job failure marking
  - `has_queued_jobs()`: Quick queue status check
  - `get_queue_summary()`: Preview of queued jobs

- **Clean Separation of Concerns**: 
  - Manager focuses purely on coordination logic
  - Workers handle job execution with improved error handling
  - Process management abstracted into `ProcessManager`
  - Factory pattern ensures consistent system configuration

- **Improved Error Handling**: Structured error management with comprehensive logging and recovery mechanisms

- **Integration Tests**: Comprehensive test suite demonstrating end-to-end workflows

### Testing Strategy

- **Unit Tests**: Each component has dedicated unit tests
- **Integration Tests**: Manager/worker coordination and system-wide functionality  
- **Interface Tests**: Verify abstract interface compliance across implementations
- **Files Local Testing**: Most tests run in files_local mode for speed
- **Fixtures**: Shared test utilities in `conftest.py` files
- **Test Organization**: Tests mirror source structure in `tests/`

### SLURM Integration

- **Job Script**: `scripts/slurm_job.sbatch` for cluster submission
- **GPU Detection**: Automatic GPU discovery via `nvidia-smi`
- **Worker Scaling**: Configurable workers per GPU
- **Resource Management**: Proper cleanup on job termination