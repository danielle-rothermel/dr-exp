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
- Node.js and npm (for Supabase CLI, if not using other installation methods like Homebrew)
- Docker (for running Supabase locally via `supabase start` during development)
- A Supabase Account (for the remote cloud instance)
- [Supabase CLI](https://supabase.com/docs/guides/cli/getting-started) installed and configured.
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

Python Backend
```
uv sync
uv run python scripts/start_backend.py
```

Frontend
```
cd react-babysitter-ui
npm install
npm run dev
```

### 4.4. Configuration
- The system will rely on environment variables for sensitive information like Supabase keys. Create a `.env` file (and add it to `.gitignore`) for local development. Example:
```plain text
# .env - For local development (DO NOT COMMIT if it contains real secrets)
# Supabase connection details for the REAL client (not the mock)
SUPABASE_URL="your_supabase_project_url"
SUPABASE_KEY="your_supabase_anon_key"
SUPABASE_SERVICE_ROLE_KEY="your_supabase_service_role_key"

# Mode for client selection (mock or real)
EXPMGR_MODE="mock" # Set to "real" to use actual Supabase
```
- Your application code will need to load these (e.g., using `python-dotenv`).

## 5. Running the System (High-Level)
    - Detailed instructions will evolve as components are built.
        - Mock Mode (for local development/testing):
        - Set EXPMGR_MODE="mock" in your environment. This will use the LocalDBClient.
        - You can reset the mock environment using:
        - ```plain text
          uv run python scripts/reset_mock_db.py
          ```

### 5.1 Local Backend and UI
To experiment with the mock FastAPI backend and the React Babysitter UI together:

1. **Start the backend** from the repository root:
   ```bash
   uv run uvicorn dr_exp.api.main:app --reload
   ```
   The server listens on `http://localhost:8000`.

2. **Start the React UI** in another terminal:
   ```bash
   cd react-babysitter-ui
   npm install   # first time only
   npm run dev
   ```
   Vite serves the app at `http://localhost:5173` and it queries `http://localhost:8000/jobs`.

Opening the UI should display the jobs table fetched from the backend.
        - SLURM Mode (for actual experiments):
        - This will involve:
            1. Setting `EXPMGR_MODE="real"`.
           2. Using `python scripts/manager_cli.py upload-configs` to populate Supabase with experiment configurations.
            3. Submitting jobs to SLURM via an `sbatch` script that runs the `SLURM Manager`.
           4. A starter script is provided at `scripts/slurm_job.sbatch`.

## 5.2. Priority System Usage

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

## 6. Development
### 6.1. Mocks
- **LocalDBClient:** Simulates Supabase interactions locally. See `dr_exp/job_db/local_job_db.py`.
- Example training code and Hydra configs live in `src/dr_exp/train_examples`.
- Other mocks, including the FastAPI backend and mock training function, are implemented as described in the PRD.
### 6.2. Testing
- Tests are written using pytest and located in the tests/ directory.
- To run tests:
```plain text
uv run pytest
```
## 7. Documentation
- **Component Specifications:** Detailed design documents live in the `docs/` directory.  See `docs/supabase_schema.md`, `docs/manager_flow.md`, `docs/manager_cli.md`, and `docs/frontend_ui.md`.
- **Priority System:** Comprehensive documentation of the priority-based job scheduling system is in `docs/priority_system.md`.
- **Training Examples:** Example configs and the dummy trainer are described in `docs/train_examples.md`.
- **Structured Logging:** The `StructuredLogger` used by workers is documented in `docs/structured_logger.md`.
- This README provides a starting point. It should be updated as the project evolves, particularly the "Getting Started" and "Running the System" sections.

