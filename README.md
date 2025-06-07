# Experiment Manager (dr_exp)
## 1. Overview
- The Experiment Manager (`dr_exp`) is a system designed to coordinate, execute, monitor, and track large-scale deep learning experiments, primarily on SLURM-managed GPU clusters. It aims to streamline the experimentation lifecycle by providing tools for efficient configuration management, robust job execution, centralized data collection (configurations, metadata, logs, metrics, artifacts), and real-time monitoring via a web interface.
- This system prioritizes reproducibility, modularity for agent-ready development, and researcher-centric control.
## 2. Key Features
- **Efficient Experimentation:** Simplified definition and execution of hyperparameter sweeps using Hydra.
- **Priority-Based Job Scheduling:** Smart job queue with priority levels (0-1000) for urgent experiments and deadline management.
- **"Run One" Functionality:** Reserve and immediately execute single high-priority jobs bypassing the queue.
- **Robust Job Execution:** Designed for SLURM environments, with considerations for error handling and job management.
- **Centralized Data Management:** Uses Supabase (PostgreSQL and Object Storage) as a single source of truth for all experiment-related data.
- **Real-time Monitoring & Control:** A React-based web UI (Babysitter UI) provides live insights and control over experiments via a FastAPI backend.
- **Advanced Job Management:** Boost job priorities, set reservations, and list jobs by priority with comprehensive CLI tools.
- **Reproducibility:** Captures code versions, configurations, and (planned) environment details.
- **Modular & Agent-Ready Design:** Components are designed with clear interfaces for independent development and testing, suitable for agentic coders.
## 3. System Architecture
- The system comprises several key components that interact to manage the experiment lifecycle:
- ```plain text
  +----------------------+      +---------------------+      +---------------------+
  | Hydra Config         |----->| Supabase            |<---->| FastAPI Backend     |
  | Generator (CLI)      |      | (DB & Storage)      |      | (API & WebSockets)  |
  +----------------------+      +----------^----------+      +---------^-----------+
                                           |                           |
                                           | (Job Claim, Logging,      | (UI Data, Control)
                                           |  Artifacts, Heartbeats)   |
                                           |                           |
  +----------------------+      +----------+----------+      +--------+------------+
  | SLURM Job Submission |----->| SLURM Manager       |----->| Worker Process(es)  |<---> React Babysitter UI|
  | (sbatch script)      |      | (Per SLURM Job)     |      | (Run train(), Logs) |      | (Monitoring & Ctrl) |
  +----------------------+      +---------------------+      +----------+----------+      +---------------------+
                                                                       |
                                                                       | (Uses)
                                                              +--------+--------+
                                                              | StructuredLogger|
                                                              +-----------------+
                                                              | train(cfg, log) |
                                                              | (User Code)     |
                                                              +-----------------+
  ```
- For a detailed breakdown, please refer to the design documents in the `docs/` directory.
### Core Components:
- **Config Generator (CLI):** Generates and uploads Hydra-based experiment configurations to Supabase.
- **Supabase:** Central PostgreSQL database and object storage.
- **SLURM Manager:** Python script launched by SLURM `sbatch`; manages worker processes on allocated nodes/GPUs.
- **Worker Process:** Python script that claims jobs, runs training logic, logs metrics/artifacts using `StructuredLogger`, and uploads results.
 - **StructuredLogger:** Python class in `dr_exp.logging` that handles local logging of metrics, checkpoints, and artifacts.
- **FastAPI Backend:** Serves as the API layer between Supabase and the UI/other clients.
- **React Babysitter UI:** Web interface for monitoring and controlling experiments.
- **Mock Components:** Local mocks for Supabase, FastAPI, and the training function to facilitate offline development and testing.
## 4. Getting Started
### 4.1. Prerequisites
- Python (e.g., 3.9+)
- Node.js and npm (for React frontend)
- Docker (for running Supabase locally via `supabase start` during development)
- A Supabase Account (for the remote cloud instance, optional for local development)
- [Supabase CLI](https://supabase.com/docs/guides/cli/getting-started) installed (via Homebrew: `brew install supabase/tap/supabase`)
- Git
### 4.2. Repository Setup
**Project Structure (Overview):**
```plain text
dr_exp/
├── src/
│   └── dr_exp/
│       ├── api/             # FastAPI backend
│       ├── job_db/          # Database helpers (LocalDBClient, Supabase client)
│       ├── manage/          # Manager and worker logic
│       ├── logging/         # Structured logging utilities
│       ├── train_examples/  # Example trainer and Hydra configs
│       └── utils/           # Helper utilities
├── supabase/            # Supabase project configuration and migrations
├── react-babysitter-ui/ # React frontend
├── scripts/             # CLI entry points and helpers
├── tests/               # Pytest tests
├── docs/                # Project documentation
├── pyproject.toml
└── README.md
```
### 4.3. Environment Setup

**Python Backend:**
```bash
uv sync
```

**React Frontend:**
```bash
cd react-babysitter-ui
npm install
```

**Local Supabase (Recommended for Development):**
```bash
# Start local Supabase development server
supabase start

# The migrations will be automatically applied
```

### 4.4. Configuration

The system supports three modes for data storage:

#### 4.4.1. Local Supabase Mode (Recommended for Development)

This mode uses a local PostgreSQL database with the full Supabase feature set, perfect for development and testing.

**Setup:**
```bash
# 1. Start local Supabase
supabase start

# 2. Set environment mode
export EXPMGR_MODE=supabase_local

# 3. Run the system
uv run uvicorn dr_exp.api.main:app --reload
```

The local mode automatically configures:
- **Database URL:** `http://127.0.0.1:54321`
- **Service Role Key:** Auto-configured from local Supabase
- **Storage Bucket:** `experiment-artifacts` (created automatically)

**Database Schema:**
- All tables are created via migrations in `supabase/migrations/`
- Includes priority system (0-1000 range)
- Job reservation system for worker-specific jobs
- Storage integration for metrics and artifacts

#### 4.4.2. Files Local Mode (Simple Mock)

Uses local JSON files for development without Docker dependency.

```bash
export EXPMGR_MODE=files_local
```

#### 4.4.3. Production Supabase Mode

For production deployment with cloud Supabase.

Create a `.env` file:
```bash
# .env - For production (DO NOT COMMIT real secrets)
EXPMGR_MODE=supabase_remote
SUPABASE_URL="your_supabase_project_url"
SUPABASE_SERVICE_ROLE_KEY="your_supabase_service_role_key"
```

## 5. Running the System

### 5.1. Quick Start (Local Supabase)

**Terminal 1 - Start Supabase:**
```bash
supabase start
```

**Terminal 2 - Start Backend:**
```bash
export EXPMGR_MODE=supabase_local
uv run uvicorn dr_exp.api.main:app --reload
```

**Terminal 3 - Start Frontend:**
```bash
cd react-babysitter-ui
npm run dev
```

**Terminal 4 - Upload Some Jobs:**
```bash
export EXPMGR_MODE=supabase_local
uv run python -m scripts.manager_cli upload-configs --sweep "model=resnet,vit lr=0.01,0.001"
```

Visit `http://localhost:5173` to see the jobs in the UI!

### 5.2. Database Management

**Reset Local Database:**
```bash
# Reset and reapply all migrations
supabase db reset

# Or for files_local mode
uv run python scripts/reset_local_jobdb.py
```

**View Database:**
```bash
# Open Supabase Studio (local)
open http://127.0.0.1:54323
```

### 5.3. SLURM Mode (Production)

For actual cluster experiments:

1. **Set production mode:**
   ```bash
   export EXPMGR_MODE=supabase_remote
   # Or configure .env file with production Supabase credentials
   ```

2. **Upload experiment configurations:**
   ```bash
   uv run python -m scripts.manager_cli upload-configs --sweep "model=resnet,vit optim=adam,sgd"
   ```

3. **Submit to SLURM:**
   ```bash
   sbatch scripts/slurm_job.sbatch
   ```

## 6. Priority System Usage

The system includes a comprehensive priority-based job scheduling system with the following capabilities:

### Priority Classes
- **SYSTEM (900-1000):** Critical system maintenance and urgent fixes
- **URGENT (700-899):** Deadline-driven experiments and "run one" jobs  
- **HIGH (400-699):** Important experiments that should run soon
- **NORMAL (100-399):** Default priority range for regular experiments
- **LOW (0-99):** Background jobs that can run when resources are available

### Basic Usage

**Upload jobs with priority:**
```bash
# Upload with high priority for urgent experiments
uv run python scripts/upload_configs.py --priority 800 --sweep "model=resnet,vit optim=adam,sgd"

# Upload with normal priority (default is 100)
uv run python scripts/upload_configs.py --sweep "lr=0.001,0.01"
```

**List jobs by priority:**
```bash
# List queued jobs ordered by priority (highest first)
uv run python -m scripts.manager_cli list-jobs --status queued --limit 20

# List all jobs regardless of status
uv run python -m scripts.manager_cli list-jobs --status queued running completed --limit 50
```

**Manage job priorities:**
```bash
# Boost a job's priority by 200 points
uv run python -m scripts.manager_cli boost-priority <job_id> --amount 200

# Set exact priority with reason
uv run python -m scripts.manager_cli set-priority <job_id> 900 --reason "Critical deadline tomorrow"
```

**Run single job immediately:**
```bash
# Reserve and run a single job with URGENT priority, bypassing the queue
uv run python -m scripts.manager_cli run-one --overrides "model=resnet lr=0.001" --priority 850

# Run with custom config
uv run python -m scripts.manager_cli run-one --config-name my_config.yaml --overrides "epochs=50"
```

### Advanced Features

**Job Reservations:**
- Jobs can be reserved for specific workers with automatic timeout
- Reserved jobs bypass normal queue order when claimed by the designated worker
- Reservations automatically expire if not claimed within the timeout period

**Priority Management:**
- Priority changes are logged with timestamps and reasons for audit trails
- Priority boost counts are tracked per job
- Priorities are automatically clamped to valid range (0-1000)

**Queue Monitoring:**
- Manager logs top queued jobs by priority during idle periods
- Real-time priority-aware job claiming ensures highest priority jobs run first

## 7. Development
### 7.1. Development Modes

**Local Supabase (`EXPMGR_MODE=supabase_local`):**
- Full PostgreSQL database with Supabase features
- Real-time updates, storage, and all production functionality
- Perfect for testing database migrations and complex workflows
- Requires Docker but provides the most realistic development environment

**Files Local (`EXPMGR_MODE=files_local`):**
- Simple JSON file storage in `job_data/` directory
- No external dependencies (no Docker required)
- Good for basic development and testing
- Reset with `uv run python scripts/reset_local_jobdb.py`

**Production (`EXPMGR_MODE=supabase_remote`):**
- Cloud Supabase instance for actual experiments
- Requires Supabase account and project setup

### 7.2. Testing
- Tests are written using pytest and located in the tests/ directory.
- To run tests:
```plain text
uv run pytest
```
## 8. Documentation
- **Component Specifications:** Detailed design documents live in the `docs/` directory.  See `docs/supabase_schema.md`, `docs/manager_flow.md`, `docs/manager_cli.md`, and `docs/frontend_ui.md`.
- **Priority System:** Comprehensive documentation of the priority-based job scheduling system is in `docs/priority_system.md`.
- **Training Examples:** Example configs and the dummy trainer are described in `docs/train_examples.md`.
- **Structured Logging:** The `StructuredLogger` used by workers is documented in `docs/structured_logger.md`.
- This README provides a starting point. It should be updated as the project evolves, particularly the "Getting Started" and "Running the System" sections.

